"""
Generates Sep17_Process_Docs.pdf -- what I shipped on 2026-09-17: the
Comment Quality Standard v2, the Review SLA and escalation path, and my
own handover note. Written plain, first person, like I'd explain it myself.

Run: python scripts/build_process_docs_pdf.py
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

OUT_PATH = "Sep17_Process_Docs.pdf"

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

story.append(Paragraph("What I shipped today: the process I now own", styles["TitleBig"]))
story.append(Paragraph("2026-09-17", styles["SubTitle"]))

story.append(Paragraph(
    "Today's job was to turn what's been living in my head into three documents other people "
    "can point at. From here, anyone building anything social at the company can go straight to "
    "these instead of asking me directly -- that's the actual point of writing them down.",
    styles["Body"],
))

story.append(Paragraph("1. The three documents", styles["H1"]))
rows = [
    ["Document", "What it settles"],
    ["COMMENT_QUALITY_STANDARD_V2.md",
     "The standing answer to “what does a good comment look like.” Versioned (v2), dated, "
     "and it replaces the draft spec from August -- same rules, but now it says plainly which ones "
     "the code actually enforces today, not just which ones I originally wanted."],
    ["docs/REVIEW_SLA.md",
     "How fast the queue should get cleared, how deep it's allowed to get before that's a real "
     "signal, and who to escalate to -- with an expected response time next to each name, not just "
     "a name."],
    ["docs/HANDOVER_NOTE.md",
     "The stuff that's only in my head right now. Written as if I disappeared tomorrow and someone "
     "else had to pick this up cold."],
]
story.append(grid(
    [[Paragraph(c, styles["CellHead"]) for c in rows[0]]] +
    [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"])] for r in rows[1:]],
    [2.3 * inch, 4.2 * inch],
))

story.append(Paragraph("2. The one real decision I made today", styles["H1"]))
story.append(Paragraph(
    "Writing the standard forced an actual choice I'd been letting slide: my original spec from "
    "August said comments should cap at 280 characters, but the code has shipped a 400-character "
    "cap this whole time and nothing bad has come of it. Rather than let the two documents keep "
    "quietly disagreeing, v2 adopts 400 as the real number -- the number already live, not the one "
    "I guessed at before I had data.",
    styles["Body"],
))
story.append(Paragraph(
    "Two other gaps I did <b>not</b> quietly fix: the sentence-count rule still isn't enforced as a "
    "blocker, and the emoji/exclamation-mark thresholds are looser than what I originally wrote "
    "down. Both need new logic in the shared quality gate, which is Hemang's call, not something to "
    "slip in while writing documentation. Both are named as open items with his name on them and a "
    "review date, not buried.",
    styles["Body"],
))

story.append(Paragraph("What the handover note says out loud", styles["WarnHead"]))
story.append(ListFlowable([
    ListItem(Paragraph("There's exactly one reviewer on this whole project right now, and it's me. "
                        "No second approver has ever cleared an item.", styles["Body"])),
    ListItem(Paragraph("The Sep 15 live dry run -- 20 real items, a real account, Deep watching, "
                        "Harshil's written sign-off -- still hasn't actually happened. Everything "
                        "around it is ready; the session itself isn't run.", styles["Body"])),
    ListItem(Paragraph("Fixed today, in passing, while verifying the docs: the frontend/backend "
                        "repo split on Sep 16 silently broke run_golden_set.py's path to "
                        "docs/golden_set/ -- it was computing the path as if scripts/ still lived "
                        "at the repo root. Found it by actually running the command the quality doc "
                        "tells people to run, not by reading the code.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing above is committed or pushed yet -- same as always, tell me and I'll do it.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Process docs -- ship note (2026-09-17)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
