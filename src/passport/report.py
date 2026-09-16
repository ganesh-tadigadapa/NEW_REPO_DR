"""The comparison report PDF.

This is NOT a second PDF architecture. It is the same one: the page geometry, the colour
tokens, the paragraph helper and the disclaimer band are imported from
`src/explain/report.py`, which owns them, so a change to the house style reaches both
documents. What differs is the content, because the two documents answer different
questions — the screening report answers "what does this photograph show?", and this one
answers "what has changed since last time?".

Everything printed here is copied from the comparison object, which was itself built by
subtracting two grades the model already decided. No value on this page is computed from
an image, and the words used for the change are the ones from `comparison.statement()` —
never a stronger claim.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, Table, TableStyle

# The existing report's own design tokens and helpers. Imported, not re-declared.
from src.explain.report import (CRIMSON, CRIMSON_SOFT, GOLD, GOLD_SOFT, INK, LINE,
                                MARGIN, MUTED, PAGE_H, PAGE_W, TEAL, TEAL_SOFT, _para)
from src.common.config import DISCLAIMER

# Grade -> the band colour used for a point and a figure. Same three-colour vocabulary
# the screening report uses for its decision band, so the two documents read as one set.
_GRADE_COLOUR = {0: TEAL, 1: TEAL, 2: GOLD, 3: CRIMSON, 4: CRIMSON}
_GRADE_SOFT = {0: TEAL_SOFT, 1: TEAL_SOFT, 2: GOLD_SOFT, 3: CRIMSON_SOFT, 4: CRIMSON_SOFT}

_PRIORITY_COLOUR = {"routine": TEAL, "soon": GOLD, "prompt": CRIMSON, "urgent": CRIMSON}
_PRIORITY_SOFT = {"routine": TEAL_SOFT, "soon": GOLD_SOFT, "prompt": CRIMSON_SOFT,
                  "urgent": CRIMSON_SOFT}


def _short_date(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return "—"
    return dt.strftime("%d %b %Y")


def _grade_card(c, x, y, w, h, *, heading: str, grade, label, date, referable):
    """One side of the comparison. Previous on the left, current on the right."""
    g = int(grade) if grade is not None else None
    fg = _GRADE_COLOUR.get(g, MUTED)
    bg = _GRADE_SOFT.get(g, colors.HexColor("#EFEDEA"))
    c.setFillColor(bg); c.setStrokeColor(fg); c.setLineWidth(0.9)
    c.rect(x, y - h, w, h, fill=1, stroke=1)

    c.setFillColor(MUTED); c.setFont("Helvetica-Bold", 7)
    c.drawString(x + 5 * mm, y - 6 * mm, heading.upper())
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 26)
    c.drawString(x + 5 * mm, y - 17 * mm, "—" if g is None else str(g))
    c.setFont("Helvetica", 8.4); c.setFillColor(INK)
    c.drawString(x + 18 * mm, y - 17 * mm, str(label or "—"))
    c.setFont("Helvetica", 7.4); c.setFillColor(MUTED)
    c.drawString(x + 5 * mm, y - 23 * mm, _short_date(date))
    c.setFillColor(fg); c.setFont("Helvetica-Bold", 7)
    c.drawRightString(x + w - 5 * mm, y - 23 * mm,
                      "REFERRAL INDICATED" if referable else "NO REFERRAL INDICATED")


def _timeline(c, x, y, w, points):
    """The longitudinal ICDR Grade Timeline, drawn as a STEP line.

    A step, not a smooth curve, and that is a clinical statement rather than a style
    choice: the ICDR grade is an ordinal CATEGORY, so there is no defined value between
    two visits and drawing a slope would invent one. The line holds each grade until the
    next screening changes it.

    Ungradeable visits are drawn as hollow markers ON the axis floor and the step does
    not pass through them — an image that could not be graded has no grade to plot.
    """
    graded = [p for p in points if p.get("icdr_grade") is not None
              and p.get("gradeable") is not False]
    if not graded:
        return y

    rows = 4                                        # grades 0..4 inclusive
    plot_h = 26 * mm
    # Inset both ends: the first and last markers carry a label above and a date below,
    # and a point drawn on the frame edge clips both of them.
    left = x + 16 * mm                              # room for the y-axis labels
    right = x + w - 10 * mm
    span = max(1, len(points) - 1)

    def px(i):
        return left + (right - left) * (i / span) if span else (left + right) / 2

    def py(grade):
        return y - plot_h + (plot_h * (int(grade) / rows))

    # --- axis -----------------------------------------------------------------
    c.setStrokeColor(LINE); c.setLineWidth(0.5)
    for g in range(rows + 1):
        gy = py(g)
        c.setStrokeColor(colors.HexColor("#E6E3DF"))
        c.line(left, gy, right, gy)
        c.setFillColor(MUTED); c.setFont("Helvetica", 6.4)
        c.drawRightString(left - 2 * mm, gy - 1.6, f"G{g}")

    # --- the step line --------------------------------------------------------
    c.setStrokeColor(INK); c.setLineWidth(1.1)
    previous = None
    for i, p in enumerate(points):
        if p.get("icdr_grade") is None or p.get("gradeable") is False:
            continue
        cx, cy = px(i), py(p["icdr_grade"])
        if previous is not None:
            # horizontal hold, then the vertical category change
            c.line(previous[0], previous[1], cx, previous[1])
            c.line(cx, previous[1], cx, cy)
        previous = (cx, cy)

    # --- the points -----------------------------------------------------------
    for i, p in enumerate(points):
        cx = px(i)
        grade = p.get("icdr_grade")
        if grade is None or p.get("gradeable") is False:
            c.setStrokeColor(MUTED); c.setLineWidth(0.8); c.setFillColor(colors.white)
            c.circle(cx, py(0), 1.6 * mm, fill=1, stroke=1)
        else:
            c.setFillColor(_GRADE_COLOUR.get(int(grade), INK))
            c.circle(cx, py(grade), 1.7 * mm, fill=1, stroke=0)
            c.setFont("Helvetica-Bold", 6.2); c.setFillColor(INK)
            c.drawCentredString(cx, py(grade) + 3 * mm, f"G{grade}")
        c.setFont("Helvetica", 5.8); c.setFillColor(MUTED)
        c.drawCentredString(cx, y - plot_h - 4 * mm, _short_date(p.get("date")))

    return y - plot_h - 9 * mm


def build_comparison_report(comparison: dict, *, timeline: list[dict] | None = None,
                            follow_up: dict | None = None,
                            clinician_review: dict | None = None) -> bytes:
    """Render the comparison report. `comparison` is the object from comparison.py."""
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=A4)
    prev = comparison.get("previous") or {}
    curr = comparison.get("current") or {}
    c.setTitle(f"CareBridge Eye Health Passport — comparison {curr.get('screening_id', '')}")

    y = PAGE_H - MARGIN

    # ---------------------------------------------------------------- header
    c.setFont("Helvetica-Bold", 13); c.setFillColor(INK)
    c.drawString(MARGIN, y - 4, "CareBridge Eye Health Passport")
    c.setFont("Helvetica", 7.6); c.setFillColor(MUTED)
    c.drawRightString(PAGE_W - MARGIN, y - 4,
                      datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    y -= 12
    c.setFont("Helvetica", 7.4)
    c.drawString(MARGIN, y - 4,
                 f"Screening comparison   ·   Previous {prev.get('screening_id', '—')}"
                 f"   ·   Current {curr.get('screening_id', '—')}")
    y -= 8
    c.setStrokeColor(LINE); c.setLineWidth(0.7)
    c.line(MARGIN, y, PAGE_W - MARGIN, y)
    y -= 12

    # ------------------------------------------------------- the change band
    change = int(comparison.get("grade_change", 0))
    if change > 0:
        band_bg, band_fg = GOLD_SOFT, GOLD
    elif change < 0:
        band_bg, band_fg = TEAL_SOFT, TEAL
    else:
        band_bg, band_fg = colors.HexColor("#EFEDEA"), MUTED

    sentence = Paragraph(comparison.get("statement", ""), ParagraphStyle(
        "s", fontName="Helvetica", fontSize=8.2, leading=10.2, textColor=INK))
    sub_w = PAGE_W - 2 * MARGIN - 14 * mm - 40 * mm
    _, sub_h = sentence.wrap(sub_w, 40 * mm)
    band_h = max(18 * mm, 12 * mm + sub_h)

    c.setFillColor(band_bg); c.setStrokeColor(band_fg); c.setLineWidth(0.9)
    c.rect(MARGIN, y - band_h, PAGE_W - 2 * MARGIN, band_h, fill=1, stroke=1)
    c.setFillColor(band_fg); c.setFont("Helvetica-Bold", 13)
    c.drawString(MARGIN + 7 * mm, y - 7.5 * mm,
                 comparison.get("change_label", "").upper())
    sentence.drawOn(c, MARGIN + 7 * mm, y - 9.5 * mm - sub_h)
    # The arrow, as the requirement writes it: 1 -> 2, +1 category.
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 20)
    c.drawRightString(PAGE_W - MARGIN - 7 * mm, y - 10 * mm,
                      f"{comparison.get('previous_grade')} → {comparison.get('current_grade')}")
    c.setFont("Helvetica", 7.2); c.setFillColor(MUTED)
    c.drawRightString(PAGE_W - MARGIN - 7 * mm, y - 15 * mm,
                      f"{change:+d} ICDR {'category' if abs(change) == 1 else 'categories'}")
    y -= band_h + 9

    # ------------------------------------------------------- the two results
    c.setFont("Helvetica-Bold", 7.4); c.setFillColor(MUTED)
    c.drawString(MARGIN, y - 3, "SCREENING COMPARISON")
    y -= 7
    gap = 5 * mm
    card_w = (PAGE_W - 2 * MARGIN - gap) / 2
    card_h = 28 * mm
    _grade_card(c, MARGIN, y, card_w, card_h, heading="Previous",
                grade=prev.get("icdr_grade"), label=prev.get("severity_label"),
                date=prev.get("date"), referable=prev.get("referable"))
    _grade_card(c, MARGIN + card_w + gap, y, card_w, card_h, heading="Current",
                grade=curr.get("icdr_grade"), label=curr.get("severity_label"),
                date=curr.get("date"), referable=curr.get("referable"))
    y -= card_h + 9

    # ---------------------------------------------------------- the timeline
    if timeline and len([p for p in timeline if p.get("icdr_grade") is not None]) >= 2:
        c.setFont("Helvetica-Bold", 7.4); c.setFillColor(MUTED)
        c.drawString(MARGIN, y - 3, "ICDR GRADE TIMELINE")
        y -= 10
        y = _timeline(c, MARGIN, y, PAGE_W - 2 * MARGIN, timeline)
        c.setFont("Helvetica-Oblique", 6.4); c.setFillColor(MUTED)
        c.drawString(MARGIN, y,
                     "ICDR grade is an ordinal category, so the line holds each grade "
                     "until the next screening. A hollow marker is a visit whose "
                     "photograph could not be graded.")
        y -= 10

    # ------------------------------------------------------- what else moved
    rows = [["What was compared", "Previous", "Current"]]
    rows.append(["ICDR grade", str(prev.get("icdr_grade", "—")), str(curr.get("icdr_grade", "—"))])
    rows.append(["Severity", str(prev.get("severity_label") or "—"),
                 str(curr.get("severity_label") or "—")])
    rows.append(["Screening date", _short_date(prev.get("date")), _short_date(curr.get("date"))])
    rows.append(["Image quality", str(prev.get("quality_status") or "—"),
                 str(curr.get("quality_status") or "—")])
    rows.append(["Referral status",
                 "Referral indicated" if prev.get("referable") else "No referral indicated",
                 "Referral indicated" if curr.get("referable") else "No referral indicated"])
    rows.append(["Clinician review",
                 str(prev.get("clinician_review_status") or "pending"),
                 str(curr.get("clinician_review_status") or "pending")])
    interval = comparison.get("interval_days")
    rows.append(["Interval between screenings", "—",
                 "—" if interval is None else f"{interval} days"])

    t = Table(rows, colWidths=[62 * mm, 52 * mm, 52 * mm])
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 7.2),
        ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEDEA")),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    _, th = t.wrap(0, 0)
    t.drawOn(c, MARGIN, y - th)
    y -= th + 10

    # ---------------------------------------------------------- follow-up box
    if follow_up:
        window = follow_up.get("recommended_window") or {}
        priority = window.get("priority", "routine")
        fg = _PRIORITY_COLOUR.get(priority, MUTED)
        bg = _PRIORITY_SOFT.get(priority, colors.HexColor("#EFEDEA"))
        body = (f"<b>{window.get('headline', 'Suggested follow-up')}:</b> "
                f"{window.get('label', '—')}. {follow_up.get('reason', '')} "
                f"<font color='#6E757B'>{follow_up.get('basis_label', '')}.</font>")
        p = Paragraph(body, ParagraphStyle("f", fontName="Helvetica", fontSize=7.6,
                                           leading=9.6, textColor=INK))
        _, h = p.wrap(PAGE_W - 2 * MARGIN - 10 * mm, 60 * mm)
        box_h = h + 7 * mm
        c.setFillColor(bg); c.setStrokeColor(fg); c.setLineWidth(0.8)
        c.rect(MARGIN, y - box_h, PAGE_W - 2 * MARGIN, box_h, fill=1, stroke=1)
        p.drawOn(c, MARGIN + 5 * mm, y - box_h + 3.5 * mm)
        y -= box_h + 8

    # ------------------------------------------------------ clinician review
    if clinician_review and clinician_review.get("status", "pending") != "pending":
        c.setFont("Helvetica-Bold", 7); c.setFillColor(MUTED)
        c.drawString(MARGIN, y - 4, "CLINICIAN REVIEW")
        y -= 12
        grade = clinician_review.get("clinician_grade")
        line = (f"{clinician_review.get('status_label', clinician_review.get('status'))}"
                f"{f' · clinician grade {grade}' if grade is not None else ''}"
                f" · recorded {_short_date(clinician_review.get('reviewed_at'))}")
        rp = _para(line, size=7.4)
        _, rh = rp.wrap(PAGE_W - 2 * MARGIN, 20 * mm)
        rp.drawOn(c, MARGIN, y - rh)
        y -= rh + 8

    # ---------------------------------------------------------- the caveat
    caveat = Paragraph(comparison.get("disclaimer", ""), ParagraphStyle(
        "c", fontName="Helvetica-Oblique", fontSize=7.2, leading=9, textColor=MUTED))
    _, ch = caveat.wrap(PAGE_W - 2 * MARGIN, 40 * mm)
    caveat.drawOn(c, MARGIN, max(y - ch, MARGIN + 14 * mm))

    # ------------------------------------------------------------ disclaimer
    c.setFillColor(CRIMSON_SOFT)
    c.rect(MARGIN, MARGIN, PAGE_W - 2 * MARGIN, 9 * mm, fill=1, stroke=0)
    c.setFillColor(CRIMSON); c.setFont("Helvetica-Bold", 7.6)
    c.drawCentredString(PAGE_W / 2, MARGIN + 3.4 * mm, DISCLAIMER.upper())

    c.showPage()
    c.save()
    return buf.getvalue()


def build_comparison_report_b64(*args, **kwargs) -> str:
    return base64.b64encode(build_comparison_report(*args, **kwargs)).decode("ascii")


__all__ = ["build_comparison_report", "build_comparison_report_b64"]
