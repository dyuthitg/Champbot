"""
Generates Task_Update_Aug25.pdf — plain memo version of the audit rollup.
No color, no boilerplate section templates, written as running prose.

Run: python scripts/build_task_update_pdf.py
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_PATH = "Task_Update_Aug25.pdf"

styles = getSampleStyleSheet()
BODY_FONT = "Times-Roman"
BOLD_FONT = "Times-Bold"

styles.add(ParagraphStyle(name="Head", fontName=BOLD_FONT, fontSize=15, leading=18, spaceAfter=2))
styles.add(ParagraphStyle(name="SubHead", fontName=BODY_FONT, fontSize=10, leading=13, textColor=colors.black))
styles.add(ParagraphStyle(name="Section", fontName=BOLD_FONT, fontSize=11.5, leading=15, spaceBefore=16, spaceAfter=6))
styles.add(ParagraphStyle(name="Body", fontName=BODY_FONT, fontSize=10.4, leading=15, spaceAfter=8))
styles.add(ParagraphStyle(name="Quote", fontName="Times-Italic", fontSize=10.2, leading=14, leftIndent=18, spaceAfter=8))
styles.add(ParagraphStyle(name="Cell", fontName=BODY_FONT, fontSize=9, leading=12))
styles.add(ParagraphStyle(name="CellBold", fontName=BOLD_FONT, fontSize=9, leading=12))

story = []

# ------------------------------------------------------------------ header
story.append(Paragraph("Task update", styles["Head"]))
story.append(Paragraph("Dyuthi &mdash; brand voice / social copy audit &mdash; Aug 17 to 25", styles["SubHead"]))
story.append(Spacer(1, 8))
story.append(HRFlowable(width="100%", thickness=0.6, color=colors.black))
story.append(Spacer(1, 10))

story.append(Paragraph(
    "Here's where things stand on the comment audit work. Two pieces: the quality audit I ran last "
    "week on what the bot is actually posting, and a follow-up this week checking whether the comment "
    "rules we already agree on are enforced in code, or just requested in the prompt and hoped for. "
    "Writing it up now so you've got the specifics before Friday rather than the summary version.",
    styles["Body"],
))

# ------------------------------------------------------------------ sec 1
story.append(Paragraph("What's actually coming out of the bot", styles["Section"]))

story.append(Paragraph(
    "There was no audit-log export to pull from and nothing reachable in a live account, so I built "
    "a script (scripts/audit_run.py) that pushes 58 synthetic prospects through the real pipeline &mdash; "
    "targeting, then the copywriter, then the quality gate &mdash; and logs everything that comes out the "
    "other side. First pass produced identical template copy for all 58, which turned out to be my own "
    "fault: an import in the test harness was wiping the OpenRouter key before the model call ran. Fixed "
    "that. Also found that the model we have configured, claude-3.5-sonnet, isn't a valid OpenRouter "
    "slug &mdash; this run used gpt-4o-mini instead, so treat the exact wording below as illustrative, not final.",
    styles["Body"],
))

story.append(Paragraph(
    "Once real generations were flowing I scored all 58 by hand against a taxonomy I built for this "
    "(scripts/score_audit.py). Split came out 6 good, 41 weak, 11 fail. The thing that actually matters: "
    "43 of the 58 &mdash; 74% &mdash; end with some version of the same question, “have you found any "
    "specific strategies for X?”, usually preceded by a “you nailed it” opener. That isn't 58 "
    "individual weak comments. It's one comment reused on 58 different people. And the quality gate scored "
    "every one of them 100 out of 100.",
    styles["Body"],
))

story.append(Paragraph(
    "Worth being specific about why the gate missed it, because it's a fixable bug, not a fuzzy "
    "calibration problem. The personalization check stoplists generic words like “growth” or "
    "“strategy” before crediting a match against someone's headline (quality.py:324&ndash;327) "
    "&mdash; that part is genuinely well built. The equivalent check against the post text, three lines "
    "further down (quality.py:330&ndash;336), has no stoplist at all. Since every comment in this batch is "
    "about activation or retention because the source post was, that check auto-passes almost every time. "
    "That's the actual reason this needed a human doing it by hand.",
    styles["Body"],
))

tax_rows = [
    ["Rank", "Failure", "n", "freq × sev"],
    ["1", "formulaic closing question", "43", "2425"],
    ["2", "validation opener", "32", "2010"],
    ["3", "full 3-beat template", "25", "1650"],
    ["4", "no specific detail", "20", "1384"],
    ["5", "sycophancy", "10", "610"],
    ["6", "exclamation hype", "2", "100"],
]
tax_data = [[Paragraph(c, styles["CellBold"] if r == 0 else styles["Cell"]) for c in row] for r, row in enumerate(tax_rows)]
t = Table(tax_data, colWidths=[0.55 * inch, 2.4 * inch, 0.5 * inch, 0.9 * inch])
t.setStyle(TableStyle([
    ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
    ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.black),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
]))
story.append(t)
story.append(Spacer(1, 8))

story.append(Paragraph("Worst one, word for word:", styles["Body"]))
story.append(Paragraph(
    "“You're spot on about the ICP issue. It's interesting how a narrow focus can actually improve "
    "both activation and retention. Have you found any specific strategies that work well for refining "
    "ICP in a B2B context?” &mdash; scored 5/100 by hand, 100/100 by the gate.",
    styles["Quote"],
))

story.append(Paragraph(
    "What I'd fix first: stoplist the post-text check the same way the headline one already is &mdash; "
    "one line, in quality.py. Add something that looks across an account's pending comments for repeated "
    "structure, since right now each comment is scored alone and can never see the pattern. And add the "
    "specific phrases this run turned up (“spot on,” “have you found any specific strategies”) "
    "to the banned-phrase list that already exists and already runs &mdash; it just isn't pointed at these.",
    styles["Body"],
))

story.append(Paragraph(
    "Everything above lives in BOT_OUTPUT_AUDIT_V1.md, with the full data in audit_log_scored.csv.",
    styles["Body"],
))

# ------------------------------------------------------------------ sec 2
story.append(Paragraph("Are the rules we have actually enforced", styles["Section"]))

story.append(Paragraph(
    "This week's follow-up was narrower: take the four rules everyone already agrees are good &mdash; "
    "one to three sentences, roughly a three-line cap, a banned-phrase list, has to reference something "
    "specific &mdash; and check whether the code actually holds that line, rather than just asking the "
    "model nicely and hoping.",
    styles["Body"],
))

story.append(Paragraph(
    "One note before the table: the brief pointed at services/comment_generator.py, which doesn't exist "
    "anywhere in this repo. Flagging it for Harshil &mdash; either the brief is describing an older layout "
    "or he means a different file, worth two minutes before Friday. What does exist is a clean split: the "
    "prompt lives in src/outreach/copy.py, the actual enforcement lives in src/outreach/quality.py. Every "
    "row below is one rule, whether it's enforced, and the file and line proving it either way.",
    styles["Body"],
))

gap_rows = [
    ["Rule", "Enforced?", "Evidence"],
    ["1–3 short sentences", "No", "No sentence-count logic anywhere in check_copy() (quality.py:151–297); the prompt itself asks for “one or two,” not one to three (copy.py:139)."],
    ["~3-line cap", "Proxy only, ~2x loose", "COMMENT_MAX = 400 characters (quality.py:34) works out to roughly 6 lines at 65 chars/line. Nothing counts lines or newlines."],
    ["Banned phrase list", "Runs, but incomplete", "_TIRED_PHRASES (quality.py:38–70) is actually checked (228–231) but has no entry for “spot on,” “nailed it,” or “great post.”"],
    ["Must reference something specific", "Half enforced", "Stoplist applied to the headline match (quality.py:323–327), not to the post-text match (330–336) — the bug from the section above."],
    ["No flattery / no product mentions", "No", "No check for either exists in check_copy() at all."],
]
gap_data = [[Paragraph(c, styles["CellBold"] if r == 0 else styles["Cell"]) for c in row] for r, row in enumerate(gap_rows)]
t = Table(gap_data, colWidths=[1.35 * inch, 1.05 * inch, 4.2 * inch])
t.setStyle(TableStyle([
    ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
    ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.black),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)
story.append(Spacer(1, 8))

story.append(Paragraph(
    "Two of these I can just fix myself this week &mdash; they're list edits, not new logic: add the "
    "missing banned phrases, and fix the one-word mismatch in the prompt where it says “one or two” "
    "sentences instead of “one to three.” The other three need actual new code in a file that "
    "connect and message also depend on, so those go to Hemang rather than me shipping them solo. Full "
    "table and reasoning is in COMMENT_RULES_ENFORCEMENT_GAP.md.",
    styles["Body"],
))

# ------------------------------------------------------------------ sec 3
story.append(Paragraph("Ideas worth floating, not built", styles["Section"]))
story.append(Paragraph(
    "A few directions came up while doing this that might be worth a longer conversation later. Not "
    "scoped, not estimated, just noting them here so they don't get lost: writing in a distinct voice "
    "per account instead of one global style for everyone; a second pass where a model judges the draft "
    "the way the recipient actually would, since that's exactly the kind of thing a structural gate keeps "
    "missing; letting the bot push back occasionally instead of only ever agreeing, since “always "
    "validates” is itself part of the fingerprint the audit found; and tracking which comments actually "
    "get replies so the system can learn from outcomes instead of only from the gate.",
    styles["Body"],
))

# ------------------------------------------------------------------ sec 4
story.append(Paragraph("Where I need a call from you", styles["Section"]))
story.append(ListFlowable([
    ListItem(Paragraph("Everything above is synthetic prospects through the real pipeline, not a live account — want to re-run once a live account is reachable to confirm the pattern holds.", styles["Body"])),
    ListItem(Paragraph("Is the personalization stoplist fix mine to ship, or does it route through whoever owns quality.py?", styles["Body"])),
    ListItem(Paragraph("The rule-enforcement fixes that touch shared code need Hemang's time booked, not just a heads-up.", styles["Body"])),
    ListItem(Paragraph("Need two minutes with Harshil on the comment_generator.py path mismatch.", styles["Body"])),
], bulletType="bullet", leftIndent=16))

# ------------------------------------------------------------------ sec 5
story.append(Paragraph("Everything that's on disk", styles["Section"]))
story.append(Paragraph(
    "DAILY_WORK_LOG.md and RAMP_WEEK_REPORT.md (last week's log and summary), BOT_OUTPUT_AUDIT_V1.md "
    "(the comment audit, full writeup), audit_log.csv / audit_log_scored.csv / audit_report.md (the "
    "underlying data), scripts/audit_run.py and scripts/score_audit.py (both re-runnable), and "
    "COMMENT_RULES_ENFORCEMENT_GAP.md (this week's enforcement audit).",
    styles["Body"],
))

story.append(Spacer(1, 6))
story.append(Paragraph("Happy to walk through any of this live if that's easier than reading it.", styles["Body"]))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.85 * inch, rightMargin=0.85 * inch,
    topMargin=0.8 * inch, bottomMargin=0.8 * inch,
    title="Task update",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
