"""
Generates Operator_UI_Audit.pdf — the operator interface audit with real
screenshots, annotated (arrows + text burned into the image, not overlay
divs), severity ratings, and the punch list. Plain language throughout.

Reuses the screenshots saved under the session scratchpad during the audit.
If those are gone, re-run the audit walkthrough first.

Run: python scripts/build_ui_audit_pdf.py
"""

import os

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

IMG_DIR = r"C:\Users\Dyudhi T G\AppData\Local\Temp\claude\C--Users-Dyudhi-T-G-Desktop-champion-champbot-Social-Bot-LinkedIn-\02a1ad2e-c29f-4b38-ba79-eb16f82a2438\scratchpad\imgs"
ANNOT_DIR = os.path.join(IMG_DIR, "annotated")
os.makedirs(ANNOT_DIR, exist_ok=True)

OUT_PATH = "Operator_UI_Audit.pdf"

NAVY = (47, 59, 82)
ACCENT = (200, 90, 36)
WHITE = (255, 255, 255)
LINE_C = colors.HexColor("#bbbbbb")
STRIPE = colors.HexColor("#f4f6f8")
MUTED = colors.HexColor("#666666")

_FONT_CACHE = {}


def bold_font(size):
    size = max(10, int(size))
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", size)
    return _FONT_CACHE[size]


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def annotate(src_name, callouts, out_name):
    """callouts: list of (box_x_pct, box_y_pct, target_x_pct, target_y_pct, text)"""
    img = Image.open(os.path.join(IMG_DIR, src_name)).convert("RGB")
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    scale = w / 1568.0  # tune everything relative to a 1568px-wide baseline
    font = bold_font(22 * scale)

    for bx, by, tx, ty, text in callouts:
        box_x, box_y = bx / 100 * w, by / 100 * h
        tgt_x, tgt_y = tx / 100 * w, ty / 100 * h
        max_w = 300 * scale
        lines = wrap_text(draw, text, font, max_w - 24 * scale)
        ascent, descent = font.getmetrics()
        line_h = (ascent + descent) * 1.25
        box_h = len(lines) * line_h + 20 * scale
        box_w = max(draw.textlength(l, font=font) for l in lines) + 24 * scale

        # connector line + target dot
        draw.line([(box_x, box_y + box_h / 2), (tgt_x, tgt_y)], fill=ACCENT + (255,), width=max(2, int(3 * scale)))
        r = 6 * scale
        draw.ellipse([tgt_x - r, tgt_y - r, tgt_x + r, tgt_y + r], fill=ACCENT + (255,), outline=WHITE + (255,), width=max(1, int(2 * scale)))

        # callout box
        draw.rounded_rectangle(
            [box_x, box_y, box_x + box_w, box_y + box_h],
            radius=8 * scale, fill=NAVY + (235,), outline=ACCENT + (255,), width=max(1, int(2 * scale)),
        )
        ty_cursor = box_y + 10 * scale
        for line in lines:
            draw.text((box_x + 12 * scale, ty_cursor), line, font=font, fill=WHITE + (255,))
            ty_cursor += line_h

    out_path = os.path.join(ANNOT_DIR, out_name)
    img.save(out_path, quality=88)
    return out_path


# ------------------------------------------------------------- Annotate ---
shots = {}

shots["approvals_error"] = annotate(
    "screenshot-1787746791620-6.jpg",
    [
        (2, 30, 15, 21, "Names 'connect' — nobody clicked connect"),
        (44, 30, 55, 21, "But the account IS in the commenting stage"),
    ],
    "approvals_error.jpg",
)

shots["repetition"] = annotate(
    "screenshot-1787746957787-9.jpg",
    [
        (30, 40, 33, 22, "Card 1 and card 2 below — same four clauses, only the name changes"),
    ],
    "repetition.jpg",
)

shots["never_contact"] = annotate(
    "mobile_approvals_buttons.png",
    [
        (10, 60, 34, 60, "Permanent suppression, zero confirmation, one thumb-width from Skip"),
    ],
    "never_contact.jpg",
)

