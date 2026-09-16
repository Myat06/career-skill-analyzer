"""Renders the consultation data dict (app/reporting/consultation.py) into a
PDF report matching a reference editorial document design the user provided
(a cream/ink typographic layout in IBM Plex Sans/Mono, thin rule dividers,
inline progress bars, and flat color pills for status/confidence -- no navy
corporate header, no charts, no avatar) -- see the design brief this was
built from: a Claude Design canvas titled "Consultation Report" mimicking
President University's real Resume & LinkedIn Expo report template. The
reference design carried no logo at all; the PU crest is added into the
running footer on every page per the user's explicit ask, alongside the
PresConsult AI attribution that replaces the original template's own brand.

Nine numbered sections, same order as the reference minus the removed Career
Readiness Evaluation section (an uncalibrated, unreliable blended score over
fixture data -- see app/scoring/scoring_utils.py's docstring): Executive
Summary, Student Profile, Resume Readiness Evaluation, Skill Gap Analysis,
Recommended Resume Improvements, Career Roadmap, Recommended Career
Direction, Compass Coach Message, Evidence & Confidence.

Uses reportlab's Platypus API with bundled IBM Plex Sans/Mono TTFs (SIL Open
Font License, in ./fonts) instead of built-in Helvetica -- the reference
design's typography (tracked mono eyebrow labels, a serif-adjacent sans for
body text) is load-bearing for how "editorial" it reads, not a cosmetic
choice on top of a generic report.
"""

import io
from datetime import date
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.config import UNIVERSITY_LOGO_PATH
from app.scoring.resume_score import SUGGESTION_SCORE_THRESHOLD

# Every "unavailable" message below distinguishes a genuine absence ("nothing
# to report") from a generation failure ("the AI didn't answer"). They used to
# share one wording, so a student whose resume scored well and a student whose
# rubric grading silently failed read the identical sentence -- and neither
# could tell whether re-generating the report would change anything.
_RETRY_HINT = "Re-generating this report will retry it."

FONTS_DIR = Path(__file__).parent / "fonts"
registerFont(TTFont("PlexSans", str(FONTS_DIR / "IBMPlexSans-Regular.ttf")))
registerFont(TTFont("PlexSans-Medium", str(FONTS_DIR / "IBMPlexSans-Medium.ttf")))
registerFont(TTFont("PlexSans-SemiBold", str(FONTS_DIR / "IBMPlexSans-SemiBold.ttf")))
registerFont(TTFont("PlexMono", str(FONTS_DIR / "IBMPlexMono-Regular.ttf")))
registerFont(TTFont("PlexMono-Medium", str(FONTS_DIR / "IBMPlexMono-Medium.ttf")))

INK = "#1b1a18"
BODY_TEXT = "#33312e"
MUTED = "#5f5a52"
LABEL = "#8a857c"
BORDER = "#ded9d0"
ROW_BORDER = "#ebe7df"
TRACK_BG = "#e8e4dc"
HIGHLIGHT_BG = "#f3f1ec"
PAGE_BG = "#fdfcfa"
TEAL = "#00848b"  # oklch(0.55 0.11 200) from the reference design
AMBER = "#a4802b"  # oklch(0.62 0.11 85)
RUST = "#ae5528"  # oklch(0.55 0.13 45)

_BAND_COLOR = {"High": TEAL, "Moderate": AMBER, "Limited evidence": RUST}
_STATUS_STYLE = {
    "matched": (TEAL, "#fdfcfa"),
    "partial": (AMBER, INK),
    "missing": (RUST, "#fdfcfa"),
}

MARGIN = 0.7 * 72  # 0.7in in points, matching the reference's doc-page margin
CHROME_BAND = 0.32 * 72  # extra space reserved above/below MARGIN for the running header/footer

