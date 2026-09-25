"""
Generates Ship_Today_Task_Map.pdf -- maps today's four go-live rules to
exactly where they live in this repo, and states plainly what the repo
shows is done vs. not done as of this morning. Written for 2026-09-16,
the first day of the Section 6 pilot window from Week3_And_Go_Live_Checklist.pdf.

Run: python scripts/build_ship_today_pdf.py
"""

import os

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

OUT_PATH = "Ship_Today_Task_Map.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")
RISK_RED = colors.HexColor("#8a2c2c")
GOOD_GREEN = colors.HexColor("#2f6f4f")
WARN_AMBER = colors.HexColor("#8a6a1a")
LINE = colors.HexColor("#d8d8d8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="H2", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=16.5, spaceAfter=10, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=16.5, spaceAfter=6, leftIndent=14, textColor=INK))
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

# ============================================================== TITLE ==
story.append(Paragraph("Ship-today task map: the four rules, mapped to this repo", styles["TitleBig"]))
story.append(Paragraph("2026-09-16 &nbsp;&bull;&nbsp; first day of the Section 6 pilot window", styles["SubTitle"]))

story.append(Paragraph(
    "This is not a new plan. Everything below already exists in "
    "<b>Week3_And_Go_Live_Checklist.pdf</b> (the Section 4 owner list and the Section 6 "
    "blast-radius plan). What this page does is take today's four rules and point each one "
    "at the exact file, script, or checklist line that satisfies it, and say plainly what the "
    "repo shows is actually done this morning versus still open.",
    styles["Body"],
))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. The four rules, and where each one lives", styles["H1"]))

rule_rows = [
    ["Rule", "Where it lives in this repo"],
    ["Get the account and blast radius agreed in writing before you start.",
     "Week3_And_Go_Live_Checklist.pdf, Section 6 (the plan) and Section 4, row "
     "“Harshil: read and sign off…”. The new §0 in "
     "<b>GO_LIVE_DAY_LOG_TEMPLATE.md</b> is where the actual written yes gets pasted in — "
     "not a checklist checkbox, the real reply."],
    ["Approve at least twenty real items live.",
     "The real review queue: frontend <b>Approvals.tsx</b> against the backend review-queue "
     "API, on the account created per Section 4 row 1. Logged item-by-item in "
     "<b>GO_LIVE_DAY_LOG_TEMPLATE.md</b> §2. This is the one rule on this page nobody but the "
     "human at the keyboard can execute — see Section 2 below."],
    ["Log every hesitation, not just every error.",
     "New: nothing in the repo captured this before today. <b>GO_LIVE_DAY_LOG_TEMPLATE.md</b> "
     "§3 is a plain table — item #, what caused the pause, how long, what would remove it — "
     "filled in live, not reconstructed from memory afterward."],
    ["Ship today: dry-run log with the issue list, and written approval on record.",
     "Same shapes the repo already uses: the transcript style of "
     "<b>staging_run/transcript.md</b> for the run narrative, the entry style of "
     "<b>BREAK_LIST.md</b> for each issue, and §0 / §6 of "
     "<b>GO_LIVE_DAY_LOG_TEMPLATE.md</b> for the written sign-off, dated and named."],
]
story.append(grid(
    [[Paragraph(c, styles["CellHead"]) for c in rule_rows[0]]] +
    [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"])] for r in rule_rows[1:]],
    [2.35 * inch, 4.2 * inch],
))
story.append(Spacer(1, 6))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. The one rule I can't run for you", styles["H1"]))
story.append(Paragraph(
    "“Approve at least twenty real items live” only means something if the approval is a "
    "real human, logged into the real account, making a real judgment call — that's the "
    "entire reason Section 6 requires 100% human review with no exceptions for “obviously "
    "fine” ones. An assistant clicking approve on your behalf would be exactly the thing the "
    "rule exists to prevent, so I'm not going to simulate it or write a log that implies it "
    "happened when it didn't. What I've done instead is get everything around that step ready: "
    "the log template, the status check below, and this map — so the only thing left for the "
    "session itself is the twenty approvals.",
    styles["Body"],
))

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. Where the Section 4 checklist actually stands this morning", styles["H1"]))
story.append(Paragraph(
    "Checked against the repo, not against memory of the plan. “No evidence in repo” means "
    "exactly that — it may well be done in an account or environment I can't see from here; it "
    "just isn't provable from what's checked in.",
    styles["Body"],
))
status_rows = [
    ["Owner", "What", "Status this morning"],
    ["Dyuthi", "Create one disposable LinkedIn account", "No evidence in repo either way."],
    ["Hemang", "Real ENCRYPTION_KEY set; /healthz credentials_encryption: ok",
     "backend/.env.example still has the placeholder value; no confirmation found."],
    ["Deep", "Redis stood up; /healthz redis: ok",
     "docker-compose.yml wires REDIS_URL by default; no run confirmation found."],
    ["Dyuthi", "validate_account.py: all four preflight checks green", "No run output found in repo."],
    ["Dyuthi", "Account enrolled in warm-up at stage zero", "No evidence in repo either way."],
    ["Harshil", "Written sign-off on the Section 6 blast-radius plan",
     "Not found — this is the §0 line in the new log template."],
    ["Dyuthi", "First single comment sent live, watched end to end", "Not yet — today's session."],
    ["Dyuthi", "Daily session-validity check on the account", "N/A until the account exists."],
    ["Kethan", "Sit through one live approval session", "Not yet — today's session."],
    ["Harshil &amp; Deep", "Go/no-go past one burner account", "Scheduled for Sep 18, after today's data."],
]
tbl = grid(
    [[Paragraph(c, styles["CellHead"]) for c in status_rows[0]]] +
    [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"]), Paragraph(r[2], styles["Cell"])]
     for r in status_rows[1:]],
    [0.85 * inch, 2.55 * inch, 3.15 * inch],
)
story.append(tbl)
story.append(Spacer(1, 6))
story.append(Paragraph(
    "Recommendation: don't run the twenty live approvals until the three infra rows "
    "(ENCRYPTION_KEY, Redis, validate_account.py) are actually green and Harshil's sign-off is "
    "on record. Section 6 exists precisely so speed doesn't quietly replace those checks.",
    styles["Small"],
))

# ============================================================== SECTION 4 ==
story.append(Paragraph("4. What's ready to use right now", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph(
        "<b>docs/templates/GO_LIVE_DAY_LOG_TEMPLATE.md</b> — one file covering written "
        "agreement, preflight, the twenty-item log, the hesitation log, the issue list, and the "
        "go/no-go input. Copy it, fill it in live.", styles["Body"])),
    ListItem(Paragraph(
        "<b>BREAK_LIST.md</b> — the existing entry format (severity, what happened, evidence, "
        "fixed today or not) for anything today's session breaks.", styles["Body"])),
    ListItem(Paragraph(
        "<b>staging_run/transcript.md</b> — the existing narrative shape for a run log, if "
        "today's dry-run portion is worth recording the same way.", styles["Body"])),
    ListItem(Paragraph(
        "<b>scripts/validate_account.py</b> — the one command for connect-and-preflight; "
        "read-only until all four checks are green.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing in this document is itself the written approval — it's the map to where that "
    "approval, and today's twenty items, get recorded once the session actually runs.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Ship-today task map (2026-09-16)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