shots["warmup_activity"] = annotate(
    "screenshot-1787747445315-23.jpg",
    [
        (2, 10, 15, 4, "Reads as a done-things log"),
        (36, 46, 40, 30, "10 connects, 8 messages — real total sent today: 0"),
    ],
    "warmup_activity.jpg",
)

shots["agents_blank"] = annotate(
    "screenshot-1787747595952-34.jpg",
    [
        (28, 62, 50, 40, "5 stat cards + 5 agent cards exist right here — stuck invisible"),
    ],
    "agents_blank.jpg",
)

shots["campaigns_seam"] = annotate(
    "screenshot-1787747610323-35.jpg",
    [
        (28, 8, 50, 10, "The seam — dark product above, a different app below"),
    ],
    "campaigns_seam.jpg",
)

shots["accounts_devtools"] = annotate(
    "screenshot-1787747538625-32.jpg",
    [
        (14, 44, 30, 56, "Step 2, for every operator: open DevTools"),
    ],
    "accounts_devtools.jpg",
)

shots["targeting"] = annotate(
    "screenshot-1787747456512-25.jpg",
    [
        (4, 44, 20, 40, "24 people live behind this card — zero of them visible here"),
    ],
    "targeting.jpg",
)

shots["mobile_dashboard"] = annotate(
    "mobile_dashboard.png",
    [
        (46, 4, 92, 3, "6th nav item, off-screen — no label to hint what's hidden"),
        (8, 76, 12, 82, "Account name: gone. Only 'outreach' survives"),
    ],
    "mobile_dashboard.jpg",
)


def img_flowable(path, max_width=6.4 * inch, max_height=4.6 * inch):
    im = Image.open(path)
    w, h = im.size
    ratio = min(max_width / w, max_height / h)
    return RLImage(path, width=w * ratio, height=h * ratio)


# ------------------------------------------------------------------ PDF ---
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=20, leading=24, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10.5, leading=14, textColor=MUTED))
styles.add(ParagraphStyle(name="H1", fontSize=13.5, leading=17, spaceBefore=20, spaceAfter=6, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a1a")))
styles.add(ParagraphStyle(name="Body", fontSize=10, leading=15, spaceAfter=6))
styles.add(ParagraphStyle(name="Small", fontSize=8.7, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=12.5))
styles.add(ParagraphStyle(name="CellHead", fontSize=8.9, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle(name="Sev", fontSize=9, leading=12, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="Missing", fontSize=10.5, leading=15.5, spaceAfter=6, backColor=colors.HexColor("#eae1f2")))
styles.add(ParagraphStyle(name="Caption", fontSize=8.7, leading=12, textColor=MUTED, spaceBefore=4, spaceAfter=10))

story = []


def sev_tag(label, color_hex):
    return Paragraph(f'<font color="{color_hex}">{label.upper()}</font>', styles["Sev"])


def grid(rows, col_widths):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_C),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


# ---------------------------------------------------------------- Header ---
story.append(Paragraph("Operator UI Audit", styles["TitleBig"]))
story.append(Paragraph("Dyuthi T G &nbsp;&bull;&nbsp; 2026-08-26 &nbsp;&bull;&nbsp; every screen, used like an operator, checked on desktop and phone", styles["SubTitle"]))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=LINE_C))
story.append(Spacer(1, 10))
story.append(Paragraph(
    "I clicked through the real dashboard the way an operator would — generated a real review queue, "
    "approved and rejected real items, connected an account, and checked the whole thing on a phone. "
    "Below is what I found, worst first.", styles["Body"],
))

# --------------------------------------------------------- Biggest finding ---
story.append(Paragraph(
    "<b>THE BIGGEST FINDING &mdash; SOMETHING MISSING, NOT SOMETHING BROKEN</b><br/><br/>"
    "Going in, the assumption was that there's no screen at all where a human checks the bot's work. "
    "That's not quite right. The review screen (Approvals) is real — it works, and nothing sends without "
    "a click. What it's actually missing: <b>there's no way to see more than one item at a time.</b> No "
    "comparison, no \"these three look identical\" warning. Just one card, then the next. When 9 of 10 "
    "queued comments turned out to be almost the exact same sentence with the name swapped, there was no "
    "way to notice that until several cards had already been clicked past.", styles["Missing"],
))
story.append(Paragraph(
    "A review screen that can't catch repeats isn't a smaller version of human review — it's the "
    "appearance of human review without the substance.", styles["Body"],
))

