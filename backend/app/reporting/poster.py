"""Renders the consultation data dict (app/reporting/consultation.py) into a
single shareable poster PNG. Layout is modeled directly on President
University's real "Resume & LinkedIn Expo" poster template (see
`Example of Resume & Linkedin expo.jpeg` in the project root) -- an event
banner, a framed headshot next to name/role/program, a quote box, stat
cards, and bulleted strength/gap columns -- re-skinned with PresConsult AI's
actual brand (navy + red, matched to President University's PUIS portal and
crest; see frontend/src/index.css for the same tokens) and extended with a
competency radar chart (no student-photo pipeline exists yet, so the photo
frame falls back to a person-silhouette placeholder).

Uses Pillow directly rather than an HTML-to-image pipeline to avoid a heavy
extra dependency for a single static graphic. Font loading tries a short list
of common system TrueType paths and falls back to Pillow's built-in bitmap
font if none exist -- works out of the box, but renders best with a real
font available. Bundling an open-font asset is the natural follow-up if this
needs to run somewhere without any of these paths (e.g. a bare Linux
container).
"""

import io
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from app.config import UNIVERSITY_LOGO_PATH

WIDTH = 1080
# Content length varies with the LLM-generated narrative/roadmap text, so the
# canvas is drawn tall enough for the longest realistic poster and then
# cropped down to the footer's actual position -- fixing a bug where a fixed
# HEIGHT clipped the next-steps banner (and pushed the footer band over it)
# whenever narrative text ran long.
MAX_HEIGHT = 2400
BG = (248, 250, 252)  # --brand-bg equivalent (slate-50)
NAVY = (15, 23, 42)  # --brand-navy
NAVY_SOFT = (232, 238, 245)  # --brand-navy-soft
RED = (220, 38, 38)  # --brand-red
GREEN = (22, 163, 74)  # matched/positive
AMBER = (217, 119, 6)  # partial
TEXT = (30, 41, 59)
TEXT_MUTED = (100, 116, 139)
WHITE = (255, 255, 255)

_FONT_CANDIDATES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


# Single source of truth for which font keys exist and their (weight, size) --
# previously this list was enumerated twice (once paired with truthful()
# calls, once again as a bare tuple for the load_default() fallback), with
# nothing enforcing that adding/renaming a key updated both.
_FONT_SPECS: dict[str, tuple[str, int]] = {
    "event_title": ("bold", 40),
    "event_sub": ("regular", 22),
    "name": ("bold", 50),
    "tagline": ("bold", 26),
    "body": ("regular", 24),
    "quote": ("bold", 26),
    "score_label": ("bold", 20),
    "score_value": ("bold", 40),
    "small_label": ("bold", 16),
    "heading": ("bold", 28),
    "footer": ("regular", 20),
    "footer_bold": ("bold", 24),
}


@lru_cache(maxsize=1)
def _load_fonts() -> dict[str, ImageFont.FreeTypeFont]:
    for regular_path, bold_path in _FONT_CANDIDATES:
        try:
            paths = {"regular": regular_path, "bold": bold_path}
            return {key: ImageFont.truetype(paths[weight], size) for key, (weight, size) in _FONT_SPECS.items()}
        except OSError:
            continue
    default = ImageFont.load_default()
    return {key: default for key in _FONT_SPECS}


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int | None = None) -> list[str]:
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        # Signal the cut rather than just stopping mid-sentence -- append an
        # ellipsis to the last visible line, trimming a word if needed so it
        # still fits max_width instead of overflowing past it.
        last = lines[-1]
        while last and draw.textlength(f"{last}…", font=font) > max_width:
            last = last.rsplit(" ", 1)[0] if " " in last else ""
        lines[-1] = f"{last}…" if last else "…"

    return lines


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    return draw.textlength(text, font=font)


def _draw_person_silhouette(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, color) -> None:
    """Default avatar placeholder for when no student photo is on file --
    there's no photo-upload pipeline yet, so this is what every poster shows."""
    head_r = radius * 0.32
    head_cy = cy - radius * 0.28
    draw.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
        fill=color,
    )
    shoulder_w = radius * 1.15
    shoulder_top = cy + radius * 0.12
    # Pieslice angles are image-space (0deg=east, increasing clockwise, so
    # 90deg=south) -- 0 to 180 sweeps through south, i.e. the BOTTOM half of
    # the circle, which is the half a pair of shoulders below a head needs.
    draw.pieslice(
        [cx - shoulder_w, shoulder_top - shoulder_w, cx + shoulder_w, shoulder_top + shoulder_w],
        start=0,
        end=180,
        fill=color,
    )


