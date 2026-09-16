"""
Generates Golden_Set_And_Rubric.pdf — written like a personal note, first
person, plain sentences, simple words. No report formatting.

Run: python scripts/build_golden_set_pdf.py
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

OUT_PATH = "Golden_Set_And_Rubric.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("The 30-case golden set, and the rubric to score against it", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-07 &nbsp;&bull;&nbsp; written in my own words, not a formal report",
    styles["SubTitle"],
))

story.append(Paragraph(
    "The brief was: 30 real-shaped posts, the ideal comment for each written by hand, and a 0-to-3 "
    "rubric with anchors clear enough that someone else scores the same way I would. Slow on "
    "purpose. Here's what I shipped and where to find each piece.",
    styles["Body"],
))

# ------------------------------------------------------------- 1
story.append(Paragraph("1. Thirty posts, spanning what the bot actually sees", styles["Body"]))
story.append(Paragraph(
    "5 each of funding news, hiring posts, thought leadership, product launches, and personal "
    "milestones. Plus 3 layoffs and 2 condolence posts, on purpose, because you asked for the "
    "awkward ones and you're right that's where this breaks.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "None of these are real people. I made them up. Two reasons: we still don't have live LinkedIn "
    "access to go scrape real posts with, and even if we did, I didn't want a permanent test file in "
    "the repo built out of real people's real grief and real layoffs. Each one is written to feel "
    "like a real post though — specific numbers, specific small details, not generic filler — because "
    "a vague fake post would let a vague fake comment pass, and that defeats the point.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 2
story.append(Paragraph("2. A hand-written ideal comment for every one of the 30", styles["Body"]))
story.append(Paragraph(
    "I wrote what I'd actually post, not what sounds impressive. The pattern across almost all of "
    "them: respond to the one specific detail that makes this post different from the four others in "
    "its category, not the general topic. “Congrats on the raise” works on all five funding "
    "posts equally, which is exactly why it's wrong for all five.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 3 the hard part
story.append(Paragraph("3. The part that actually mattered: three cases where the right answer is silence", styles["Body"]))
story.append(Paragraph(
    "Two condolence posts and one layoff post announced in corporate-speak (“optimizing our "
    "workforce to align with strategic priorities”) are marked SKIP in the notes column. For "
    "those three, I didn't write an ideal comment, because there isn't one — the correct output is "
    "no comment at all. A well-written comment on a bereavement post is not a slightly-wrong answer, "
    "it's the specific failure that costs you a person's trust permanently.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "This is why the rubric's first question isn't about tone or specificity — it's “should this "
    "have gotten a comment at all.” If the bot ever writes fluent, on-topic text for one of these "
    "three, that's a 0 no matter how good the sentence is. I'd rather find that out against 30 fake "
    "posts today than against a real one later.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 4 rubric
story.append(Paragraph("4. The rubric: one number, four anchors", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>3</b> — exactly what I'd have posted myself, responds to the one distinctive detail", styles["BodyIndent"])),
    ListItem(Paragraph("<b>2</b> — good, read the post, right tone, but I'd tweak one phrase", styles["BodyIndent"])),
    ListItem(Paragraph("<b>1</b> — technically fine, but could've been posted on anyone's similar update unchanged", styles["BodyIndent"])),
    ListItem(Paragraph("<b>0</b> — wrong tone for the moment, a formulaic template shape, or commented on a SKIP case at all", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "No sub-scores for tone, specificity, length, and so on separately. One number. I tried a longer "
    "version first and it took four times as long to apply and didn't produce different scores than "
    "the short one — the anchors were doing the real work, not the extra dimensions.",
    styles["Small"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 5 calibration
story.append(Paragraph("5. How I'll know the rubric actually holds, not just feels right to me", styles["Body"]))
story.append(Paragraph(
    "I haven't skipped this, but I also can't finish it alone — it needs a second person. The plan, "
    "written down in the rubric file so it's ready to run: pick 3 posts (one easy, one medium, one "
    "hard), give Harshil only the source posts, no ideal comments, no notes, and have him write a "
    "comment for each blind. Then I score his three against the rubric myself.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "If he agrees with my score and the reason I give for it, the rubric is anchored well enough to "
    "trust on real bot output. If he doesn't — I call his comment a 2, he thinks it's obviously a 3 — "
    "that's not him being wrong, it means one of the anchors is vague enough that two reasonable "
    "people read it differently, and I go fix that anchor with his exact case as the new example.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "This is the one piece of today's brief I can point you to but haven't closed out, because it "
    "needs Harshil's actual time, not more of mine.",
    styles["Small"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 6 where
story.append(Paragraph("6. Where everything is", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>docs/golden_set/golden_set.csv</b> — all 30 cases: post, author, hand-written ideal comment, notes", styles["BodyIndent"])),
    ListItem(Paragraph("<b>docs/golden_set/RUBRIC.md</b> — the 0-to-3 rubric, the anchors, and the Harshil blind-test steps", styles["BodyIndent"])),
    ListItem(Paragraph("<b>scripts/build_golden_set.py</b> — regenerates the CSV from source; edit the posts here, not the CSV directly", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "Nothing here is committed or pushed yet. Say the word and I'll push it.",
    styles["Small"],
))
story.append(Paragraph(
    "What I need from you: 15 minutes of Harshil's time for the blind test in section 5. That's the "
    "one thing that turns “I think this rubric is right” into “we checked, and it is.”",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Golden set and rubric (2026-09-07)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
