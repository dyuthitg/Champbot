"""
Generates Review_Queue_Wireframes.pdf — the shipment itself: Review Queue
wireframes (list view, single item, actions, failure states, inline flags)
plus a user flow. No prep notes, no process narration — just the artifact.

Run: python scripts/build_review_queue_pdf.py
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_PATH = "Review_Queue_Wireframes.pdf"

NAVY = colors.HexColor("#2f3b52")
LINE = colors.HexColor("#bbbbbb")
STRIPE = colors.HexColor("#f4f6f8")
MUTED = colors.HexColor("#666666")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=20, leading=24, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10.5, leading=14, textColor=MUTED))
styles.add(ParagraphStyle(name="H1", fontSize=13.5, leading=17, spaceBefore=18, spaceAfter=8, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a1a")))
styles.add(ParagraphStyle(name="Body", fontSize=10, leading=15, spaceAfter=6))
styles.add(ParagraphStyle(name="Small", fontSize=8.7, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=12.5))
styles.add(ParagraphStyle(name="CellMuted", fontSize=8.3, leading=11, textColor=MUTED))
styles.add(ParagraphStyle(name="CellHead", fontSize=8.9, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle(name="FlowBox", fontSize=9.5, leading=13, alignment=1))
styles.add(ParagraphStyle(name="FlowArrow", fontSize=11, leading=13, alignment=1, textColor=MUTED))
styles.add(ParagraphStyle(name="FlowBranch", fontSize=8.5, leading=11, alignment=1, textColor=MUTED))

story = []


def box_grid(rows, col_widths, header=False):
    t = Table(rows, colWidths=col_widths)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.75, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eceef1")))
    t.setStyle(TableStyle(style))
    return t


def flow_box(text, width=3.4 * inch):
    t = Table([[Paragraph(text, styles["FlowBox"])]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#555555")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    t.hAlign = "CENTER"
    return t


def flow_arrow(branch_label=None):
    story.append(Spacer(1, 2))
    story.append(Paragraph("↓", styles["FlowArrow"]))
    if branch_label:
        story.append(Paragraph(branch_label, styles["FlowBranch"]))
    story.append(Spacer(1, 2))


# ---------------------------------------------------------------- Header ---
story.append(Paragraph("Review Queue — Wireframes &amp; Flow", styles["TitleBig"]))
story.append(Paragraph("Dyuthi T G &nbsp;&bull;&nbsp; 2026-08-28 &nbsp;&bull;&nbsp; low-fidelity, boxes and labels only", styles["SubTitle"]))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=LINE))
story.append(Spacer(1, 10))

# ============================================================== SECTION 1 ==
story.append(Paragraph("List view (default once more than 5 items are waiting)", styles["H1"]))
list_header = [Paragraph(x, styles["CellHead"]) for x in ["Select", "Who", "What we'd say", "Score", "Action"]]
list_rows = [
    ["[ ]", "Amaya Reyes\nHead of Growth · Northwind", "Comment — “This matches what I keep seeing, Amaya — the hard part is...”", "100", "[Approve] [Skip]"],
    ["[ ]", "Tom Okafor\nVP of Growth · DataForge", "Comment — “This matches what I keep seeing, Tom — the hard part is...”", "100", "[Approve] [Skip]"],
    ["[ ]", "Marcus Bell\nHead of Growth · Segmenta", "Comment — “This matches what I keep seeing, Marcus — the hard part is...”", "100", "[Approve] [Skip]"],
    ["[ ]", "Priya Sharma\nGrowth Lead · Cloudrise", "Connect — “Hi Priya, your post on activation loops was...”", "88", "[Approve] [Skip]"],
    ["—", "Daniel Hunt\nDirector · Flowbase", "Message — BLOCKED: reads as templated, no reference to their post", "—", "[Review]"],
]
list_data = [list_header] + [[Paragraph(str(c).replace("\n", "<br/>"), styles["CellMuted"] if i == 4 else styles["Cell"]) for i, c in enumerate(row)] for row in list_rows]
t = box_grid(list_data, [0.5 * inch, 1.5 * inch, 2.9 * inch, 0.5 * inch, 1.1 * inch], header=True)
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
story.append(t)
story.append(Paragraph(
    "Three rows in a row say almost the same sentence — visible at a glance, which a one-at-a-time "
    "screen could never show. The blocked row stays visible with its reason, never vanishes.",
    styles["Small"],
))
story.append(Spacer(1, 10))

# ============================================================== SECTION 2 ==
story.append(Paragraph("Single item view (opens when you click a row)", styles["H1"]))
single_rows = [
    [Paragraph("<b>Amaya Reyes</b> — Head of Growth, Northwind SaaS &nbsp;&nbsp; Match score: 100", styles["Cell"])],
    [Paragraph("Why matched: title match, industry match, seniority match", styles["CellMuted"])],
    [Paragraph("Draft: “This matches what I keep seeing, Amaya — the hard part is usually getting everyone to agree on it first. How did you handle that?”", styles["Cell"])],
    [Paragraph("Flag: near-identical to 2 other queued comments (Tom Okafor, Marcus Bell)", styles["CellMuted"])],
    [Paragraph("[ Approve &amp; schedule ] &nbsp; [ Edit ] &nbsp; [ Skip ] &nbsp;&nbsp;&nbsp;&nbsp; [ Never contact ]", styles["Cell"])],
]
story.append(box_grid(single_rows, [6.5 * inch]))
story.append(Spacer(1, 10))

story.append(Paragraph("Showing why something was flagged", styles["H1"]))
story.append(Paragraph(
    "The reason sits directly under the draft, always visible — never behind a click.",
    styles["Body"],
))
flag_rows = [
    [Paragraph("Draft: “This matches what I keep seeing, Amaya —…”", styles["Cell"])],
    [Paragraph("Flag: near-identical to 2 other queued comments", styles["CellMuted"])],
    [Paragraph("Flag: generic — doesn't reference anything specific to Amaya's post", styles["CellMuted"])],
]
story.append(box_grid(flag_rows, [6.5 * inch]))
story.append(Spacer(1, 10))

# ============================================================== SECTION 3 ==
story.append(Paragraph("Actions — routine vs. destructive", styles["H1"]))
action_header = [Paragraph(x, styles["CellHead"]) for x in ["Type", "Buttons", "Behaviour"]]
action_rows = [
    ["Routine — one tap", "[Approve]  [Edit]  [Skip]", "Happens immediately, no confirmation needed."],
    ["Destructive — two taps", "[Never contact] → “Confirm — never contact this person?” → [Confirm] [Cancel]", "A permanent action always asks first. Set apart by distance and weight, not colour alone."],
]
action_data = [action_header] + [[Paragraph(c, styles["Cell"]) for c in row] for row in action_rows]
t = box_grid(action_data, [1.4 * inch, 2.6 * inch, 2.5 * inch], header=True)
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]))
story.append(t)
story.append(Spacer(1, 10))

# ============================================================== SECTION 4 ==
story.append(Paragraph("Failure states", styles["H1"]))
fail_header = [Paragraph(x, styles["CellHead"]) for x in ["Situation", "What the screen shows"]]
fail_rows = [
    ["Nothing waiting", "“Nothing waiting for review” + a button to go import more people."],
    ["400 things waiting", "List view is forced (no one-at-a-time mode). Sort by score, plus “Approve top 20” as a safe shortcut."],
    ["A comment got blocked", "Stays visible in the list, marked blocked, with the reason shown — never silently disappears."],
    ["Connection drops mid-edit", "“Session expired — your edit is saved, reconnecting…” The unfinished edit is not lost."],
]
fail_data = [fail_header] + [[Paragraph(c, styles["Cell"]) for c in row] for row in fail_rows]
t = box_grid(fail_data, [2.0 * inch, 4.5 * inch], header=True)
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE])]))
story.append(t)
story.append(Spacer(1, 14))

# ============================================================== SECTION 5 ==
story.append(Paragraph("User flow", styles["H1"]))
story.append(Spacer(1, 4))
story.append(flow_box("Queue loads"))
flow_arrow()
story.append(flow_box("More than 5 pending?"))
flow_arrow("Yes → List view (sorted, flags visible)   ·   No → Single item view")
story.append(flow_box("Scan for flags and repetition"))
flow_arrow()
story.append(flow_box("Confident at a glance?"))
flow_arrow("Yes → Batch approve / batch skip   ·   No → Open single item")
story.append(flow_box("Read who + why + flags — all inline, no extra click"))
flow_arrow()
story.append(flow_box("Decide: Approve · Edit · Skip · Never contact (confirm first)"))
flow_arrow()
story.append(flow_box("Next item loads — or the empty state, if the queue is clear"))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    title="Review Queue Wireframes — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