def _draw_radar_chart(draw: ImageDraw.ImageDraw, cx: int, cy: int, radius: int, units: list, fonts) -> None:
    """Plots each required competency unit's coverage_fraction as one axis of
    a radar/spider chart -- a single glance at shape+size communicates the
    skill-gap profile far better than a flat matched/partial/missing bar."""
    n = len(units)
    if n < 3:
        return

    def vertex(frac: float, i: int) -> tuple[float, float]:
        # Image space is Y-down, so starting at -90deg (north/top) and
        # increasing the angle sweeps east-then-south, i.e. clockwise on
        # screen -- axes read clockwise starting from the top, as expected.
        angle = math.radians(-90 + i * (360 / n))
        return (cx + frac * radius * math.cos(angle), cy + frac * radius * math.sin(angle))

    grid_color = (221, 228, 238)
    for frac in (0.25, 0.5, 0.75, 1.0):
        draw.polygon([vertex(frac, i) for i in range(n)], outline=grid_color)
    for i in range(n):
        draw.line([(cx, cy), vertex(1.0, i)], fill=grid_color, width=1)

    # A 0% unit still gets a small visible nub instead of collapsing exactly
    # onto the center point, which would otherwise look like a missing axis.
    data_pts = [vertex(max(0.05, u.coverage_fraction), i) for i, u in enumerate(units)]
    tint = tuple(int(RED[j] * 0.14 + BG[j] * 0.86) for j in range(3))
    draw.polygon(data_pts, fill=tint)
    for i in range(n):
        draw.line([data_pts[i], data_pts[(i + 1) % n]], fill=RED, width=3)
    for x, y in data_pts:
        draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=RED)

    for i, u in enumerate(units):
        lx, ly = vertex(1.22, i)
        # unit_title is already English (translated once at analysis time in
        # gap_engine.py) -- unit_code alone ("K.62AIN00.010.2") means nothing
        # to a reader, so only fall back to it if a title is somehow missing.
        label = _wrap(draw, u.unit_title or u.unit_code, fonts["small_label"], 210, max_lines=1)[0]
        lw = _text_width(draw, label, fonts["small_label"])
        if lx > cx + 5:
            tx = lx
        elif lx < cx - 5:
            tx = lx - lw
        else:
            tx = lx - lw / 2
        draw.text((tx, ly - 8), label, font=fonts["small_label"], fill=TEXT_MUTED)


def _paste_logo_chip(img: Image.Image, x: int, y: int, size: int = 64) -> None:
    if not UNIVERSITY_LOGO_PATH.exists():
        return
    pad = 8
    chip = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size, size], radius=12, fill=255)
    logo = Image.open(UNIVERSITY_LOGO_PATH).convert("RGBA")
    logo.thumbnail((size - pad * 2, size - pad * 2))
    lx = (size - logo.width) // 2
    ly = (size - logo.height) // 2
    chip.paste(logo, (lx, ly), logo)
    img.paste(chip, (x, y), mask)