# ---------------------------------------------------------- Scorecard ---
story.append(Paragraph("What I found", styles["H1"]))
sc_rows = [
    [Paragraph("Blocks work", styles["CellHead"]), Paragraph("Slows work", styles["CellHead"]), Paragraph("Looks bad", styles["CellHead"])],
    [Paragraph("4", styles["Cell"]), Paragraph("3", styles["Cell"]), Paragraph("3", styles["Cell"])],
]
t = Table(sc_rows, colWidths=[2.1 * inch] * 3)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("GRID", (0, 0), (-1, -1), 0.5, LINE_C),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("FONTSIZE", (0, 1), (-1, 1), 16),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
]))
story.append(t)
story.append(Spacer(1, 6))
story.append(Paragraph("\"Blocks work\" always outranks \"slows work,\" which always outranks \"looks bad\" — no matter how visually loud a finding is.", styles["Small"]))

# ============================================================== FINDINGS ==
def finding(sev_label, sev_hex, title, body, img_key, caption):
    story.append(Spacer(1, 14))
    story.append(sev_tag(sev_label, sev_hex))
    story.append(Paragraph(title, styles["H1"]))
    story.append(Paragraph(body, styles["Body"]))
    story.append(img_flowable(shots[img_key]))
    story.append(Paragraph(caption, styles["Caption"]))


finding(
    "Blocks work", "#a8362f",
    "\u201cSuggest who to contact\u201d returns nothing for 9 of the program's first 21 days &mdash; and blames the wrong thing",
    "Every account ramps through six stages before it can connect or message. Clicking the queue's only "
    "button while an account is in the Commenting stage &mdash; where comments are supposed to work "
    "&mdash; returns zero suggestions out of 24 available people, and blames <b>'connect'</b>, an action "
    "nobody tried to use. The generator checks connect/message first and quits before it ever reaches the "
    "comment logic that would have worked.",
    "approvals_error",
    "24 candidate people were on the account, all scored 100 — none reached the operator.",
)

finding(
    "Blocks work", "#a8362f",
    "Ten queued comments, nine of them the same template",
    "Once suggestions did generate, nine of ten used the identical skeleton: \u201cThis matches what I "
    "keep seeing, [name] &mdash; the hard part is usually getting everyone to agree on it first. How did "
    "you handle that?\u201d The queue shows one card at a time, so nothing on this screen would tell an "
    "operator this was happening.",
    "repetition",
    "Same pattern the Aug 21 comment-quality audit flagged at 43 of 58 — now visible live in the queue, with nothing built to catch it.",
)

finding(
    "Blocks work", "#a8362f",
    "\u201cNever contact\u201d is one un-confirmed tap, right next to routine buttons",
    "Tapping Never Contact permanently suppresses a real person. It fires immediately &mdash; no dialog, "
    "no undo. It sits right beside Skip in the same row. On the phone the row wraps to two lines, landing "
    "almost exactly where a thumb rests while scrolling one-handed.",
    "never_contact",
    "Permanent action, zero confirmation, one thumb-width from a routine button.",
)

finding(
    "Blocks work", "#a8362f",
    "\u201cToday's activity\u201d shows a made-up schedule as if it already happened",
    "This account sent nothing today &mdash; three separate counters on the Overview page say so. The "
    "Warm-up page's \u201cToday's activity\u201d panel disagrees: 3 comments, 8 messages, 12 likes, 10 "
    "connects, each with a clock time, formatted exactly like a real log. It's actually a randomized "
    "hypothetical plan, and the real (all-zero) numbers are never shown on this screen at all.",
    "warmup_activity",
    "10 connects, 8 messages shown here. Real total sent today, everywhere else on this account: 0.",
)

