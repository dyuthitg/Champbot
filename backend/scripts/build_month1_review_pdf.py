"""
Generates Sep18_Month1_Review_And_Month2_Proposal.pdf -- the Sep 18 brief:
demo outline, real before/after quality numbers, an honest "is it live"
answer, a retro, and one Month 2 recommendation (not a menu).

Run: python scripts/build_month1_review_pdf.py
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
    Table,
    TableStyle,
)

OUT_PATH = "Sep18_Month1_Review_And_Month2_Proposal.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")
WARN_AMBER = colors.HexColor("#8a6a1a")
GOOD_GREEN = colors.HexColor("#2f6f4f")
LINE = colors.HexColor("#d8d8d8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="H2", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=16.5, spaceAfter=10, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=10, leftIndent=14))
styles.add(ParagraphStyle(name="WarnHead", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=3, fontName="Helvetica-Bold", textColor=WARN_AMBER))
styles.add(ParagraphStyle(name="GoodHead", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=3, fontName="Helvetica-Bold", textColor=GOOD_GREEN))
styles.add(ParagraphStyle(name="Cell", fontSize=9.0, leading=12.2, textColor=INK))
styles.add(ParagraphStyle(name="CellHead", fontSize=9.0, leading=12.2, textColor=colors.white, fontName="Helvetica-Bold"))


def grid(rows, col_widths, header_bg=INK):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
    ]))
    return t


story = []

story.append(Paragraph("Month 1 review: what I built, what it's worth, what's next", styles["TitleBig"]))
story.append(Paragraph("2026-09-18 &nbsp;&bull;&nbsp; 15-minute review for Deep", styles["SubTitle"]))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. The 15-minute demo, in order", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>The problem (2 min).</b> The bot had been stuck since March: a review "
                        "queue nobody trusted, quality nobody had measured, and no path from "
                        "“it runs” to “someone would actually let it touch a real account.”",
                        styles["Body"])),
    ListItem(Paragraph("<b>What I built (7 min).</b> A real review queue wired to real data with "
                        "keyboard actions and undo; a quality gate with a named rule table, shown "
                        "the same way to the reviewer and in the spec; brand voice as a per-account "
                        "config file, no deploy needed; guardrail flags visible in the queue instead "
                        "of hidden in logs; an operator runbook, a voice-tuning guide, and a "
                        "documented, rerunnable quality measurement method.", styles["Body"])),
    ListItem(Paragraph("<b>The numbers (3 min).</b> Section 2 below.", styles["Body"])),
    ListItem(Paragraph("<b>What's still open (3 min).</b> Section 3 below -- said plainly, not "
                        "glossed over.", styles["Body"])),
], bulletType="1", leftIndent=14))
story.append(Paragraph(
    "Rehearsed once, out loud, alone, before this goes in front of Deep -- per the brief.",
    styles["Small"],
))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. The before/after quality numbers", styles["H1"]))
story.append(Paragraph(
    "Method: <b>backend/scripts/run_golden_set.py</b> runs the real copywriter against all 30 "
    "golden-set cases (5 each of funding / hiring / thought-leadership / product-launch / "
    "personal-milestone, plus 3 layoffs and 2 condolences that should get no comment at all), "
    "through a real OpenRouter call, and grades every result with a deterministic 0-3 scorer. "
    "Same code, same 30 cases, same scorer, both times -- that's what makes the comparison honest.",
    styles["Body"],
))
rows = [
    ["", "Baseline", "After one prompt change", "Change"],
    ["Average rubric score (0-3)", "1.77", "1.93", "+0.16"],
    ["Hit the post's specific hook (score 3)", "6 / 30", "10 / 30", "+4"],
    ["Generic but personalized (score 2)", "14 / 30", "11 / 30", "-3"],
    ["No personalization at all (score 1)", "7 / 30", "6 / 30", "-1"],
    ["Blocked / wrong tone / SKIP-case miss (score 0)", "3 / 30", "3 / 30", "0"],
]
story.append(grid(
    [[Paragraph(c, styles["CellHead"]) for c in rows[0]]] +
    [[Paragraph(c, styles["Cell"]) for c in r] for r in rows[1:]],
    [2.55 * inch, 1.15 * inch, 1.6 * inch, 0.95 * inch],
))
story.append(Spacer(1, 6))
story.append(Paragraph(
    "The one change tested was a prompt instruction telling the model to find the single most "
    "distinctive detail in the post and build the comment around it. It measurably helped "
    "specificity (the “3” column nearly doubled) and, by design, didn't touch the three "
    "score-of-0 cases -- the bot still has no concept of “don't comment on this post at all,” "
    "which is a separate, bigger change. Verified again today as part of this review, rerunning the "
    "same script live: <b>2.00/3</b> on a fresh run -- same range, real variance from a real model "
    "call, not a fabricated repeat of the old number.",
    styles["Body"],
))
story.append(Paragraph(
    "Caveat that stays attached to every one of these numbers: this is golden-set data -- realistic "
    "but synthetic, not a live account. It measures “did this change help in principle,” not a "
    "substitute for reviewing real queue output.",
    styles["Small"],
))

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. Is the bot live?", styles["H1"]))
story.append(Paragraph("Not yet. Named blocker, not a vague “almost there.”", styles["WarnHead"]))
story.append(Paragraph(
    "The Sep 15 brief called for a real person approving 20 real items on a real disposable "
    "account, with Deep watching and Harshil's written sign-off on the blast-radius plan on record "
    "first. That session hasn't run. Three prerequisites are still not confirmed green: a real "
    "<b>ENCRYPTION_KEY</b> (Hemang), Redis actually standing up with <code>/healthz</code> reporting "
    "ok (Deep), and Harshil's written sign-off itself. Full detail in "
    "<b>Sep15_Live_Dry_Run_Status.pdf</b>.",
    styles["Body"],
))
story.append(Paragraph(
    "<b>Recommendation:</b> once those three items are confirmed green -- which is infra work, not "
    "product work, and doesn't depend on me -- the live session can run within the same week. "
    "Proposing <b>Sep 22</b> as the target date for the real 20-item session, with the actual "
    "go/no-go to follow once that log is filled in, not before.",
    styles["Body"],
))

# ============================================================== SECTION 4 ==
story.append(Paragraph("4. Retro: what worked, what I'd redo", styles["H1"]))
story.append(Paragraph("What worked", styles["GoodHead"]))
story.append(ListFlowable([
    ListItem(Paragraph("Measuring the baseline before guessing at a fix. I assumed the dominant "
                        "problem was still yesterday's banned-phrase issue; the baseline measurement "
                        "proved that assumption wrong and pointed at specificity instead. Guessing "
                        "first would have spent a day fixing the wrong thing.", styles["Body"])),
    ListItem(Paragraph("Changing one thing at a time and measuring it. The before/after number is "
                        "trustworthy specifically because nothing else moved between the two runs.",
                        styles["Body"])),
    ListItem(Paragraph("Reusing what already existed instead of inventing parallel systems -- the "
                        "existing account-activity audit ledger for approvals, the existing "
                        "BREAK_LIST.md shape for issues, the existing ship-note format for every "
                        "PDF. Fewer formats for the next person to learn.", styles["Body"])),
], bulletType="bullet", leftIndent=14))
story.append(Paragraph("What I'd redo", styles["WarnHead"]))
story.append(ListFlowable([
    ListItem(Paragraph("I let the Sep 15 live-session prerequisites (ENCRYPTION_KEY, Redis) sit "
                        "unconfirmed for three days before naming them plainly in a status doc. "
                        "Naming a blocker the day it's discovered, not the day someone asks about "
                        "it, is the actual habit worth keeping.", styles["Body"])),
    ListItem(Paragraph("The Sep 16 repo split (frontend/ and backend/) shipped without an audit of "
                        "which scripts compute paths relative to their own location -- one "
                        "(run_golden_set.py) broke silently and only surfaced today because I "
                        "happened to run the exact command the docs tell people to run. A "
                        "structural change like that deserved a five-minute grep for "
                        "<code>Path(__file__)</code> across scripts/ before calling it done.",
                        styles["Body"])),
    ListItem(Paragraph("Still only one reviewer on the whole project. That was fine at demo scale; "
                        "it's the first real limit Month 2 hits if account count goes up before a "
                        "second approver is trained.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 5 ==
story.append(Paragraph("5. Month 2 proposal", styles["H1"]))
story.append(Paragraph(
    "<b>One recommendation:</b> don't widen to more accounts until the Sep 15 live session has "
    "actually run and passed go/no-go. Once it has, add a second trained reviewer before adding a "
    "second account -- the single-reviewer bottleneck in "
    "<b>docs/REVIEW_SLA.md</b> §2 is the more urgent scaling limit than account count, and it's "
    "cheaper to fix first. In parallel, start the ChampESS front-end track (per the program's own "
    "Month 2 window, 21 Sep to 16 Oct) since it doesn't compete for the same reviewer time.",
    styles["Body"],
))
story.append(Paragraph(
    "<b>What I'd stop doing:</b> building new guardrail-flag types ahead of demand. Every flag in "
    "the current rule table traces back to a real thing the audit or the golden set found -- that "
    "discipline is worth keeping instead of adding rules that feel plausible but aren't backed by a "
    "measured failure.",
    styles["Body"],
))
story.append(Paragraph(
    "The Ranch and Montana idea, parked in August, is on the table for Month 2 per the program's "
    "own plan -- I don't have the specifics of that idea written down anywhere in this repo or in "
    "what I've worked from this month, so bringing it back out needs a real conversation with Deep, "
    "not a guess from me about what it was.",
    styles["Small"],
))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing above is committed or pushed yet -- same as always, tell me and I'll do it.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Month 1 review and Month 2 proposal (2026-09-18)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