_styles = getSampleStyleSheet()
_EYEBROW = ParagraphStyle(
    "Eyebrow", fontName="PlexMono", fontSize=9, textColor=colors.HexColor(LABEL), leading=11
)
_TITLE = ParagraphStyle(
    "Title", fontName="PlexSans-SemiBold", fontSize=25, textColor=colors.HexColor(INK), leading=28, spaceAfter=2
)
_NAME = ParagraphStyle("Name", fontName="PlexSans-SemiBold", fontSize=15, textColor=colors.HexColor(INK), leading=18)
_INFO = ParagraphStyle("Info", fontName="PlexSans", fontSize=10, textColor=colors.HexColor(MUTED), leading=16)
_H2 = ParagraphStyle(
    "H2", fontName="PlexSans-SemiBold", fontSize=12.5, textColor=colors.HexColor(INK), spaceBefore=16, spaceAfter=7
)
_SUBLABEL = ParagraphStyle(
    "Sublabel", fontName="PlexMono", fontSize=8.5, textColor=colors.HexColor(LABEL), spaceBefore=4, spaceAfter=6
)
_BODY = ParagraphStyle("Body", fontName="PlexSans", fontSize=10, textColor=colors.HexColor(BODY_TEXT), leading=15)
_BODY_MUTED = ParagraphStyle("BodyMuted", fontName="PlexSans", fontSize=9.5, textColor=colors.HexColor(MUTED), leading=14)
_CELL = ParagraphStyle("Cell", fontName="PlexSans", fontSize=9.5, textColor=colors.HexColor(BODY_TEXT), leading=14)
_CELL_LABEL = ParagraphStyle("CellLabel", fontName="PlexSans-Medium", fontSize=9.5, textColor=colors.HexColor(INK), leading=14)
_CELL_MUTED = ParagraphStyle("CellMuted", fontName="PlexSans", fontSize=9.5, textColor=colors.HexColor(MUTED), leading=14)
_MONO_SCORE = ParagraphStyle("MonoScore", fontName="PlexMono", fontSize=9.5, textColor=colors.HexColor(INK), leading=13)
_QUOTE_TEXT = ParagraphStyle("QuoteText", fontName="PlexSans", fontSize=10, textColor=colors.HexColor(BODY_TEXT), leading=16)
_TIMEFRAME = ParagraphStyle("Timeframe", fontName="PlexMono-Medium", fontSize=9.5, textColor=colors.HexColor(INK))

TABLE_HEADER_STYLE = [
    ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.HexColor(INK)),
    ("LINEBELOW", (0, 1), (-1, -2), 0.5, colors.HexColor(ROW_BORDER)),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ("TOPPADDING", (0, 0), (-1, 0), 0),
    ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
    ("TOPPADDING", (0, 1), (-1, -1), 9),
    ("BOTTOMPADDING", (0, 1), (-1, -1), 9),
]


def _track(text: str) -> str:
    """Approximates CSS letter-spacing/tracking for short all-caps mono
    labels -- reportlab's Paragraph markup has no letter-spacing attribute,
    but the reference design's tracked-caps eyebrow labels are a defining
    part of its look, not a detail worth losing. Plain ASCII spaces don't
    work here: reportlab's Paragraph parser follows XML whitespace rules and
    collapses any run of them to one, so a naive letter-gap/word-gap split
    (e.g. one space between letters, three between words) still renders as
    one indistinguishable run -- "MATCHING EVIDENCE" reads as an unbroken
    blob of letters with no visible word break. Unicode space characters
    (thin space, non-breaking space) fall outside that ASCII whitespace
    class and survive uncollapsed in both Paragraph text and
    canvas.drawString."""
    return "  ".join(" ".join(word) for word in text.split(" "))


def _p(text: str, style=_BODY) -> Paragraph:
    return Paragraph(text, style)


def _bar(fraction: float, color_hex: str, width_mm: float = 42, height_mm: float = 2.3) -> Drawing:
    width, height = width_mm * mm, height_mm * mm
    d = Drawing(width, height)
    d.add(Rect(0, 0, width, height, fillColor=colors.HexColor(TRACK_BG), strokeColor=None))
    filled = max(0.0, min(1.0, fraction)) * width
    if filled > 0:
        d.add(Rect(0, 0, filled, height, fillColor=colors.HexColor(color_hex), strokeColor=None))
    return d


