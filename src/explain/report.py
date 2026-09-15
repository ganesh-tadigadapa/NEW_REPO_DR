"""Requirement #4d — the one-page PDF an ophthalmologist signs off in under 30 seconds.

Design constraints that come from that 30-second target, not from taste:

  - **One page.** A second page means scrolling, and scrolling means the 30 seconds is
    gone. Everything that matters is above the fold of a single A4 sheet.
  - **The decision first.** Referable yes/no is the largest element on the page, top
    left, colour-coded. The grade is secondary. A reviewer should be able to triage from
    across the room.
  - **Images side by side.** The original and the Grad-CAM overlay at the same scale, so
    the eye can flick between them without re-orienting.
  - **The evidence is a table, not prose.** Counts by quadrant, and the ICDR criteria
    that fired, so the reviewer can check the reasoning rather than trust it.
  - **Disagreements are printed in a box, not buried.** If the CNN and the rules differ,
    that is the single most decision-relevant fact on the page.
  - **The disclaimer is on the page**, not in a footer nobody reads.

No metric that has not been measured appears here. Fields that are unavailable print as
"not available", never as a plausible-looking number.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

import cv2
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, Table, TableStyle

from src.common.config import DISCLAIMER, ICDR_LABELS

PAGE_W, PAGE_H = A4
MARGIN = 14 * mm

INK = colors.HexColor("#15181A")
MUTED = colors.HexColor("#6E757B")
LINE = colors.HexColor("#C8C4BE")
CRIMSON = colors.HexColor("#A8322A")
TEAL = colors.HexColor("#0F6157")
GOLD = colors.HexColor("#8A6210")
GOLD_SOFT = colors.HexColor("#F4EAD3")
CRIMSON_SOFT = colors.HexColor("#F3E2DF")
TEAL_SOFT = colors.HexColor("#DDEBE8")


def _img_reader(bgr: np.ndarray) -> ImageReader:
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("png encode failed")
    return ImageReader(io.BytesIO(buf.tobytes()))


def _para(text, size=8.2, colour=INK, leading=None, bold=False):
    st = ParagraphStyle(
        "p", parent=getSampleStyleSheet()["BodyText"],
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size, leading=leading or size * 1.35, textColor=colour)
    return Paragraph(text, st)


def build_report(result: dict, original_bgr: np.ndarray, overlay_bgr: np.ndarray | None,
                 lesion_bgr: np.ndarray | None = None) -> bytes:
    """Render the report. `result` is the analyze response dict (contract v1)."""
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"DR screening report {result.get('scan_id', '')}")

    y = PAGE_H - MARGIN
    grading = result.get("grading") or {}
    rules = result.get("rule_check") or {}
    quality = result.get("quality") or {}

    # ---------------------------------------------------------------- header
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(INK)
    c.drawString(MARGIN, y - 4, "Diabetic Retinopathy Screening Report")
    c.setFont("Helvetica", 7.6)
    c.setFillColor(MUTED)
    c.drawRightString(PAGE_W - MARGIN, y - 4,
                      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    y -= 12
    c.setFont("Helvetica", 7.4)
    meta = (f"Scan {result.get('scan_id', '—')}   ·   Model {result.get('model_id', '—')}"
            f"   ·   Patient ref {result.get('patient_ref') or '—'}")
    c.drawString(MARGIN, y - 4, meta)
    y -= 8
    c.setStrokeColor(LINE); c.setLineWidth(0.7)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 12

    # ------------------------------------------------------- the decision band
    referable = bool(grading.get("referable"))
    graded = bool(grading)
    # Three distinct states, and conflating them is a real error: an image the gate
    # REJECTED is a clinical instruction to retake, whereas an image the gate PASSED but
    # that no model was available to grade still carries valid lesion evidence and a
    # rule-based grade. Reporting the second as "rejected" would tell a health worker to
    # re-photograph a perfectly good eye.
    gate_passed = bool(quality.get("gradeable"))
    if not gate_passed:
        band_bg, band_fg, headline = GOLD_SOFT, GOLD, "NOT GRADED — IMAGE REJECTED"
        sub = quality.get("recapture_instruction") or "Image did not pass the quality gate."
    elif not graded:
        band_bg, band_fg, headline = GOLD_SOFT, GOLD, "MODEL GRADE UNAVAILABLE"
        reason = result.get("grading_unavailable_reason") or "the grading model is not loaded"
        rg = rules.get("rule_grade")
        sub = (f"Image quality passed. Clinical-rule grade {rg} ({rules.get('rule_label')}) "
               f"is shown below from detected lesions. CNN grade unavailable: {reason}.")
    elif referable:
        band_bg, band_fg, headline = CRIMSON_SOFT, CRIMSON, "REFER TO OPHTHALMOLOGIST"
        sub = "Referable diabetic retinopathy (ICDR grade 2 or above)."
    else:
        band_bg, band_fg, headline = TEAL_SOFT, TEAL, "NO REFERRAL INDICATED"
        sub = "Below the referral threshold. Re-screen at the routine interval."

    sub_para = Paragraph(sub, ParagraphStyle(
        "sub", fontName="Helvetica", fontSize=7.8, leading=9.6, textColor=INK))
    # reserve the right-hand strip for the grade block so text never runs under it
    sub_w = PAGE_W - 2 * MARGIN - 14 * mm - 42 * mm
    _, sub_h = sub_para.wrap(sub_w, 40 * mm)
    band_h = max(18 * mm, 12 * mm + sub_h)

    c.setFillColor(band_bg); c.setStrokeColor(band_fg); c.setLineWidth(0.9)
    c.rect(MARGIN, y - band_h, PAGE_W - 2 * MARGIN, band_h, fill=1, stroke=1)
    c.setFillColor(band_fg); c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN + 7 * mm, y - 7.5 * mm, headline)
    sub_para.drawOn(c, MARGIN + 7 * mm, y - 9.5 * mm - sub_h)

    if graded:
        g = int(grading.get("icdr_grade", 0))
        c.setFillColor(INK); c.setFont("Helvetica-Bold", 22)
        c.drawRightString(PAGE_W - MARGIN - 7 * mm, y - 10 * mm, str(g))
        c.setFont("Helvetica", 7.2); c.setFillColor(MUTED)
        c.drawRightString(PAGE_W - MARGIN - 7 * mm, y - 14.5 * mm,
                          f"ICDR · {ICDR_LABELS.get(g, '')}")
        conf = grading.get("confidence")
        if conf is not None:
            cal = "calibrated" if grading.get("confidence_calibrated") else "UNCALIBRATED"
            c.setFont("Helvetica", 6.8)
            c.drawRightString(PAGE_W - MARGIN - 7 * mm, y - 18 * mm,
                              f"confidence {conf:.0%} ({cal})")
    y -= band_h + 9

    # ---------------------------------------------------------------- images
    img_h = 52 * mm
    gap = 5 * mm
    img_w = (PAGE_W - 2 * MARGIN - gap) / 2
    side = min(img_h, img_w)
    x0 = MARGIN
    c.setFont("Helvetica-Bold", 7.4); c.setFillColor(MUTED)
    c.drawString(x0, y - 3, "FUNDUS IMAGE (AS CAPTURED)")
    c.drawString(x0 + side + gap, y - 3, "MODEL ATTENTION (GRAD-CAM)")
    y -= 6
    c.drawImage(_img_reader(original_bgr), x0, y - side, side, side)
    if overlay_bgr is not None:
        c.drawImage(_img_reader(overlay_bgr), x0 + side + gap, y - side, side, side)
    else:
        c.setFillColor(colors.HexColor("#EFEDEA"))
        c.rect(x0 + side + gap, y - side, side, side, fill=1, stroke=0)
        c.setFillColor(MUTED); c.setFont("Helvetica", 8)
        c.drawCentredString(x0 + side + gap + side / 2, y - side / 2, "not available")
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.rect(x0, y - side, side, side, fill=0, stroke=1)
    c.rect(x0 + side + gap, y - side, side, side, fill=0, stroke=1)
    y -= side + 8

    if graded and (result.get("explain") or {}).get("attention_summary"):
        f = Paragraph(result["explain"]["attention_summary"],
                      ParagraphStyle("s", fontName="Helvetica-Oblique", fontSize=7.6,
                                     leading=9.6, textColor=MUTED))
        w, h = f.wrap(PAGE_W - 2 * MARGIN, 30)
        f.drawOn(c, MARGIN, y - h); y -= h + 7

    # ------------------------------------------------------- evidence table
    # Rendered whenever lesion analysis succeeded. It does not depend on the CNN — that
    # independence is the point of having a rule engine at all.
    if result.get("lesions"):
        les = result.get("lesions") or {}
        rows = [["Lesion evidence", "Total", "ST", "SN", "IT", "IN"]]
        pretty = {"microaneurysms": "Microaneurysms", "haemorrhages": "Haemorrhages",
                  "hard_exudates": "Hard exudates"}
        for key, label in pretty.items():
            blk = les.get(key) or {}
            q = blk.get("by_quadrant") or {}
            rows.append([label, str(blk.get("count", "—")),
                         str(q.get("ST", "—")), str(q.get("SN", "—")),
                         str(q.get("IT", "—")), str(q.get("IN", "—"))])
        t = Table(rows, colWidths=[38 * mm, 13 * mm] + [9 * mm] * 4)
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 7.2),
            ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEDEA")),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        tw, th = t.wrap(0, 0)
        t.drawOn(c, MARGIN, y - th)

        # rule column on the right — starts clear of the table's right edge
        rx = MARGIN + 92 * mm
        rw = PAGE_W - MARGIN - rx
        c.setFont("Helvetica-Bold", 7); c.setFillColor(MUTED)
        c.drawString(rx, y - 6, "ICDR CLINICAL RULE CHECK")
        ry = y - 16
        rp = Paragraph(f"<b>Rule grade {rules.get('rule_grade', '—')}</b> — "
                       f"{rules.get('rule_label', '—')}",
                       ParagraphStyle("rg", fontName="Helvetica", fontSize=7.4,
                                      leading=9, textColor=INK))
        _, rh = rp.wrap(rw, 20 * mm); rp.drawOn(c, rx, ry - rh); ry -= rh + 3
        for crit in (rules.get("criteria_fired") or [])[:3]:
            cp = Paragraph("• " + crit, ParagraphStyle(
                "c", fontName="Helvetica", fontSize=6.4, leading=7.8, textColor=MUTED))
            _, ch = cp.wrap(rw, 30 * mm)
            cp.drawOn(c, rx, ry - ch); ry -= ch + 1.5
        y = min(y - th, ry) - 8

        # ---------------------------------------------- disagreement box
        flag = rules.get("flag")
        if flag:
            msg = rules.get("flag_message") or flag
            p = Paragraph(f"<b>Cross-check:</b> {msg}", ParagraphStyle(
                "f", fontName="Helvetica", fontSize=7.4, leading=9.4, textColor=INK))
            w, h = p.wrap(PAGE_W - 2 * MARGIN - 10 * mm, 60)
            box_h = h + 7 * mm
            c.setFillColor(GOLD_SOFT); c.setStrokeColor(GOLD); c.setLineWidth(0.8)
            c.rect(MARGIN, y - box_h, PAGE_W - 2 * MARGIN, box_h, fill=1, stroke=1)
            p.drawOn(c, MARGIN + 5 * mm, y - box_h + 3.5 * mm)
            y -= box_h + 7

    # ---------------------------------------------------------- quality strip
    c.setFont("Helvetica-Bold", 7); c.setFillColor(MUTED)
    c.drawString(MARGIN, y - 4, "IMAGE QUALITY")
    y -= 12
    checks = (quality.get("checks") or {})
    cx = MARGIN
    for name in ("focus", "illumination", "field_of_view"):
        ch = checks.get(name) or {}
        ok = ch.get("passed")
        col = TEAL if ok else CRIMSON
        c.setFillColor(col); c.circle(cx + 1.6 * mm, y + 1.2, 1.4 * mm, fill=1, stroke=0)
        c.setFillColor(INK); c.setFont("Helvetica", 7.2)
        val = ch.get("value")
        c.drawString(cx + 4.5 * mm, y,
                     f"{name.replace('_', ' ')}: {val if val is None else f'{val:.2f}'} "
                     f"({'pass' if ok else 'FAIL'})")
        cx += 58 * mm
    y -= 8
    if not quality.get("thresholds_fitted", False):
        c.setFillColor(GOLD); c.setFont("Helvetica-Oblique", 6.6)
        c.drawString(MARGIN, y, "Quality thresholds are provisional defaults — not yet "
                                "fitted against human labels.")
        y -= 7

    # ------------------------------------------------------------- sign-off
    y = max(y, MARGIN + 34 * mm)
    c.setStrokeColor(LINE); c.setLineWidth(0.7)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 12
    c.setFont("Helvetica", 7.4); c.setFillColor(INK)
    c.drawString(MARGIN, y, "Reviewing ophthalmologist:")
    c.setStrokeColor(LINE)
    c.line(MARGIN + 40 * mm, y - 1, MARGIN + 95 * mm, y - 1)
    c.drawString(MARGIN + 100 * mm, y, "Agree / Amend to grade:")
    c.line(MARGIN + 145 * mm, y - 1, PAGE_W - MARGIN, y - 1)
    y -= 13
    c.drawString(MARGIN, y, "Signature:")
    c.line(MARGIN + 20 * mm, y - 1, MARGIN + 95 * mm, y - 1)
    c.drawString(MARGIN + 100 * mm, y, "Date:")
    c.line(MARGIN + 112 * mm, y - 1, PAGE_W - MARGIN, y - 1)

    # ------------------------------------------------------------ disclaimer
    c.setFillColor(CRIMSON_SOFT)
    c.rect(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, 9 * mm, fill=1, stroke=0)
    c.setFillColor(CRIMSON); c.setFont("Helvetica-Bold", 7.6)
    c.drawCentredString(PAGE_W / 2, MARGIN + 3.4 * mm, DISCLAIMER.upper())

    c.showPage()
    c.save()
    return buf.getvalue()


def build_report_b64(*args, **kwargs) -> str:
    return base64.b64encode(build_report(*args, **kwargs)).decode("ascii")
