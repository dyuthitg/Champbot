"""
Generates Sep15_Live_Dry_Run_Status.pdf -- an honest status report for the
Sep 15 brief ("Live dry run"). This is NOT a dry-run log: the actual
session -- a real person approving 20 real items on a real account, with
Deep watching and Harshil's written sign-off -- has not happened. Writing
a log that implied it had would be exactly the thing the 100%-human-review
rule exists to prevent. What this page does instead: state plainly what's
ready, what's checked and still blocking, and the exact next steps.

Run: python scripts/build_sep15_dry_run_status_pdf.py
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

OUT_PATH = "Sep15_Live_Dry_Run_Status.pdf"

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

story.append(Paragraph("Sep 15 brief: live dry run -- where this honestly stands", styles["TitleBig"]))
story.append(Paragraph("2026-09-15 &nbsp;&bull;&nbsp; status check, not a completed run", styles["SubTitle"]))

story.append(Paragraph(
    "The Sep 15 brief asked for a real person approving at least 20 real items live, on a real "
    "disposable account, with Deep watching and Harshil's written sign-off on the blast-radius plan "
    "on record first. That session has not happened. I'm not going to write a dry-run log that "
    "implies it did -- an assistant clicking approve on my behalf, or a log reconstructed after the "
    "fact, is exactly what the 100% human-review rule in Section 6 of "
    "<b>Week3_And_Go_Live_Checklist.pdf</b> exists to prevent. This page says plainly what's ready "
    "and what's still blocking it.",
    styles["Body"],
))

story.append(Paragraph("1. What's ready to use the moment the session runs", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>docs/templates/GO_LIVE_DAY_LOG_TEMPLATE.md</b> -- written agreement, "
                        "preflight, the 20-item log, the hesitation log, the issue list, and the "
                        "go/no-go input, all in one file. Copy it, fill it in live, item by item.",
                        styles["Body"])),
    ListItem(Paragraph("<b>scripts/validate_account.py</b> (now at <b>backend/scripts/</b> after the "
                        "Sep 16 repo split) -- confirmed today that it actually runs: whoami, "
                        "profile, inbox, and activity preflight checks, and the real flag is "
                        "<b>--rotate</b>, not <b>--replace</b> as an older planning doc says.",
                        styles["Body"])),
    ListItem(Paragraph("<b>BREAK_LIST.md</b> and <b>staging_run/transcript.md</b> -- the existing "
                        "entry and narrative formats, ready to reuse for whatever the session finds.",
                        styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph("2. What I checked just now, and where it actually stands", styles["H1"]))
story.append(Paragraph(
    "Checked against the real repo and a real local run today, not against memory of the plan.",
    styles["Body"],
))
status_rows = [
    ["Owner", "What", "Status, checked today"],
    ["Dyuthi", "Create one disposable LinkedIn account", "No evidence in repo either way."],
    ["Hemang", "Real ENCRYPTION_KEY set; /healthz credentials_encryption: ok",
     "Still a placeholder in backend/.env.example; still absent from the real backend/.env."],
    ["Deep", "Redis stood up; /healthz redis: ok",
     "docker-compose.yml still wires it correctly, but Docker isn't running on this machine right "
     "now -- no live confirmation possible from here."],
    ["Dyuthi", "validate_account.py: all four preflight checks green",
     "Script runs and the flags are as documented; no run against a real account on file."],
    ["Dyuthi", "Account enrolled in warm-up at stage zero", "No evidence in repo either way."],
    ["Harshil", "Written sign-off on the Section 6 blast-radius plan", "Still not found."],
    ["Dyuthi", "First single comment sent live, watched end to end", "Not yet."],
    ["Kethan", "Sit through one live approval session", "Not yet."],
    ["Harshil &amp; Deep", "Go/no-go past one burner account", "Still scheduled for Sep 18, and "
     "Sep 18 needs today's data to mean anything."],
]
tbl = grid(
    [[Paragraph(c, styles["CellHead"]) for c in status_rows[0]]] +
    [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"]), Paragraph(r[2], styles["Cell"])]
     for r in status_rows[1:]],
    [0.85 * inch, 2.35 * inch, 3.35 * inch],
)
story.append(tbl)

story.append(Paragraph("3. Exact next steps, in order", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("Hemang sets a real ENCRYPTION_KEY and confirms /healthz shows "
                        "credentials_encryption: ok.", styles["Body"])),
    ListItem(Paragraph("Deep brings Redis up and confirms /healthz shows redis: ok.", styles["Body"])),
    ListItem(Paragraph("I create the one disposable account and run validate_account.py against it "
                        "until all four checks are green.", styles["Body"])),
    ListItem(Paragraph("Harshil's written sign-off on the blast-radius plan goes into "
                        "GO_LIVE_DAY_LOG_TEMPLATE.md §0 -- an actual reply or message, not a "
                        "checkbox.", styles["Body"])),
    ListItem(Paragraph("Only then: the real session, Deep watching, 20 real items, filled in live.",
                        styles["Body"])),
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
    title="Sep 15 live dry run -- honest status (2026-09-15)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
