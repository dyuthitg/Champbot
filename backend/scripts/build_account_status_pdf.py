"""
Generates Account_Health_And_Run_Status.pdf -- written like a personal note,
first person, plain sentences, simple words. No report formatting.

Run: python scripts/build_account_status_pdf.py
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
)

OUT_PATH = "Account_Health_And_Run_Status.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's ship — the bot can't go quiet without saying so", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-09",
    styles["SubTitle"],
))

story.append(Paragraph(
    "The ask was three things: an account and run-status view, failure that's loud and specific "
    "instead of a red dot, and the daily cap and quiet-hours state shown so nobody mistakes the "
    "scheduler behaving correctly for a bug. Then prove it by breaking something on purpose. "
    "Here's what I did for each, where to look, and how I checked it.",
    styles["Body"],
))

# ------------------------------------------------------------- 1
story.append(Paragraph("1. The account and run-status view", styles["Body"]))
story.append(Paragraph(
    "This lives on the Overview page (<b>frontend/src/pages/Dashboard.tsx</b>) — it was already the "
    "screen everyone opens first, so I built into it rather than adding a second place to check. "
    "Every account card now shows, in one row: when the scheduler last touched it, whether that run "
    "was clean, today's usage against the cap for connects/messages/comments/likes, and whether "
    "quiet hours or weekend pacing is the reason it looks idle right now.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "The data comes from the same <b>/api/v1/outreach/dashboard</b> endpoint the page already called "
    "(<b>src/api/routes/outreach.py</b>) — I extended it rather than standing up a new one, so there's "
    "one source of truth instead of two dashboards that can quietly disagree.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 2
story.append(Paragraph("2. Where \"last run\" and \"last error\" actually come from", styles["Body"]))
story.append(Paragraph(
    "This was the part that didn't exist yet. The scheduler already tracked a global heartbeat, but "
    "nothing recorded, per account, whether its own last sweep worked. So every account now gets a "
    "mark left on it at the end of every tick, win or lose — see "
    "<b>src/scheduler/tick.py</b> calling <b>record_run_outcome</b> in "
    "<b>src/accounts/service.py</b>. And every place the code already changes an account's status "
    "(session rejected, LinkedIn pushed back, a re-verify) now stamps <i>when</i> that happened, not "
    "just what it changed to — that's <b>set_status</b> in the same file. That stamp is the whole "
    "reason the screen can say \"2 hours ago\" instead of \"at some point.\"",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 3
story.append(Paragraph("3. Failure is a sentence now, not a dot", styles["Body"]))
story.append(Paragraph(
    "Any account with a real problem — session expired, LinkedIn suspended it, LinkedIn pushed "
    "back, or its last run failed — shows up in a red banner at the very top of the Overview page, "
    "above the summary tiles. Not a status word: a full sentence naming the account and saying how "
    "long ago, plus a Reconnect link when that's the fix. Word for word what I tested against: "
    "“LinkedIn session expired for Demo User, 2 minutes ago.”",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 4
story.append(Paragraph("4. Caps and quiet hours, shown instead of implied", styles["Body"]))
story.append(Paragraph(
    "Each account card now has a strip of chips: how many of each action it's used today against "
    "its cap, its weekly invitation count where that applies, and — when it's true right now — a "
    "“Quiet hours” or “Weekend — reduced pace” chip that says plainly this is "
    "expected. Those two are new pure functions, <b>in_quiet_hours</b> and <b>is_weekend</b> in "
    "<b>src/accounts/caps.py</b>, read in the account's own timezone. When there's no Redis "
    "connected — like on my machine right now — the chip says “uncapped, no Redis” instead "
    "of quietly showing 0 and looking fine.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 5
story.append(Paragraph("5. How I checked it — broke a session on purpose", styles["Body"]))
story.append(Paragraph(
    "I seeded a local database with two accounts under the same identity the dev server logs in "
    "as, ran the real API and the real frontend against it, and forced one account's session to "
    "fail and its last scheduled run to error out. Then I opened the Overview page and looked, "
    "without reading a single log line.",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph(
        "The banner named the account and said <b>2 minutes ago</b> — real elapsed time, not a "
        "placeholder.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "A second banner line showed the exact run failure: <b>“send: TransportError: rate limit "
        "hit.”</b>", styles["BodyIndent"])),
    ListItem(Paragraph(
        "The account's own card carried a red “last run failed” chip alongside its caps, so "
        "the detail is still there even once you stop looking at the banner.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "The healthy account right next to it stayed green with no banner entry — so this doesn't cry "
        "wolf for accounts that are fine.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "All of that on one screen, no log file involved. I also ran the backend test suite for "
    "everything this touches — 164 tests, all passing, including new ones I wrote for this: two "
    "that break a session and a scheduled run on purpose and check the dashboard reflects it, and "
    "five for the quiet-hours/weekend math across timezones.",
    styles["Small"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 6
story.append(Paragraph("6. Where everything is", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>frontend/src/pages/Dashboard.tsx</b> — the banner and the per-account run-status row", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/api/routes/outreach.py</b> (dashboard) — last run, last error, caps today, quiet hours", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/accounts/service.py</b> — set_status and record_run_outcome, the two new stamps", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/scheduler/tick.py</b> — where every account gets marked at the end of its sweep", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/accounts/caps.py</b> — in_quiet_hours / is_weekend", styles["BodyIndent"])),
    ListItem(Paragraph("<b>tests/test_outreach_flow.py, tests/test_caps.py</b> — the break-it-on-purpose tests", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "Nothing here is committed or pushed yet — it's sitting on the branch, tested and checked "
    "in a real browser against a real (locally faked) LinkedIn session. Say the word and I'll commit "
    "it.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Account health and run status (2026-09-09)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
