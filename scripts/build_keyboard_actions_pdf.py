"""
Generates Keyboard_Actions_Undo.pdf on the Desktop — written like a personal
note, first person, plain sentences, simple words. No jargon.

Run: python scripts/build_keyboard_actions_pdf.py
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

OUT_PATH = r"C:\Users\Dyudhi T G\Desktop\Keyboard_Actions_Undo.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's work — approve, reject, and the keyboard", styles["TitleBig"]))
story.append(Paragraph("Dyuthi &nbsp;&bull;&nbsp; 2026-09-02 &nbsp;&bull;&nbsp; written in my own words", styles["SubTitle"]))

story.append(Paragraph(
    "Today was about making the review screen fast to use, because someone clearing two "
    "hundred comments in a day is never going to touch a mouse for every single one. Here's "
    "what I actually built, in my own words.",
    styles["Body"],
))

story.append(Paragraph("1. Approve, edit-then-approve, and reject now really save", styles["Body"]))
story.append(Paragraph(
    "All three buttons actually talk to the system now. Reject also asks why, every single "
    "time — you have to type a reason, you can't skip it. That's on purpose: the reason is "
    "what teaches the system to write better comments later, so it can't be left blank.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("2. You can clear the whole list without touching the mouse", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("J and K move you up and down the list", styles["BodyIndent"])),
    ListItem(Paragraph("A approves whoever is selected", styles["BodyIndent"])),
    ListItem(Paragraph("R opens a small box to type why you're rejecting, then Enter sends it", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "I timed it for real: cleared 10 comments using only the keyboard in under 2 seconds of "
    "key presses. Nothing made me wait in between.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("3. Approve feels instant, with 5 seconds to undo", styles["Body"]))
story.append(Paragraph(
    "The old way would've made you sit and wait for the server every single time you approved "
    "something, before you could move to the next one. Now the comment leaves the list the "
    "moment you act, and a small \"Undo\" button shows up for 5 seconds. Only after those 5 "
    "seconds does it actually send. Click Undo in time and it's like it never happened — "
    "nothing was sent, nothing was recorded. I tested this exact thing: undo really does stop "
    "it, and letting the 5 seconds pass really does send it. No pop-up boxes asking \"are you "
    "sure\" — those are the kind of thing people learn to click through without reading anyway.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("4. Every decision gets written down, using what we already had", styles["Body"]))
story.append(Paragraph(
    "The brief said not to build a second logging system if one already exists — so before "
    "writing anything, I went looking. Found one: the app already keeps a record of every "
    "action an account takes, originally built for tracking warm-up progress. I used that "
    "same record for approvals and rejections instead of inventing a new one. Every approve "
    "and every reject (with its reason) now lands in that one place.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

story.append(Paragraph("Tested for real: ran everything twice on purpose", styles["Body"]))
story.append(Paragraph(
    "The brief said: run the same action twice on the same comment, it must not post twice or "
    "log twice. So I actually did that, through the real system, not just in my head:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Approved the same comment twice — the second try was refused, nothing extra was sent or recorded", styles["BodyIndent"])),
    ListItem(Paragraph("Rejected the same comment twice — same result, refused the second time, only one record written", styles["BodyIndent"])),
    ListItem(Paragraph("Checked the actual record after each test to count exactly how many entries got written — always exactly one", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 8))
story.append(Paragraph("Checked it was actually working, not just guessed", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("Opened the real app and used J, K, A, and R myself, more than once", styles["BodyIndent"])),
    ListItem(Paragraph("Timed clearing 10 real comments with only the keyboard", styles["BodyIndent"])),
    ListItem(Paragraph("Ran the code checker — no errors", styles["BodyIndent"])),
    ListItem(Paragraph("Ran all 240 automatic tests — every one passed", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 16))
story.append(Paragraph(
    "That's today. Fast to clear with just the keyboard, a real 5-second undo instead of "
    "annoying pop-ups, a reason required on every reject, and every decision written down in "
    "the log that was already there.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    topMargin=0.8 * inch, bottomMargin=0.8 * inch,
    title="Today's work — approve, reject, and the keyboard",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
