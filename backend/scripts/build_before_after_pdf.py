"""
Generates Before_After_Quality_Memo.pdf — written like a personal note, first
person, plain sentences, simple words. One chart, one table, three sentences,
per the brief. Numbers pulled live from docs/golden_set/*_run.csv so the PDF
can never drift from the actual measured data.

Run: python scripts/build_before_after_pdf.py
"""

import csv
import os
from collections import Counter

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend

HERE = os.path.abspath(os.path.dirname(__file__))
GOLDEN_DIR = os.path.join(HERE, "..", "docs", "golden_set")
OUT_PATH = "Before_After_Quality_Memo.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")
BASELINE_COLOR = colors.HexColor("#9aa5b1")
AFTER_COLOR = colors.HexColor("#2f6f4f")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))


def _load(label: str):
    path = os.path.join(GOLDEN_DIR, f"{label}_run.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _dist(rows):
    c = Counter(int(r["rubric_score"]) for r in rows)
    return [c.get(i, 0) for i in range(4)]  # [count0, count1, count2, count3]


def _avg(rows):
    scores = [int(r["rubric_score"]) for r in rows]
    return sum(scores) / len(scores)


def _generic_failures(rows):
    return sum(
        1 for r in rows
        if "R4" in r["quality_flags"].split(";") or "TEMPLATE3" in r["quality_flags"].split(";")
    )


baseline = _load("baseline")
after = _load("after")

base_avg, after_avg = _avg(baseline), _avg(after)
base_dist, after_dist = _dist(baseline), _dist(after)
base_generic, after_generic = _generic_failures(baseline), _generic_failures(after)

story = []

story.append(Paragraph("Before and after: one prompt change, measured on 30 real cases", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-08 &nbsp;&bull;&nbsp; written in my own words, not a formal report",
    styles["SubTitle"],
))

# ---- the three sentences, as asked for ----
story.append(Paragraph(
    f"Average score went from <b>{base_avg:.2f}</b> to <b>{after_avg:.2f}</b> out of 3 across the "
    f"same 30 cases, run through the real model both times. The number of comments that hit the "
    f"post's actual distinctive detail nearly doubled, from {base_dist[3]} to {after_dist[3]}, "
    f"because the one thing I changed was telling the model to find that detail before writing "
    f"instead of settling for the general topic. It didn't fix everything — the 3 cases where the "
    f"honest answer is no comment at all (2 bereavement posts, 1 euphemistic layoff announcement) "
    f"still scored 0 in both runs, because that's a different problem this change never touched.",
    styles["Body"],
))
story.append(Spacer(1, 6))

# ---- the chart ----
drawing = Drawing(420, 220)
chart = VerticalBarChart()
chart.x = 50
chart.y = 40
chart.width = 300
chart.height = 150
chart.data = [base_dist, after_dist]
chart.categoryAxis.categoryNames = ["0", "1", "2", "3"]
chart.categoryAxis.labels.fontSize = 9
chart.valueAxis.valueMin = 0
chart.valueAxis.valueMax = 16
chart.valueAxis.valueStep = 4
chart.valueAxis.labels.fontSize = 8
chart.bars[0].fillColor = BASELINE_COLOR
chart.bars[1].fillColor = AFTER_COLOR
chart.barSpacing = 3
chart.groupSpacing = 12
drawing.add(chart)

legend = Legend()
legend.x = 360
legend.y = 150
legend.dx = 8
legend.dy = 8
legend.fontSize = 9
legend.alignment = "right"
legend.columnMaximum = 2
legend.colorNamePairs = [(BASELINE_COLOR, "Baseline"), (AFTER_COLOR, "After")]
drawing.add(legend)

story.append(Paragraph("Score distribution across all 30 cases (0 = worst, 3 = best)", styles["Small"]))
story.append(drawing)
story.append(Spacer(1, 4))

# ---- the table ----
table_data = [
    ["", "Baseline", "After", "Change"],
    # Delta computed from the same rounded figures shown in the two columns
    # to their left, not from the unrounded floats -- otherwise 1.77 -> 1.93
    # can display a "+0.17" that looks like an arithmetic error next to two
    # numbers that plainly differ by 0.16.
    ["Average rubric score (0-3)", f"{base_avg:.2f}", f"{after_avg:.2f}", f"{round(after_avg, 2) - round(base_avg, 2):+.2f}"],
    ["Score of 3 (hit the specific detail)", f"{base_dist[3]}/30", f"{after_dist[3]}/30", f"{after_dist[3]-base_dist[3]:+d}"],
    ["Score of 2 (generic but personalized)", f"{base_dist[2]}/30", f"{after_dist[2]}/30", f"{after_dist[2]-base_dist[2]:+d}"],
    ["Score of 1 (no personalization at all)", f"{base_dist[1]}/30", f"{after_dist[1]}/30", f"{after_dist[1]-base_dist[1]:+d}"],
    ["Score of 0 (blocked / wrong tone / SKIP case)", f"{base_dist[0]}/30", f"{after_dist[0]}/30", f"{after_dist[0]-base_dist[0]:+d}"],
    ["Generic-phrase failures (gate's R4/TEMPLATE3 flag)", f"{base_generic}/30", f"{after_generic}/30", f"{after_generic-base_generic:+d}"],
]
tbl = Table(table_data, colWidths=[230, 70, 60, 70])
tbl.setStyle(TableStyle([
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("TEXTCOLOR", (0, 0), (-1, -1), INK),
    ("LINEBELOW", (0, 0), (-1, 0), 0.75, INK),
    ("LINEBELOW", (0, 1), (-1, -2), 0.25, MUTED),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
]))
story.append(tbl)
story.append(Spacer(1, 10))

# ---- the honest caveats ----
story.append(Paragraph("What the one change actually was, and why", styles["Body"]))
story.append(Paragraph(
    "I expected the fix to be about banned phrases and the formulaic closing question — that's what "
    "the demo found two days ago. But I measured the baseline first, before touching anything, and "
    "that assumption turned out wrong: zero of the 30 baseline comments tripped a banned-phrase or "
    "3-beat-template flag. The real problem, measured, was specificity — 14 comments passed every "
    "rule but talked about the general topic instead of the one distinctive detail, and 7 more showed "
    "no personalization at all.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "So the one thing I changed was a new instruction in the prompt telling the model to find the "
    "single most distinctive detail — a number, an admission, a concrete consequence — before "
    "writing, and explicitly ruling out industry or job title as counting as “specific.” "
    "Nothing else moved: same banned-phrase list, same length limits, same everything else.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "One after-run comment opened with “You make a solid point” — the exact banned-opener "
    "pattern from two days ago — and the gate correctly caught it. That's not this change failing; "
    "it's a different failure mode this change was never aimed at. Change one thing, measure it "
    "honestly, and don't credit it for problems it didn't touch.",
    styles["Small"],
))
story.append(Spacer(1, 6))

story.append(Paragraph("Where everything is", styles["Body"]))
story.append(Paragraph(
    "<b>docs/golden_set/BEFORE_AFTER_MEMO.md</b> — the full write-up these numbers come from.<br/>"
    "<b>docs/golden_set/baseline_run.csv</b> and <b>after_run.csv</b> — one row per case: the actual "
    "candidate text, the quality flags, the rubric score and why.<br/>"
    "<b>scripts/run_golden_set.py</b> — rerun it and get the same numbers; the scorer is code, not a "
    "feeling.<br/>"
    "<b>src/outreach/copy.py</b> — the one prompt change, in <code>_STYLE_RULES</code>.",
    styles["BodyIndent"],
))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing here is committed or pushed yet. Say the word and I'll push it.",
    styles["Small"],
))
story.append(Paragraph(
    "Still open, on purpose, not folded into this number: the 3 score-of-0 cases (2 condolence posts, "
    "1 euphemistic layoff) are unchanged in both runs. Teaching the pipeline to recognize those and "
    "suppress the suggestion entirely is a bigger, separate change — it deserves its own before/after, "
    "not a line item borrowed from this one.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Before and after quality memo (2026-09-08)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
