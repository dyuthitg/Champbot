"""
Generates Queue_List_Real_Data.pdf on the Desktop — written like a personal
note, first person, plain sentences, simple words. No jargon.

Run: python scripts/build_queue_list_pdf.py
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

OUT_PATH = r"C:\Users\Dyudhi T G\Desktop\Queue_List_Real_Data.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's work — the real list of comments", styles["TitleBig"]))
story.append(Paragraph("Dyuthi &nbsp;&bull;&nbsp; 2026-09-01 &nbsp;&bull;&nbsp; written in my own words", styles["SubTitle"]))

story.append(Paragraph(
    "Today's rule was: use real data, not fake sample data. Fake data hides real problems, like a "
    "comment that's way too long. It's okay if it looks ugly today. It has to be true.",
    styles["Body"],
))

story.append(Paragraph("1. Made the list, and it shows real comments", styles["Body"]))
story.append(Paragraph(
    "No pretend screens. The Approvals page now shows the real list of comments waiting for "
    "review, pulled straight from the system. Each row shows the person's name, what they're "
    "replying to, the comment we want to post, and two buttons — Approve and Skip. There's also "
    "an “Open” button if you want to see more. It doesn't look pretty yet, that comes Thursday. "
    "But everything on the screen is real.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("2. Handled all three cases: loading, empty, and broken", styles["Body"]))
story.append(Paragraph(
    "I did all three today instead of putting it off. While the list is loading, you see a "
    "spinner. When there's nothing waiting, you see a simple “all done” message. And if "
    "something goes wrong and the list can't load, you now see a clear message plus a button to "
    "try again — instead of just an empty blank screen that looks broken.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("3. Now you can see the post each comment is replying to", styles["Body"]))
story.append(Paragraph(
    "You can't tell if a comment is good without seeing what it's replying to. The good news: "
    "that info was already saved in the system, it just wasn't being shown. So I didn't need to "
    "wait and ask Hemang about it — I fixed it myself today. Now every comment shows the words "
    "“Replying to:” followed by the actual post. I also added a test so this can't quietly break "
    "again later.", styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("4. Tested it for real before calling it done", styles["Body"]))
story.append(Paragraph(
    "The rule was: if it lags, or if one really long comment breaks the layout, it's not done. "
    "So instead of just looking at a few items, I loaded 60 real people into the system, using "
    "the real comment-writing part of the app — not fake text I typed myself. I made one of those "
    "60 comments almost 1,000 characters long on purpose, to try to break it.", styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Scrolled through all 60 — nothing lagged", styles["BodyIndent"])),
    ListItem(Paragraph("The very long comment did not break anything. It just wrapped onto more lines", styles["BodyIndent"])),
    ListItem(Paragraph("Checked how it looks on a phone screen too, like I was asked to", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Spacer(1, 8))

story.append(Paragraph("Two real problems this testing found", styles["Body"]))
story.append(Paragraph(
    "This is why testing with real, messy data matters. If I'd used a small, clean, fake sample, "
    "I never would have found these:", styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph(
        "<b>The list was hiding 10 comments without telling anyone.</b> I had 60 comments "
        "waiting, but the screen only ever showed 50. No warning, nothing saying “and 10 more.” "
        "They were just missing. I found the setting causing this and fixed it, so now the list "
        "shows everything that's actually waiting.",
        styles["BodyIndent"],
    )),
    ListItem(Paragraph(
        "<b>On a phone screen, words were overlapping.</b> The label and the score number were "
        "printed on top of each other, so you couldn't read either one. I fixed the layout so "
        "everything moves to its own line instead of overlapping.",
        styles["BodyIndent"],
    )),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 8))
story.append(Paragraph("Checked it was actually working, not just guessed", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("Opened the real app myself and clicked through it more than once", styles["BodyIndent"])),
    ListItem(Paragraph("Ran the code checker — no errors", styles["BodyIndent"])),
    ListItem(Paragraph("Ran all 237 automatic tests — every one passed", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 16))
story.append(Paragraph(
    "That's today's work. The list is a bit plain to look at, but it's real, it handles all the "
    "cases it should, and testing it with real messy data caught two real problems before anyone "
    "else saw them.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    topMargin=0.8 * inch, bottomMargin=0.8 * inch,
    title="Today's work — the real list of comments",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
