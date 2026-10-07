"""
Generates TASK_AUDIT_2026-08-25.pdf — a manager-facing rollup of the ramp-week
comment-quality audit and the rules-vs-reality enforcement audit.

Run: python scripts/build_task_audit_pdf.py
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
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

OUT_PATH = "TASK_AUDIT_2026-08-25.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=20, leading=24, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10.5, leading=14, textColor=colors.HexColor("#555555")))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=18, spaceAfter=8, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a1a")))
styles.add(ParagraphStyle(name="H2", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="Body", fontSize=9.7, leading=14, alignment=TA_LEFT, spaceAfter=6))
styles.add(ParagraphStyle(name="Quote", fontSize=9.3, leading=13, leftIndent=14, textColor=colors.HexColor("#333333"), spaceAfter=4, fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="Small", fontSize=8.5, leading=11, textColor=colors.HexColor("#666666")))
styles.add(ParagraphStyle(name="Cell", fontSize=8.7, leading=11.5))
styles.add(ParagraphStyle(name="CellHead", fontSize=8.9, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white))

story = []

# ---------------------------------------------------------------- Header ---
story.append(Paragraph("Task Audit — Brand Voice / Social Copy Auditor", styles["TitleBig"]))
story.append(Paragraph("Dyuthi T G  &nbsp;&bull;&nbsp; LinkedIn Automation Platform  &nbsp;&bull;&nbsp; 2026-08-17 to 2026-08-25", styles["SubTitle"]))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
story.append(Spacer(1, 10))

story.append(Paragraph(
    "This is a rollup of two completed audits: whether the bot's LinkedIn comments actually read "
    "as human, and whether the rules that are supposed to guarantee that are actually enforced by "
    "code rather than only requested in a prompt. Every finding below cites a file, a line, or a "
    "real generated comment — nothing here rests on opinion alone.",
    styles["Body"],
))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. Comment Quality Audit (2026-08-20 &ndash; 2026-08-21)", styles["H1"]))

story.append(Paragraph("Objective", styles["H2"]))
story.append(Paragraph(
    "Go from zero visibility into the bot's real LinkedIn comments to a scored, ranked failure "
    "taxonomy that Harshil and Deep can act on.", styles["Body"],
))

story.append(Paragraph("What I did", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("No audit-log CSV export existed and no comment history was reachable in a live account.", styles["Body"])),
    ListItem(Paragraph("Built <b>scripts/audit_run.py</b>: generates a real 58-comment batch through the actual production pipeline (targeting &rarr; copywriter &rarr; quality gate) against 58 synthetic prospects.", styles["Body"])),
    ListItem(Paragraph("Diagnosed why the LLM wasn't firing (comments were silently falling back to templates): an import in the harness was wiping <b>OPENROUTER_API_KEY</b> at module load. Fixed by inlining the recording transport.", styles["Body"])),
    ListItem(Paragraph("Found the configured model (<b>anthropic/claude-3.5-sonnet</b>) is not a valid OpenRouter endpoint; switched to <b>openai/gpt-4o-mini</b> to get real generations.", styles["Body"])),
    ListItem(Paragraph("Exported <b>audit_log.csv</b>, built <b>scripts/score_audit.py</b> with a self-designed structural failure taxonomy, and hand-scored all 58 comments, including the good ones.", styles["Body"])),
    ListItem(Paragraph("Traced the root cause of why the product's own quality gate missed all of this: a specific bug in <b>src/outreach/quality.py</b>.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph("Headline finding", styles["H2"]))
story.append(Paragraph(
    "The bot writes one comment: <b>validate &rarr; restate the thesis &rarr; “have you found any "
    "specific strategies?”</b> 43 of 58 comments (74%) end in that exact question shape; 25 of 58 run "
    "the full three-beat skeleton. Individually each comment reads fine &mdash; stamped on 58 different "
    "people from one account, it is an unmistakable bot fingerprint. The deterministic quality gate "
    "scored <b>all 58 of them 100/100</b>.", styles["Body"],
))

story.append(Paragraph("The specific code bug (not a summary &mdash; a named defect)", styles["H2"]))
story.append(Paragraph(
    "<b>src/outreach/quality.py, _personalization_signals(), lines 300&ndash;338.</b> The headline-match "
    "check stoplists generic business vocabulary before crediting a match (lines 324&ndash;327, via "
    "<i>_GENERIC_HEADLINE_WORDS</i>). The post-text match three lines below it (330&ndash;336) applies "
    "<b>no stoplist at all</b>: any shared 6+ letter word between the comment and the source post is "
    "credited as personalization. Every audited comment was about activation, retention, or onboarding "
    "because the post was &mdash; so this check passed automatically almost every time, including on the "
    "templated “you nailed it&hellip;have you found any specific strategies” comments.", styles["Body"],
))

story.append(Paragraph("Verdict split (58 comments)", styles["H2"]))
verdict_data = [
    [Paragraph("Good", styles["CellHead"]), Paragraph("Weak", styles["CellHead"]), Paragraph("Fail", styles["CellHead"])],
    [Paragraph("6 (10%)", styles["Cell"]), Paragraph("41 (71%)", styles["Cell"]), Paragraph("11 (19%)", styles["Cell"])],
]
t = Table(verdict_data, colWidths=[1.9 * inch] * 3)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t)
story.append(Spacer(1, 8))

story.append(Paragraph("Ranked failure taxonomy (frequency &times; severity)", styles["H2"]))
tax_header = [Paragraph(x, styles["CellHead"]) for x in ["Rank", "Failure", "n", "Freq×Sev"]]
tax_rows = [
    ["1", "formulaic_strategy_question", "43", "2425"],
    ["2", "validation_opener", "32", "2010"],
    ["3", "template_3beat", "25", "1650"],
    ["4", "no_specific_detail", "20", "1384"],
    ["5", "sycophancy", "10", "610"],
    ["6", "exclamation_hype", "2", "100"],
]
tax_data = [tax_header] + [[Paragraph(c, styles["Cell"]) for c in row] for row in tax_rows]
t = Table(tax_data, colWidths=[0.5 * inch, 2.6 * inch, 0.5 * inch, 1.0 * inch])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)
story.append(Spacer(1, 8))

story.append(Paragraph("Worst comment, verbatim (score 5/100)", styles["H2"]))
story.append(Paragraph(
    "“You're spot on about the ICP issue. It's interesting how a narrow focus can actually improve "
    "both activation and retention. Have you found any specific strategies that work well for refining "
    "ICP in a B2B context?”", styles["Quote"],
))

story.append(Paragraph("What I recommended (Section 1)", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("Stoplist the post-text personalization check the same way the headline check already is (quality.py:330&ndash;336) &mdash; a one-line fix that closes the exact hole above.", styles["Body"])),
    ListItem(Paragraph("Add an account-level repetition check: a cheap structure-overlap check across an account's pending suggestions, run before send, since <i>check_copy()</i> is stateless per call and cannot see the pattern across people.", styles["Body"])),
    ListItem(Paragraph("Extend <i>_TIRED_PHRASES</i> to the opener/closer stems found here (“you make a great point,” “have you found any specific strategies,” “spot on”) &mdash; the pattern-list mechanism already exists, it just isn't pointed at these phrases.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph(
    "Deliverables shipped: <b>audit_log.csv, audit_log_scored.csv, audit_report.md, "
    "BOT_OUTPUT_AUDIT_V1.md, RAMP_WEEK_REPORT.md, scripts/audit_run.py, scripts/score_audit.py.</b>",
    styles["Small"],
))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. Rules-vs-Reality Enforcement Audit (2026-08-24 &ndash; 2026-08-25)", styles["H1"]))

story.append(Paragraph("Objective", styles["H2"]))
story.append(Paragraph(
    "The documented comment rules are good rules &mdash; 1&ndash;3 short sentences, a hard cap around "
    "three lines, a banned-phrase list, must reference something specific. Nobody had checked whether "
    "the machine actually follows them, as opposed to merely being asked to.", styles["Body"],
))

story.append(Paragraph("Where the rules actually live in code", styles["H2"]))
story.append(Paragraph(
    "The path named in the original brief, <b>services/comment_generator.py</b>, does not exist in this "
    "repository &mdash; flagged for Harshil to confirm whether that's a stale reference. The real split is:", styles["Body"],
))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Prompt</b> &mdash; src/outreach/copy.py: <i>_STYLE_RULES</i> (lines 37&ndash;52) and <i>_task_for()</i> (lines 119&ndash;144). This is what the model is asked to do; nothing here is enforced.", styles["Body"])),
    ListItem(Paragraph("<b>Review pass</b> &mdash; src/outreach/quality.py: <i>check_copy()</i> (lines 151&ndash;297) and <i>_personalization_signals()</i> (lines 300&ndash;338). This is the only place a rule becomes real.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph("Rules-versus-reality gap table", styles["H2"]))
gap_header = [Paragraph(x, styles["CellHead"]) for x in ["Rule", "Enforced?", "Evidence"]]
gap_rows = [
    ["1–3 short sentences", "No", "No sentence-splitting/counting logic exists in check_copy() (quality.py:151-297); prompt itself says “one or two” (copy.py:139), not one to three."],
    ["Hard cap ~3 lines", "Proxy only, ~2x too loose", "COMMENT_MAX = 400 chars (quality.py:34) ≈ 6 lines at 65 chars/line. No code counts lines or \\n."],
    ["Banned phrase list", "Mechanism yes, coverage no", "_TIRED_PHRASES (quality.py:38-70) is checked (228-231) but has no entry for “spot on,” “nailed it,” “have you found any specific strategies,” or “great post.”"],
    ["Must reference something specific", "Half-enforced", "Stoplist applied to headline match (quality.py:323-327) but not to post-text match (330-336) — the exact bug in Section 1."],
    ["No flattery / no product mentions", "No", "No such check exists anywhere in check_copy(); matches the sycophancy tag on 10/58 audited comments."],
]
gap_data = [gap_header] + [[Paragraph(c, styles["Cell"]) for c in row] for row in gap_rows]
t = Table(gap_data, colWidths=[1.5 * inch, 1.1 * inch, 4.0 * inch])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t)
story.append(Spacer(1, 8))

story.append(Paragraph("Sorted by what it takes to fix", styles["H2"]))
story.append(Paragraph("<b>Prompt problems &mdash; fixable this week, no new logic:</b>", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("Extend _TIRED_PHRASES / _GENERIC_OPENERS with the phrases actually found in output. The list mechanism already runs; this is data entry.", styles["Body"])),
    ListItem(Paragraph("Fix the prompt text mismatch at copy.py:139 (“one or two” &rarr; “one to three” sentences).", styles["Body"])),
], bulletType="bullet", leftIndent=14))
story.append(Paragraph("<b>Missing-code problems &mdash; need Hemang and a booked slot:</b>", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("No sentence-count check exists at all &mdash; needs new parsing logic in check_copy().", styles["Body"])),
    ListItem(Paragraph("The char-cap-as-line-cap proxy is shared across connect/message/comment (_limit_for(), quality.py:143-148) &mdash; tightening it isn't isolated to comments.", styles["Body"])),
    ListItem(Paragraph("The post-text stoplist fix is small, but src/outreach/quality.py isn't mine to edit unilaterally &mdash; ownership decision already logged as an open ask.", styles["Body"])),
    ListItem(Paragraph("A real flattery/own-product detector doesn't exist in any form and needs design (the gate has no concept today of the account's own product/company to check against).", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph(
    "Deliverable shipped: <b>COMMENT_RULES_ENFORCEMENT_GAP.md.</b>", styles["Small"],
))

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. Forward-looking: proposed differentiation features (not yet scoped)", styles["H1"]))
story.append(Paragraph(
    "Raised for roadmap discussion, not built or estimated yet. Each targets the same root problem "
    "both audits above found: not getting flagged is not the same as being recognizably human.", styles["Body"],
))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Per-account voice fingerprinting</b> &mdash; derive style from that account's own real posts instead of one global prompt for every user.", styles["Body"])),
    ListItem(Paragraph("<b>Adversarial “would this get me caught” pass</b> &mdash; a second model judges the draft as the recipient would, catching shape problems regex-based gates miss.", styles["Body"])),
    ListItem(Paragraph("<b>Deliberate, occasional disagreement</b> &mdash; counters the uniformly-agreeable pattern this audit found in nearly every comment.", styles["Body"])),
    ListItem(Paragraph("<b>Relationship continuity across interactions</b> &mdash; reference prior engagement with the same person instead of treating every comment as stateless.", styles["Body"])),
    ListItem(Paragraph("<b>Outcome-linked style learning</b> &mdash; reweight generation based on which comment shapes actually get replies, not just which ones pass the gate.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 4 ==
story.append(Paragraph("4. Open asks / decisions needed from you", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("No real audit-log CSV export exists yet, and no comment history is reachable in a live account &mdash; every finding above is synthetic-prospect data through the real production pipeline. Recommend re-running against a live account once one is reachable to confirm the pattern holds.", styles["Body"])),
    ListItem(Paragraph("Is the quality-gate stoplist fix (Section 1) mine to ship, or does it go to whoever owns src/outreach/quality.py?", styles["Body"])),
    ListItem(Paragraph("The sentence-count and char-cap fixes (Section 2) touch logic shared with connect/message &mdash; needs Hemang's sign-off on scope before anyone starts.", styles["Body"])),
    ListItem(Paragraph("Confirm with Harshil whether services/comment_generator.py refers to a different/older codebase, since that path doesn't exist here.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 5 ==
story.append(Paragraph("5. All deliverables shipped this period", styles["H1"]))
deliv_header = [Paragraph(x, styles["CellHead"]) for x in ["File", "What it is"]]
deliv_rows = [
    ["DAILY_WORK_LOG.md", "Day-by-day log of the comment quality audit build"],
    ["RAMP_WEEK_REPORT.md", "Week 1 summary + 15-minute demo script"],
    ["BOT_OUTPUT_AUDIT_V1.md", "Primary audit: ranked taxonomy, verdict split, verbatim worst/best, quality-gate defect"],
    ["audit_log.csv / audit_log_scored.csv", "Raw and scored data underlying the audit (58 comments)"],
    ["audit_report.md", "Raw scorer output"],
    ["scripts/audit_run.py", "Re-runnable: generates comments through the real pipeline"],
    ["scripts/score_audit.py", "Re-runnable: applies the structural failure taxonomy"],
    ["COMMENT_RULES_ENFORCEMENT_GAP.md", "Rules-vs-reality gap table, code locations, prompt-vs-missing-code sort"],
    ["TASK_AUDIT_2026-08-25.pdf", "This document"],
]
deliv_data = [deliv_header] + [[Paragraph(c, styles["Cell"]) for c in row] for row in deliv_rows]
t = Table(deliv_data, colWidths=[2.3 * inch, 4.3 * inch])
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f3b52")),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbbbbb")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)

story.append(Spacer(1, 14))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "Provenance note: Section 1 and 2 findings are from the real production pipeline (targeting &rarr; "
    "copywriter &rarr; quality gate) run against synthetic prospects, since no live-account audit log "
    "was reachable. The taxonomy, the quality-gate defect, and the enforcement gaps are real regardless "
    "of data source; do not present the specific phrasing distribution as live-account data.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    title="Task Audit — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