def render_consultation_poster(data: dict) -> bytes:
    student, job_role, academic = data["student"], data["job_role"], data["academic"]
    resume_result, narrative, consult = data["resume_result"], data["narrative"], data["consultation_narrative"]
    gap_result = data["gap_result"]
    match_pct = gap_result["match_percentage"]
    fonts = _load_fonts()

    img = Image.new("RGB", (WIDTH, MAX_HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    # --- Event header banner ----------------------------------------------
    header_x0, header_y0, header_x1 = 40, 36, WIDTH - 40
    header_h = 168
    header_y1 = header_y0 + header_h
    draw.rounded_rectangle([header_x0, header_y0, header_x1, header_y1], radius=32, fill=NAVY)

    logo_size = 108
    logo_x = header_x0 + 24
    logo_y = header_y0 + (header_h - logo_size) // 2
    _paste_logo_chip(img, logo_x, logo_y, size=logo_size)

    title_x = logo_x + logo_size + 28
    draw.text((title_x, header_y0 + 34), "RESUME & LINKEDIN EXPO", font=fonts["event_title"], fill=WHITE)
    draw.text(
        (title_x, header_y0 + 34 + 56),
        "President University · Powered by PresConsult AI",
        font=fonts["event_sub"],
        fill=(203, 213, 225),
    )

    # --- Photo frame + name/role block --------------------------------------
    row_y0 = header_y1 + 40
    photo_size = 260
    photo_x0, photo_y0 = 40, row_y0
    photo_x1, photo_y1 = photo_x0 + photo_size, photo_y0 + photo_size
    draw.rounded_rectangle([photo_x0, photo_y0, photo_x1, photo_y1], radius=20, outline=NAVY, width=5, fill=NAVY_SOFT)
    _draw_person_silhouette(draw, (photo_x0 + photo_x1) // 2, (photo_y0 + photo_y1) // 2, 78, NAVY)

    text_x = photo_x1 + 40
    text_w = WIDTH - 40 - text_x

    name_y = row_y0 + 6
    for line in _wrap(draw, student.full_name, fonts["name"], text_w, max_lines=1):
        draw.text((text_x, name_y), line, font=fonts["name"], fill=NAVY)

    tagline_y = name_y + 66
    tagline_lines = _wrap(draw, job_role.role_title.upper(), fonts["tagline"], text_w, max_lines=2)
    ty = tagline_y
    for line in tagline_lines:
        draw.text((text_x, ty), line, font=fonts["tagline"], fill=RED)
        ty += 34

    program_y = ty + 8
    draw.text((text_x, program_y), f"{student.program} · Batch {student.cohort_year}", font=fonts["body"], fill=TEXT_MUTED)
    gpa_y = program_y + 34
    if academic["gpa"] is not None:
        draw.text((text_x, gpa_y), f"GPA {academic['gpa']} / 4.00", font=fonts["body"], fill=TEXT_MUTED)
        gpa_y += 34

    y = max(photo_y1, gpa_y) + 36

    # --- Quote box -----------------------------------------------------------
    quote_text = (consult["coach_message"] if consult else "").strip() or "Keep building evidence for your target role."
    quote_lines = _wrap(draw, f'"{quote_text}"', fonts["quote"], WIDTH - 200, max_lines=4)
    box_height = 50 + 34 * len(quote_lines)
    draw.rounded_rectangle([70, y, WIDTH - 70, y + box_height], radius=16, fill=NAVY_SOFT)
    ty = y + 25
    for line in quote_lines:
        draw.text((100, ty), line, font=fonts["quote"], fill=NAVY)
        ty += 34
    y += box_height + 36

    # --- Stat cards: resume readiness / role match ----------------------------
    card_gap = 24
    card_w = (WIDTH - 80 - card_gap) // 2
    card_h = 120
    resume_score_text = f"{resume_result['overall_score']:.0f}/100" if resume_result else "N/A"
    cards = [
        ("RESUME READINESS", resume_score_text),
        ("ROLE MATCH", f"{match_pct:.0f}%"),
    ]
    for i, (label, value) in enumerate(cards):
        x0 = 40 + i * (card_w + card_gap)
        draw.rounded_rectangle([x0, y, x0 + card_w, y + card_h], radius=16, outline=NAVY, width=2)
        draw.text((x0 + 22, y + 18), label, font=fonts["score_label"], fill=NAVY)
        draw.text((x0 + 22, y + 52), value, font=fonts["score_value"], fill=NAVY)
    y += card_h + 44

    # --- Competency radar chart -----------------------------------------------
    all_units = (gap_result["matched_units"] + gap_result["partial_units"] + gap_result["missing_units"])[:8]
    matched_n = len(gap_result["matched_units"])
    partial_n = len(gap_result["partial_units"])
    missing_n = len(gap_result["missing_units"])

    draw.text((70, y), "COMPETENCY RADAR", font=fonts["heading"], fill=NAVY)
    y += 44

    if len(all_units) >= 3:
        radius = 130
        cx = WIDTH // 2
        # Axis labels sit at 1.22x the radius, so both the top gap (below the
        # heading) and bottom gap (above the caption) need buffer for that,
        # not just the bare radius.
        cy = y + radius * 1.32
        _draw_radar_chart(draw, cx, cy, radius, all_units, fonts)
        y = cy + radius * 1.32 + 10

        caption = f"{len(all_units)} competency units required for {job_role.role_title}"
        cap_w = _text_width(draw, caption, fonts["body"])
        draw.text((WIDTH / 2 - cap_w / 2, y), caption, font=fonts["body"], fill=TEXT_MUTED)
        y += 34
    else:
        note = "Not enough competency units on file yet to plot a radar chart."
        note_w = _text_width(draw, note, fonts["body"])
        draw.text((WIDTH / 2 - note_w / 2, y), note, font=fonts["body"], fill=TEXT_MUTED)
        y += 34

    legend = f"{matched_n} Matched   ·   {partial_n} Partial   ·   {missing_n} Missing competency units"
    legend_w = _text_width(draw, legend, fonts["small_label"])
    draw.text((WIDTH / 2 - legend_w / 2, y), legend, font=fonts["small_label"], fill=TEXT_MUTED)
    y += 46

    # --- Strengths / gaps: one "at a glance" card, two columns -----------------
    strengths = [p["text"] for p in (narrative or {}).get("strengths", [])][:3]
    gaps = [p["text"] for p in (narrative or {}).get("weaknesses", [])][:3]
    if not gaps:
        gaps = [u.unit_title or u.unit_code for u in gap_result["missing_units"]][:3]

    card_x0, card_x1 = 40, WIDTH - 40
    card_pad = 30
    col_w = (card_x1 - card_x0 - 2 * card_pad - 30) // 2
    left_x = card_x0 + card_pad
    right_x = left_x + col_w + 30
    bullet_r = 5

    def _wrapped_items(items: list[str]) -> list[list[str]]:
        return [_wrap(draw, text, fonts["body"], col_w - 26, max_lines=2) for text in items]

    strength_lines = _wrapped_items(strengths)
    gap_lines = _wrapped_items(gaps)
    col_height = lambda items: sum(30 * len(lines) + 6 for lines in items)  # noqa: E731

    heading_y = y + 26
    body_top = heading_y + 44
    card_y0 = y
    card_y1 = body_top + max(col_height(strength_lines), col_height(gap_lines)) + card_pad
    draw.rounded_rectangle([card_x0, card_y0, card_x1, card_y1], radius=20, outline=NAVY_SOFT, width=2, fill=(252, 253, 254))

    draw.text((left_x, heading_y), "YOUR STRENGTHS", font=fonts["heading"], fill=GREEN)
    draw.text((right_x, heading_y), "PRIORITY GAPS", font=fonts["heading"], fill=RED)

    def _draw_column(x: int, items: list[list[str]], color) -> None:
        cy = body_top
        for lines in items:
            draw.ellipse([x, cy + 10, x + bullet_r * 2, cy + 10 + bullet_r * 2], fill=color)
            for line in lines:
                draw.text((x + 26, cy), line, font=fonts["body"], fill=TEXT)
                cy += 30
            cy += 6

    _draw_column(left_x, strength_lines, GREEN)
    _draw_column(right_x, gap_lines, RED)

    y = card_y1 + 30

    # --- Next steps banner -----------------------------------------------------
    next_steps = consult["career_roadmap"][0]["actions"] if consult and consult["career_roadmap"] else "Run a skill-gap analysis to get a personalized roadmap."
    banner_lines = _wrap(draw, next_steps, fonts["body"], WIDTH - 200, max_lines=3)
    banner_height = 60 + 32 * len(banner_lines)
    draw.rounded_rectangle([40, y, WIDTH - 40, y + banner_height], radius=20, fill=NAVY)
    draw.text((70, y + 20), "NEXT STEPS", font=fonts["heading"], fill=WHITE)
    ty = y + 60
    for line in banner_lines:
        draw.text((70, ty), line, font=fonts["body"], fill=(226, 232, 240))
        ty += 32

    # --- Footer ------------------------------------------------------------
    footer_h = 84
    footer_y = int(ty + 30)
    height = footer_y + footer_h
    draw.rectangle([0, footer_y, WIDTH, height], fill=NAVY)
    draw.text((40, footer_y + 16), "Powered by PresConsult AI", font=fonts["footer_bold"], fill=WHITE)
    draw.text((40, footer_y + 48), "President University · AI Career Consultation", font=fonts["footer"], fill=(203, 213, 225))
    _paste_logo_chip(img, WIDTH - 96, footer_y + 12, size=56)

    img = img.crop((0, 0, WIDTH, height))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
