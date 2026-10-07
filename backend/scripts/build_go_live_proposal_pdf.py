"""
Generates Go_Live_Proposal.pdf — plain-language version of the Weeks 2-4
go-live proposal: what's broken, the plan, the dates, who's needed, and
what's deliberately being skipped.

Run: python scripts/build_go_live_proposal_pdf.py
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

OUT_PATH = "Go_Live_Proposal.pdf"

NAVY = colors.HexColor("#2f3b52")
LINE = colors.HexColor("#bbbbbb")
STRIPE = colors.HexColor("#f4f6f8")
MUTED = colors.HexColor("#666666")
RED = colors.HexColor("#a8362f")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=20, leading=24, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10.5, leading=14, textColor=MUTED))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=18, spaceAfter=8, fontName="Helvetica-Bold", textColor=colors.HexColor("#1a1a1a")))
styles.add(ParagraphStyle(name="H2", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=4, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="Body", fontSize=10, leading=15, spaceAfter=6))
styles.add(ParagraphStyle(name="Quote", fontSize=9.6, leading=14, leftIndent=14, textColor=colors.HexColor("#333333"), spaceAfter=4, fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="Small", fontSize=8.7, leading=12, textColor=MUTED))
styles.add(ParagraphStyle(name="Cell", fontSize=9, leading=12.5))
styles.add(ParagraphStyle(name="CellHead", fontSize=8.9, leading=11.5, fontName="Helvetica-Bold", textColor=colors.white))
styles.add(ParagraphStyle(name="Ask", fontSize=10.5, leading=15, spaceAfter=6, backColor=colors.HexColor("#f7e6da")))

story = []


def grid(rows, col_widths, header_bg=NAVY):
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


# ---------------------------------------------------------------- Header ---
story.append(Paragraph("What It Takes To Get This Bot Live", styles["TitleBig"]))
story.append(Paragraph("Dyuthi T G &nbsp;&bull;&nbsp; 2026-08-28 &nbsp;&bull;&nbsp; covers Weeks 2&ndash;4 (Aug 31 &ndash; Sep 18)", styles["SubTitle"]))
story.append(Spacer(1, 6))
story.append(HRFlowable(width="100%", thickness=1, color=LINE))
story.append(Spacer(1, 10))

story.append(Paragraph(
    "Short version: the bot writes the same comment over and over, and there's no screen where a "
    "human checks it before it posts. That's the whole reason this hasn't gone live. Below is my plan "
    "to fix that, with real dates attached.", styles["Body"],
))

story.append(Paragraph(
    "<b>The ask:</b> Approve this plan by Monday, Sep 1, so Week 2 starts on time. If something here "
    "is wrong, tell me which one thing it is — a date, a person, or the plan itself — not “redo it.”",
    styles["Ask"],
))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. What's actually broken", styles["H1"]))
story.append(Paragraph("In order of what actually stops us from going live:", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("The review screen shows one item at a time. There's no way to notice that 9 of 10 comments waiting are basically the same comment.", styles["Body"])),
    ListItem(Paragraph("The system that's supposed to catch bad comments gave all 58 test comments a perfect score, including the worst ones. One specific piece of code is missing a check that a very similar piece of code right next to it already has.", styles["Body"])),
    ListItem(Paragraph("For roughly the first two weeks of any new account's life, the “who should I contact” button returns nothing at all, and blames the wrong reason when it fails.", styles["Body"])),
    ListItem(Paragraph("A button called “never contact this person again” — which is permanent — fires the moment you tap it, no “are you sure.”", styles["Body"])),
    ListItem(Paragraph("The Warm-up screen shows a made-up activity log (comments, messages, likes) as if it already happened, while every real number on the same account says zero.", styles["Body"])),
    ListItem(Paragraph("Connecting an account today means digging into your browser's developer tools and copying login codes by hand — the only way in that currently exists.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. The plan I'm recommending", styles["H1"]))
story.append(Paragraph(
    "I looked at three ways to do this and picked one. Here's the pick, and the two I said no to.",
    styles["Body"],
))
plan_rows = [
    ["Fix everything, in order", "No — most of it (like ugly pages nobody's blocked on) doesn't need to happen before going live. It would burn two weeks for no real benefit."],
    ["Fix the two broken pieces first, build the new screen, then test it live with a real person (chosen)", "Cheap fixes first, unblocks everything else. Ship something people can actually click fast. Check it against real feedback before adding more."],
    ["Build the perfect version all at once", "No — too much guessing before we've even talked to Kethan once. Week 2 would end with nothing anyone could try."],
]
t = grid([[Paragraph(x, styles["CellHead"]) for x in ["Option", "Why / why not"]]] +
         [[Paragraph(a, styles["Cell"]), Paragraph(b, styles["Cell"])] for a, b in plan_rows],
         [2.3 * inch, 4.2 * inch])
story.append(t)

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. Dates I'm committing to", styles["H1"]))

story.append(Paragraph("Week 2 (Aug 31 &ndash; Sep 4) &mdash; get the basics working", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Mon Sep 1</b> — talk to Kethan, check my guesses against reality.", styles["Body"])),
    ListItem(Paragraph("<b>Wed Sep 2</b> — the two backend fixes are done and checked by Deep.", styles["Body"])),
    ListItem(Paragraph("<b>Fri Sep 4</b> — the new review screen works: approve, edit, skip, with a confirm step before anything permanent. Built together with Hemang.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph("Week 3 (Sep 7 &ndash; Sep 11) &mdash; the part that catches repeats", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Wed Sep 9</b> — the screen can spot near-identical comments before you approve them.", styles["Body"])),
    ListItem(Paragraph("<b>Fri Sep 11</b> — the broken-day scenarios are handled: empty queue, 400 things waiting, a blocked comment, a dropped connection.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Paragraph("Week 4 (Sep 14 &ndash; Sep 18) &mdash; prove it, then decide", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Tue Sep 15</b> — works properly on a phone.", styles["Body"])),
    ListItem(Paragraph("<b>Sep 16&ndash;17</b> — a real person (Kethan) uses it for a full day, for real.", styles["Body"])),
    ListItem(Paragraph("<b>Fri Sep 18</b> — go/no-go meeting with Harshil and Deep.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 4 ==
story.append(Paragraph("4. Who I need, and exactly what I'm asking for", styles["H1"]))
dep_rows = [
    ["Hemang", "Two specific 3-hour blocks: Mon Sep 1, 10am&ndash;1pm and Wed Sep 3, 10am&ndash;1pm. Just the new review screen, nothing else, so it's boundable."],
    ["Deep", "Check and approve the two backend fixes by Wed Sep 2. Also help plan the “spot a repeat comment” logic, since it extends code he already owns."],
    ["Harshil", "Approve this plan by Sep 1. Attend the demo (Section 6) and the Sep 18 go/no-go."],
    ["Kethan", "Two sessions: Sep 1 to check my guesses, Sep 16&ndash;17 to actually use the finished screen for a day."],
]
t = grid([[Paragraph(x, styles["CellHead"]) for x in ["Person", "What I'm asking for"]]] +
         [[Paragraph(a, styles["Cell"]), Paragraph(b, styles["Cell"])] for a, b in dep_rows],
         [1.3 * inch, 5.2 * inch])
story.append(t)
story.append(Spacer(1, 8))
story.append(Paragraph(
    "<b>One thing I don't know yet:</b> who owns the login setup we'd need for the real Week 4 test "
    "(not the workaround I used for testing). Flagging this now instead of finding out on Sep 15 — "
    "need a name by Sep 4.", styles["Body"],
))
story.append(Paragraph("Message I'm sending Hemang today:", styles["H2"]))
story.append(Paragraph(
    "“Hey Hemang — could I get you for two 3-hour blocks next week: Mon Sep 1 10–1 and Wed "
    "Sep 3 10–1? Scope is just the new review-screen card (approve/edit/skip plus a confirm step "
    "on one risky action) — I'll have the sketches and the technical details ready beforehand so "
    "it's a build session, not a design one. Let me know today if either slot clashes with your other "
    "work so I can replan.”", styles["Quote"],
))

# ============================================================== SECTION 5 ==
story.append(Paragraph("5. What I'm choosing not to do, and why", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("Not fixing the ugly, broken Agents page. Recommending it gets removed from the menu instead, until someone actually owns rebuilding it — a broken page one click away is worse than no page. It doesn't stop us from going live either way.", styles["Body"])),
    ListItem(Paragraph("Not building an easier way to connect an account (like a normal login button) this round. Copying login codes by hand is a one-time annoyance per person right now — worth fixing later, once there are more people using this.", styles["Body"])),
    ListItem(Paragraph("Not building file/CSV upload for adding prospects. The current copy-paste box is good enough at our current size. The real problem was not being able to see who got imported, and that gets fixed by the new list screen instead.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

# ============================================================== SECTION 6 ==
story.append(Paragraph("6. Week 1 report and the 15-minute demo", styles["H1"]))
story.append(Paragraph(
    "What shipped this week: a comment-quality audit (58 real comments checked by hand), a full "
    "interface audit (every screen, on desktop and phone), and the wireframes for the fix. This plan "
    "is what comes after all three.", styles["Body"],
))
story.append(Paragraph("Demo order: problem first, then the fix.", styles["H2"]))
story.append(Paragraph("Read out loud, worst comment the bot wrote (real score: 5 out of 100):", styles["Body"]))
story.append(Paragraph(
    "“You're spot on about the ICP issue. It's interesting how a narrow focus can actually improve "
    "both activation and retention. Have you found any specific strategies that work well for refining "
    "ICP in a B2B context?”", styles["Quote"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Name the exact bug that let it score 100/100 anyway.", styles["Body"])),
    ListItem(Paragraph("Show that the review screen, as it exists today, could never have caught this.", styles["Body"])),
    ListItem(Paragraph("Show the wireframe of the screen that would catch it.", styles["Body"])),
    ListItem(Paragraph("Ask for the plan above to be approved.", styles["Body"])),
], bulletType="bullet", leftIndent=14))

story.append(Spacer(1, 14))
story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "If Monday's conversation with Kethan changes a core assumption in the wireframes, I'll say so "
    "that same day and the Week 2 dates will move. The backend fixes and the people I've asked for "
    "help don't depend on that conversation, so those stay on schedule regardless.", styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    topMargin=0.7 * inch, bottomMargin=0.7 * inch,
    title="Go-Live Proposal — Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