def _icon_label_row(icon, label, icon_col_width_mm: float, zero_pad_second_cell: bool = False) -> Table:
    """A two-cell icon + label row: small graphic on the left, a Paragraph on
    the right, vertically centered with no padding around either -- shared by
    every "icon beside a line of text" row (a bar + score, dots + a confidence
    level, ...) that would otherwise each set up the identical TableStyle."""
    style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]
    if zero_pad_second_cell:
        style.append(("RIGHTPADDING", (1, 0), (1, 0), 0))
    t = Table([[icon, label]], colWidths=[icon_col_width_mm * mm, None])
    t.setStyle(TableStyle(style))
    return t


def _bar_row(fraction: float, color_hex: str, score_text: str, width_mm: float = 42) -> Table:
    """Bar + mono score side by side, matching the reference's inline
    `<div style="display:flex">` progress rows."""
    return _icon_label_row(
        _bar(fraction, color_hex, width_mm), _p(score_text, _MONO_SCORE), width_mm, zero_pad_second_cell=True
    )


def _pill(text: str, bg_hex: str, fg_hex: str) -> Table:
    t = Table([[_p(text, ParagraphStyle("pill", fontName="PlexSans-Medium", fontSize=8.5, textColor=colors.HexColor(fg_hex)))]])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(bg_hex)),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return t


def _quote_box(text: str) -> Table:
    """A Table-wrapped Paragraph, not a Paragraph with backColor/borderPadding
    directly -- reportlab's automatic flowable-height calculation doesn't
    reliably reserve room for a Paragraph's own borderPadding, so the
    highlighted background bleeds upward and overlaps whatever precedes it
    (here, the section heading right above it). A Table cell's background
    and padding are properly accounted for in layout."""
    t = Table([[_p(text, _QUOTE_TEXT)]], colWidths=[174 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(HIGHLIGHT_BG)),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
                ("TOPPADDING", (0, 0), (-1, -1), 14),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return t


def _confidence_dots(level: str, dot_mm: float = 5.4, gap_mm: float = 1.2) -> Drawing:
    color_hex = _BAND_COLOR.get(level, MUTED)
    filled = {"High": 3, "Moderate": 2, "Limited evidence": 1}.get(level, 0)
    width = dot_mm * 3 * mm + gap_mm * 2 * mm
    d = Drawing(width, dot_mm * mm)
    for i in range(3):
        x = i * (dot_mm + gap_mm) * mm
        fill = colors.HexColor(color_hex) if i < filled else colors.HexColor(TRACK_BG)
        d.add(Rect(x, 0, dot_mm * mm, dot_mm * mm * 0.32, fillColor=fill, strokeColor=None))
    return d


def _confidence_row(level: str) -> Table:
    return _icon_label_row(_confidence_dots(level), _p(level, _CELL), 24)


def _draw_chrome(canvas, doc, show_logo: bool = False) -> None:
    """Running header/footer on every page: a page-wide cream background and
    a thin rule top and bottom with small tracked mono labels. The PU crest
    only appears in the header of the FIRST page (show_logo) -- repeating it
    in the running header of every single page reads as branding overload for
    what's otherwise a clean, minimal document; once at the top is enough.
    """
    canvas.saveState()
    page_w, page_h = A4
    canvas.setFillColor(colors.HexColor(PAGE_BG))
    canvas.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    canvas.setFont("PlexMono", 8)
    canvas.setFillColor(colors.HexColor(LABEL))
    canvas.setStrokeColor(colors.HexColor(BORDER))
    canvas.setLineWidth(0.6)

    header_rule_y = page_h - MARGIN + CHROME_BAND * 0.4
    canvas.line(MARGIN, header_rule_y, page_w - MARGIN, header_rule_y)
    canvas.drawString(MARGIN, header_rule_y + 6, _track("AI CAREER CONSULTATION"))
    if show_logo and UNIVERSITY_LOGO_PATH.exists():
        # Big enough to actually register as a logo at a glance, not just a
        # faint mark in the corner -- 20pt (~7mm) was easy to miss entirely.
        # The whole top margin band above the rule is only ~41pt tall
        # (MARGIN - CHROME_BAND*0.4), so the logo has to fit inside that
        # without extending past the physical page top edge. The crest
        # already reads "President University" at this size, so it replaces
        # the separate text label rather than sitting redundantly beside it.
        logo_size = 26
        canvas.drawImage(
            str(UNIVERSITY_LOGO_PATH),
            page_w - MARGIN - logo_size,
            header_rule_y + 4,
            width=logo_size,
            height=logo_size,
            preserveAspectRatio=True,
            mask="auto",
        )
    else:
        canvas.drawRightString(page_w - MARGIN, header_rule_y + 6, _track("PRESIDENT UNIVERSITY"))

    footer_rule_y = MARGIN - CHROME_BAND * 0.4
    canvas.line(MARGIN, footer_rule_y, page_w - MARGIN, footer_rule_y)
    canvas.drawString(MARGIN, footer_rule_y - 14, _track("POWERED BY PRESCONSULT AI"))
    date_text = _track(date.today().strftime("%d %b %Y").upper())
    canvas.drawRightString(page_w - MARGIN, footer_rule_y - 14, date_text)

    canvas.restoreState()


def _title_block(data: dict) -> list:
    student, job_role = data["student"], data["job_role"]
    resume_overall = data["resume_result"]["overall_score"] if data["resume_result"] else None

    flow: list = [
        _p(_track("AI CAREER PORTFOLIO"), _EYEBROW),
        _p("Consultation Report", _TITLE),
        Spacer(1, 14),
    ]

    info_lines = f"Student ID: {student.student_no}<br/>{student.program} — Cohort {student.cohort_year}<br/>"
    info_lines += f"Target Role: <font color=\"{INK}\">{job_role.role_title}</font>"
    left_cell = [_p(student.full_name, _NAME), Spacer(1, 6), _p(info_lines, _INFO)]

    resume_label_row = Table(
        [[_p("Resume Readiness", _CELL_LABEL), ""]], colWidths=[None, 20 * mm], style=[("ALIGN", (1, 0), (1, 0), "RIGHT")]
    )
    resume_bar = _bar_row(
        (resume_overall or 0) / 100, TEAL, f"{resume_overall:.0f}<font color=\"{LABEL}\">/100</font>" if resume_overall is not None else "N/A"
    )

    right_cell = [resume_label_row, Spacer(1, 3), resume_bar]

    header_table = Table([[left_cell, right_cell]], colWidths=[95 * mm, 79 * mm])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 16),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 16),
                ("LINEBELOW", (0, 0), (-1, -1), 1.6, colors.HexColor(INK)),
            ]
        )
    )
    flow.append(header_table)
    flow.append(Spacer(1, 6))
    return flow


