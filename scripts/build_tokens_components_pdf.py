"""
Generates Design_Tokens_Components.pdf — written like a personal note, first
person, plain sentences. Same facts as before, none of the report formatting.

Run: python scripts/build_tokens_components_pdf.py
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

OUT_PATH = "Design_Tokens_Components.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's work — design tokens + components", styles["TitleBig"]))
story.append(Paragraph("Dyuthi &nbsp;&bull;&nbsp; 2026-08-31 &nbsp;&bull;&nbsp; written in my own words, not a formal report", styles["SubTitle"]))

story.append(Paragraph(
    "Had 4 things to get done today, so here's what I actually did, in my own words, not "
    "office-speak.", styles["Body"],
))

story.append(Paragraph("1. Picked 8 colours and wrote them into the code", styles["Body"]))
story.append(Paragraph(
    "Didn't want anyone (including me) arguing about colours later, so I just picked 8 and "
    "locked them in: the page background, the card background, borders, normal text, faded "
    "text, my main brand colour, a green for “approve”, and a red for “danger.” "
    "That's genuinely all 8. Nothing fancier.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("2. Picked 5 text sizes, that's it", styles["Body"]))
story.append(Paragraph(
    "12px for tiny stuff like timestamps, 14px for normal text and buttons, 16px for card "
    "titles, 20px for section headers, 28px for page titles. Five sizes, done.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("3. Left spacing alone", styles["Body"]))
story.append(Paragraph(
    "Turned out the app already measured everything in steps of 4 pixels anyway, so instead of "
    "changing anything I just wrote that down as the official rule.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("4. Built exactly 4 reusable pieces, and stopped myself there", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("A <b>Card</b> — the box shape everything sits inside", styles["BodyIndent"])),
    ListItem(Paragraph("A <b>Chip</b> — the small labeled pill (match score, why-matched tags, warning flags)", styles["BodyIndent"])),
    ListItem(Paragraph("A <b>Button</b> — one file that handles all 4 button styles (normal, approve, cancel, dangerous)", styles["BodyIndent"])),
    ListItem(Paragraph("An <b>Empty State</b> — the “nothing here yet” screen", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "I really wanted to build a couple more while I was in there, but I made myself stop. Rule I "
    "set: only build something new the second time I actually need it, not the first.", styles["Small"],
))

story.append(Paragraph("5. Actually checked if the colours were readable", styles["Body"]))
story.append(Paragraph(
    "Not just eyeballing it — ran the real readability math on every text-on-colour combo. And it "
    "caught something real: white text on my “approve” green button was basically "
    "unreadable (2.54, when it needs to be at least 4.5 to pass). So I made the green darker "
    "until it actually passed — 5.48. Glad I checked instead of assuming it was fine.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("6. Made sure it's real, not just pretty", styles["Body"]))
story.append(Paragraph(
    "“Done” for today meant it had to actually work in the real app, not just look nice "
    "somewhere isolated. So I:", styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Swapped the real Approvals screen over to use these new pieces — not a copy off to the side", styles["BodyIndent"])),
    ListItem(Paragraph("Opened the actual running app and clicked around to make sure it still worked", styles["BodyIndent"])),
    ListItem(Paragraph("Ran the type-checker — zero errors", styles["BodyIndent"])),
    ListItem(Paragraph("Ran all 236 automatic tests — every single one passed, nothing else broke", styles["BodyIndent"])),
    ListItem(Paragraph("Saved it and pushed it to GitHub, so it's not just sitting on my laptop", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 16))
story.append(Paragraph(
    "That's the whole thing. Small, boring decisions, made once, written down, actually working "
    "in the app — not just talked about.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    topMargin=0.8 * inch, bottomMargin=0.8 * inch,
    title="Today's work — design tokens + components",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
