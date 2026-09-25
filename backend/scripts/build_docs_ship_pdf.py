"""
Generates Operator_Runbook_And_Voice_Guide.pdf -- maps today's three
documentation asks to the new files that satisfy them, states what's
genuinely new versus what already existed, names one real inconsistency
found while writing this, and states the verification test still owed
before Friday.

Run: python scripts/build_docs_ship_pdf.py
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

OUT_PATH = "Operator_Runbook_And_Voice_Guide.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")
WARN_AMBER = colors.HexColor("#8a6a1a")
LINE = colors.HexColor("#d8d8d8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=16.5, spaceAfter=10, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=10, leftIndent=14))
styles.add(ParagraphStyle(name="WarnHead", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=3, fontName="Helvetica-Bold", textColor=WARN_AMBER))
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

story.append(Paragraph("What ships today: the runbook, the voice guide, and the quality writeup", styles["TitleBig"]))
story.append(Paragraph("2026-09-16", styles["SubTitle"]))

story.append(Paragraph(
    "The premise for today: I'm the bottleneck on this product as long as clearing the queue, "
    "tuning the voice, or rerunning the quality check only works if I'm the one doing it. Three "
    "documents, each aimed at someone who joins next month and has never met me.",
    styles["Body"],
))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. The three asks, and what satisfies each one", styles["H1"]))
rows = [
    ["Ask", "New file", "What it covers"],
    ["Operator runbook", "docs/OPERATOR_RUNBOOK.md",
     "Clearing the queue (the four actions and what each does), the full flag "
     "glossary read straight from quality.py's rule table, what to do when a "
     "session expires, and a named escalation table."],
    ["Voice-tuning guide", "docs/VOICE_TUNING_GUIDE.md",
     "Adding/editing a brand profile (no deploy) versus changing a shared rule "
     "or the global banned-phrase list (code + deploy) -- the one distinction "
     "that determines who can make a given change without going through me."],
    ["Quality measurement method", "docs/QUALITY_MEASUREMENT_METHOD.md",
     "How the golden set, the rubric, and the runner fit together, the exact "
     "command to rerun it, and what the resulting number does and doesn't prove."],
]
story.append(grid(
    [[Paragraph(c, styles["CellHead"]) for c in rows[0]]] +
    [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"]), Paragraph(r[2], styles["Cell"])] for r in rows[1:]],
    [1.3 * inch, 1.9 * inch, 3.3 * inch],
))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. New pages versus pages that already existed", styles["H1"]))
story.append(Paragraph(
    "Two things already covered part of this ground, and the new docs point to them rather than "
    "repeat them: <b>docs/CONNECTING_AN_ACCOUNT.md</b> already has the account setup, warm-up "
    "stages, and a symptom/meaning/fix table for account problems. "
    "<b>backend/config/brand_voices/README.md</b> already explains adding a brand profile field "
    "by field. What was actually missing, and is what the two new docs add: the queue-actions "
    "and flag glossary, the escalation table, and -- the real gap -- nothing anywhere explained "
    "the difference between a per-brand change (a marketer can do it, no deploy) and a shared-rule "
    "change (needs code and a deploy). That line is now explicit in "
    "<b>VOICE_TUNING_GUIDE.md</b> §2.",
    styles["Body"],
))

story.append(Paragraph("One real inconsistency found while writing this", styles["WarnHead"]))
story.append(Paragraph(
    "Week3_And_Go_Live_Checklist.pdf's daily-check line says to run "
    "<b>validate_account.py --replace</b>. The flag actually implemented in the script is "
    "<b>--rotate</b> -- there is no <code>--replace</code>. OPERATOR_RUNBOOK.md §3 uses "
    "<b>--rotate</b> and calls out the discrepancy explicitly so whoever reads the older PDF first "
    "doesn't type a flag that doesn't exist mid-pilot.",
    styles["Body"],
))

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. The bar, and what's still owed before Friday", styles["H1"]))
story.append(Paragraph(
    "“Good” here isn't these documents existing -- it's handing the runbook to someone "
    "who has never used the tool and watching them clear five items with no help. That test needs "
    "a real second person at the keyboard, so it isn't done by writing the page; it's the next "
    "step, not a step I completed by producing this PDF.",
    styles["Body"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Sit someone who's never opened Approvals down with only "
                        "OPERATOR_RUNBOOK.md open.", styles["Body"])),
    ListItem(Paragraph("Have them clear five real items -- approve, edit, skip, whatever the "
                        "queue actually gives them.", styles["Body"])),
    ListItem(Paragraph("Every question they ask out loud is logged verbatim. A question is a gap "
                        "in the page, not a gap in them.", styles["Body"])),
    ListItem(Paragraph("Fix each logged gap in the runbook before Friday, then consider it "
                        "shipped -- not before.", styles["Body"])),
], bulletType="1", leftIndent=14))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing above is committed or pushed yet -- same as always, tell me and I'll do it.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Operator runbook and voice-tuning guide -- ship note (2026-09-16)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