def _executive_summary_section(data: dict) -> list:
    consult = data["consultation_narrative"]
    # Truthiness, not just presence: partial salvage in narrative_prompts.py
    # can now return a dict where one section came back empty but the others
    # are good, so each section checks its own field rather than assuming that
    # a non-None consult means every field is populated.
    text = (consult or {}).get("executive_summary") or (
        f"The AI summary was not generated for this report -- the scores and tables below are "
        f"deterministic and unaffected. {_RETRY_HINT}"
    )
    return [_p("1. Executive Summary", _H2), _p(text, _BODY)]


def _profile_section(data: dict) -> list:
    student, academic = data["student"], data["academic"]
    rows = [
        ("Student ID", student.student_no),
        ("Name", student.full_name),
        ("Email", student.email),
        ("Program / Cohort", f"{student.program} / {student.cohort_year}"),
        ("GPA", str(academic["gpa"]) if academic["gpa"] is not None else "Not yet available"),
        ("Courses Completed", f"{academic['completed_courses']} / {academic['total_catalog_courses']}"),
        ("Logged Activities", str(academic["activity_count"])),
    ]
    table = Table(
        [[_p(k, _CELL_MUTED), _p(v, _CELL)] for k, v in rows],
        colWidths=[62 * mm, 112 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor(ROW_BORDER)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [_p("2. Student Profile", _H2), table]


def _resume_section(data: dict) -> list:
    resume_result = data["resume_result"]
    flow = [_p("3. Resume Readiness Evaluation", _H2)]
    if resume_result is None:
        flow.append(_p("No resume on file for this student.", _BODY))
        return flow

    categories = resume_result["rubric_categories"]
    if not categories:
        # A resume scored before this rubric ran to completion (e.g. a chat hiccup
        # during the initial provisional scoring pass) can carry an overall_score
        # with zero rubric_categories -- a header row with no data rows under it
        # would look broken, so show a plain note instead of an empty table.
        flow.append(
            _p(
                f'Resume Readiness Score: <font color="{INK}">{resume_result["overall_score"]:.0f}/100</font> '
                "(provisional -- a detailed per-category breakdown is not available for this score).",
                _BODY_MUTED,
            )
        )
        return flow

    flow.append(
        _p(
            f'Resume Readiness Score: <font color="{INK}">{resume_result["overall_score"]:.0f}/100</font> '
            f"&mdash; {len(categories)} assessment areas, each scored out of 100.",
            _BODY_MUTED,
        )
    )
    flow.append(Spacer(1, 8))

    header = [_p("Assessment Area", _SUBLABEL), _p("Score", _SUBLABEL), _p("Feedback", _SUBLABEL)]
    rows = [header]
    for c in categories:
        rows.append([_p(c["label"], _CELL_LABEL), _bar_row(c["score"] / 100, TEAL if c["score"] >= 70 else (AMBER if c["score"] >= 40 else RUST), f"{c['score']:.0f}", width_mm=22), _p(c["feedback"], _CELL)])
    table = Table(rows, colWidths=[38 * mm, 34 * mm, 102 * mm])
    table.setStyle(TableStyle(TABLE_HEADER_STYLE))
    flow.append(table)
    flow.append(Spacer(1, 6))
    flow.append(_p(f"Keyword alignment against target role: {resume_result['keyword_alignment_score']:.0f}/100", _BODY_MUTED))
    return flow


def _skill_gap_section(data: dict) -> list:
    gap_result, narrative = data["gap_result"], data["narrative"]
    all_units = gap_result["matched_units"] + gap_result["partial_units"] + gap_result["missing_units"]
    flow = [_p("4. Skill Gap Analysis", _H2)]
    flow.append(_p(f'Skill match against target role: <font color="{INK}">{gap_result["match_percentage"]:.0f}%</font>.', _BODY))
    flow.append(Spacer(1, 8))
    if not all_units:
        flow.append(_p("No competency units evaluated yet.", _BODY))
        return flow

    header = [_p("Competency Unit", _SUBLABEL), _p("Coverage", _SUBLABEL), _p("Status", _SUBLABEL)]
    rows = [header]
    for u in all_units:
        bg, fg = _STATUS_STYLE.get(u.status, (MUTED, "#fdfcfa"))
        rows.append(
            [
                _p(u.unit_title or u.unit_code, _CELL),
                _bar_row(u.coverage_fraction, bg, f"{u.coverage_fraction:.0%}", width_mm=22),
                _pill(u.status.title(), bg, fg),
            ]
        )
    table = Table(rows, colWidths=[96 * mm, 40 * mm, 38 * mm])
    table.setStyle(TableStyle(TABLE_HEADER_STYLE))
    flow.append(table)

    strengths = (narrative or {}).get("strengths", [])
    if strengths:
        flow.append(Spacer(1, 8))
        flow.append(_p(_track("MATCHING EVIDENCE"), _SUBLABEL))
        for point in strengths:
            flow.append(_p(f"&bull; {point['text']}", _BODY))
    return flow


def _resume_improvements_section(data: dict) -> list:
    resume_result = data["resume_result"]
    flow = [_p("5. Recommended Resume Improvements", _H2)]
    # Every other section in this report shows a fallback message rather than
    # disappearing when its data is missing (a resume that wasn't uploaded, a
    # skill-gap analysis that hasn't run) -- vanishing here instead would silently
    # skip a number in an explicitly numbered document, which reads as broken.
    if not resume_result:
        flow.append(
            _p("No resume on file -- upload one to receive targeted improvement suggestions here.", _BODY)
        )
        return flow
    if not resume_result.get("rubric_categories"):
        # Suggestions are derived from rubric categories scoring below the
        # threshold, so no categories means no suggestions -- which is a
        # grading failure, not a clean resume, and must not read like one.
        flow.append(
            _p(f"The AI rubric grading did not complete for this report, so no improvement "
               f"suggestions could be generated. {_RETRY_HINT}", _BODY)
        )
        return flow
    if not resume_result["suggestions"]:
        # Suggestions only exist for categories below the threshold, so a
        # uniformly strong resume produced a blank section -- unhelpful in a
        # consultation report a student is meant to act on. Name the weakest
        # categories instead. Their rubric feedback is praise, not advice, so
        # it is deliberately not reprinted here as though it were guidance.
        weakest = sorted(resume_result["rubric_categories"], key=lambda c: c["score"])[:3]
        flow.append(
            _p(f"No priority fixes -- every graded rubric category scored "
               f"{SUGGESTION_SCORE_THRESHOLD} or above. The categories with the most room "
               f"left to gain are listed below.", _BODY)
        )
        flow.append(_p(_track("CLOSEST TO NEEDING ATTENTION"), _SUBLABEL))
        for c in weakest:
            flow.append(_p(f"&bull; {c['label']} -- scored {c['score']:.0f}/100", _BODY))
        return flow
    flow.append(_p(_track("PRIORITY EDITING ACTIONS"), _SUBLABEL))
    for s in resume_result["suggestions"]:
        flow.append(_p(f"&bull; {s['text']}", _BODY))
    return flow


def _roadmap_section(data: dict) -> list:
    consult = data["consultation_narrative"]
    flow = [_p("6. Career Roadmap", _H2)]
    if not consult:
        flow.append(
            _p(f"The AI advisory sections could not be generated for this report -- the local model "
               f"was unreachable or returned an unusable response. Every score and table in this "
               f"report is deterministic and unaffected. {_RETRY_HINT}", _BODY)
        )
        return flow
    if not consult["career_roadmap"]:
        flow.append(
            _p(f"The roadmap section did not come back in a usable form for this report, though the "
               f"other advisory sections did. {_RETRY_HINT}", _BODY)
        )
        return flow
    rows = [[_p(r["timeframe"], _TIMEFRAME), _p(r["actions"], _BODY)] for r in consult["career_roadmap"]]
    table = Table(rows, colWidths=[32 * mm, 142 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, 0), (-1, -1), 0.5, colors.HexColor(ROW_BORDER)),
                ("LINEABOVE", (0, 0), (-1, 0), 1.2, colors.HexColor(INK)),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.HexColor(ROW_BORDER)),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    flow.append(table)
    return flow


def _direction_section(data: dict) -> list:
    consult = data["consultation_narrative"]
    return [
        _p("7. Recommended Career Direction", _H2),
        _p(
            (consult or {}).get("recommended_direction")
            or f"This section was not generated for this report. {_RETRY_HINT}",
            _BODY,
        ),
    ]


def _coach_message_section(data: dict) -> list:
    consult = data["consultation_narrative"]
    return [
        _p("8. Compass Coach Message", _H2),
        _quote_box(
            (consult or {}).get("coach_message")
            or f"This section was not generated for this report. {_RETRY_HINT}"
        ),
    ]


def _confidence_section(data: dict) -> list:
    rows = [[_p(category, _CELL), _confidence_row(level)] for category, level in data["confidence"].items()]
    table = Table(rows, colWidths=[115 * mm, 59 * mm])
    table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor(ROW_BORDER)),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [_p("9. Evidence and Confidence", _H2), table]


def render_consultation_pdf(data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=MARGIN + CHROME_BAND,
        bottomMargin=MARGIN + CHROME_BAND,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
    )

    flow: list = []
    flow += _title_block(data)
    flow += _executive_summary_section(data)
    flow += _profile_section(data)
    flow += _resume_section(data)
    flow += _skill_gap_section(data)
    flow += _resume_improvements_section(data)
    flow += _roadmap_section(data)
    flow += _direction_section(data)
    flow += _coach_message_section(data)
    flow += _confidence_section(data)

    doc.build(
        flow,
        onFirstPage=lambda c, d: _draw_chrome(c, d, show_logo=True),
        onLaterPages=lambda c, d: _draw_chrome(c, d, show_logo=False),
    )
    return buffer.getvalue()