finding(
    "Blocks work", "#a8362f",
    "The Agents page renders a blank white screen &mdash; the data is there, it's just invisible",
    "One click from the main menu. The real data loads (5 agents, real status) but the page's own "
    "animation gets stuck before showing anything, leaving a header on an empty page. Reproduced "
    "repeatedly, not a one-off.",
    "agents_blank",
    "5 stat cards and 5 agent cards exist in the page right now — stuck invisible.",
)

finding(
    "Slows work", "#a5680f",
    "Connecting an account means digging into browser DevTools and copying login codes by hand",
    "The only way to link a LinkedIn account: sign in, open DevTools, find two cookie values, and paste "
    "them into the form. There's no simpler login option.",
    "accounts_devtools",
    "Step 2, for every single operator: open developer tools.",
)

finding(
    "Slows work", "#a5680f",
    "No screen anywhere shows the people you've actually imported",
    "This target list has 24 real people behind it. The card only shows the filter rules &mdash; no "
    "count, not clickable. Those 24 people are only ever visible if they later survive into a suggestion.",
    "targeting",
    "24 people live behind this card. Zero of them are visible here.",
)

finding(
    "Looks bad", "#3c5a8a",
    "Two different apps live behind the same menu bar",
    "Every other screen shares one dark, purple-and-amber look. The Agents and Campaigns pages are "
    "white-background, generic-blue, different-font pages &mdash; visibly a different, older build. "
    "Campaigns isn't even linked from the menu; the only way in is typing the address directly.",
    "campaigns_seam",
    "The seam — the real product above this line, a different app below it.",
)

finding(
    "Looks bad", "#3c5a8a",
    "On a phone, the menu loses its labels and the account name disappears",
    "Below tablet width, the menu drops to icons only with no names, and a 6th item gets pushed off the "
    "right edge with just a faint scrollbar as a hint. Lower on the same screen, the connected account's "
    "name vanishes entirely &mdash; just a dot, a divider, and the word \u201coutreach,\u201d no way to "
    "tell which account it is.",
    "mobile_dashboard",
    "The account name is simply gone here — this is the phone view of the very first page an operator sees.",
)

# --------------------------------------------------------------- Recap ---
story.append(Spacer(1, 16))
story.append(Paragraph("Everything, in order", styles["H1"]))
pl_rows = [
    ["Blocks", "Suggestion engine returns nothing for 2 of 6 stages, blames the wrong action", "Approvals"],
    ["Blocks", "No way to see repeats across queued suggestions before approving", "Approvals"],
    ["Blocks", "\u201cNever contact\u201d — permanent, zero confirmation, beside routine buttons", "Approvals"],
    ["Blocks", "\u201cToday's activity\u201d shows a made-up plan labeled as real history", "Warm-up"],
    ["Blocks", "Page renders invisible — data loads, nothing is shown", "Agents"],
    ["Slows", "Connecting an account requires copying raw login codes from DevTools", "Accounts"],
    ["Slows", "No screen shows the raw list of imported people", "Targeting"],
    ["Looks bad", "Different look entirely, and unreachable from the menu", "Agents / Campaigns"],
    ["Looks bad", "Menu loses labels and cuts off an item; account name disappears", "Overview, phone"],
]
pl_data = [[Paragraph(x, styles["CellHead"]) for x in ["Severity", "Finding", "Screen"]]] + \
          [[Paragraph(a, styles["Cell"]), Paragraph(b, styles["Cell"]), Paragraph(c, styles["Cell"])] for a, b, c in pl_rows]
t = grid(pl_data, [0.9 * inch, 4.7 * inch, 1.3 * inch])
story.append(t)

story.append(Spacer(1, 16))
story.append(HRFlowable(width="100%", thickness=0.5, color=LINE_C))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Method: ran the real product on my own machine with real data (1 connected account, 24 imported "
    "people, a live-generated review queue), clicked through every page in the menu plus the two pages "
    "that aren't in the menu, and repeated the main screens on a 390-pixel-wide phone view. Every finding "
    "above was actually seen happening in the browser, not just read from the code.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.7 * inch, rightMargin=0.7 * inch,
    topMargin=0.65 * inch, bottomMargin=0.65 * inch,
    title="Operator UI Audit — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
