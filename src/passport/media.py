"""Keeping the comparison PDF where the delivery layer can already reach it.

This file is deliberately thin, because the interesting machinery already exists. The
report media store in `src/delivery/media.py` solves exactly the problems a comparison
PDF has — keep the bytes, record the owner, mint a short-lived signed URL that Meta or
Twilio can fetch, and log what was delivered — and it solves them for any PDF, not just
for a screening report. So the comparison PDF is stored there, under its own id, and
gets the signed media URL, the ownership check, the delivery log and the cooldown for
free. There is no second media endpoint and no second signing scheme.

Two things make the two documents distinguishable rather than interchangeable:

  * the media id is `cmp_<screening_id>`, so the files never collide, and
  * the metadata carries `kind: "comparison_report"`, which `src/delivery/routes.py`
    refuses to send — the screening-report endpoint composes screening-report wording,
    and it must not be able to attach a comparison to it.

The PDF is generated LAZILY, on the first request that needs it. `/v1/analyze` stays
exactly as fast as it was: a patient who never opens their passport never pays for a
document nobody asked for.
"""
from __future__ import annotations

import logging

from src.api.evidence import get_review_ledger
from src.delivery import media as delivery_media
from src.passport import service as passport_service
from src.passport.report import build_comparison_report
from src.passport.store import get_passport_store, safe_id

log = logging.getLogger("dr-passport.media")

KIND = "comparison_report"


def comparison_media_id(screening_id: str) -> str:
    """`cmp_<screening_id>`. Constrained by the same rule as every other media id."""
    sid = safe_id(screening_id)
    return f"cmp_{sid}" if sid else ""


def _media_result(comparison: dict, media_id: str, created_at: str | None) -> dict:
    """The fields `ReportMediaStore.save()` copies, and only those.

    The store's `save()` takes an analyse-result-shaped dict and whitelists a handful of
    values out of it. This builds that shape from the comparison's CURRENT side, so the
    grade recorded against the stored file is the same grade the comparison printed.
    """
    current = comparison.get("current") or {}
    return {
        "scan_id": media_id,
        "created_at": created_at,
        "report": {"filename": f"carebridge-comparison-{media_id}.pdf"},
        "grading": {
            "icdr_grade": current.get("icdr_grade"),
            "icdr_label": current.get("severity_label"),
            "referable": current.get("referable"),
        },
        "quality": {"gradeable": True},
    }


def ensure_comparison_pdf(account_id: str, screening_id: str) -> tuple[str, dict] | None:
    """(media_id, comparison) for a comparison PDF that exists on disk, or None.

    None means there is nothing to build: no such screening for this account, or no
    valid comparison (a first screening, or an ungradeable one). Neither is an error.
    """
    store = get_passport_store()
    rec = store.get_screening(screening_id)
    if rec is None or rec.get("account_id") != account_id:
        return None
    comparison = passport_service.comparison_for(account_id, screening_id)
    if not comparison or not comparison.get("available"):
        return None

    media_id = comparison_media_id(screening_id)
    media_store = delivery_media.get_media_store()
    if media_store.pdf_path(media_id) is not None:
        return media_id, comparison

    follow_up = _follow_up_for(account_id, screening_id)
    review = get_review_ledger().latest(safe_id(screening_id))
    try:
        pdf = build_comparison_report(
            comparison,
            timeline=passport_service.timeline(account_id),
            follow_up=follow_up,
            clinician_review=review)
    except Exception:                                    # noqa: BLE001
        log.exception("comparison report generation failed for %s", media_id)
        return None

    media_store.save(_media_result(comparison, media_id, rec.get("created_at")),
                     pdf, account_id=account_id, kind=KIND)
    return media_id, comparison


def _follow_up_for(account_id: str, screening_id: str) -> dict | None:
    """The plan written against THIS screening, whatever has happened since."""
    sid = safe_id(screening_id)
    store = get_passport_store()
    for f in reversed(store.follow_ups(account_id)):
        if f.get("screening_id") == sid:
            return f
    return store.active_follow_up(account_id)


def comparison_pdf_bytes(account_id: str, screening_id: str) -> tuple[bytes, str] | None:
    """(bytes, filename) for download, or None. Ownership is checked by
    `ensure_comparison_pdf`; this never reads a path a caller supplied."""
    made = ensure_comparison_pdf(account_id, screening_id)
    if made is None:
        return None
    media_id, _ = made
    store = delivery_media.get_media_store()
    path = store.pdf_path(media_id)
    if path is None:
        return None
    meta = store.meta(media_id) or {}
    return path.read_bytes(), meta.get("filename") or f"{media_id}.pdf"


__all__ = ["ensure_comparison_pdf", "comparison_pdf_bytes", "comparison_media_id", "KIND"]
