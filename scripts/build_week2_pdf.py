"""
Generates Week_2_Demo_And_Breaks.pdf — written like a personal note, first
person, plain sentences, simple words. No report formatting.

Run: python scripts/build_week2_pdf.py
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

OUT_PATH = "Week_2_Demo_And_Breaks.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's work — the whole thing running, start to finish", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-04 &nbsp;&bull;&nbsp; written in my own words, not a formal report",
    styles["SubTitle"],
))

story.append(Paragraph(
    "Three things to ship today: run the whole loop on a staging account, record a short "
    "walkthrough, and write down everything that broke — plus the week 2 report. Here's what "
    "actually happened, starting with the part you'd want to poke at first.",
    styles["Body"],
))

# ------------------------------------------------------------- the caveat
story.append(Paragraph("First, the bit I'd rather tell you than have you find", styles["Body"]))
story.append(Paragraph(
    "The comment in the demo really does go all the way — the system finds the person, finds "
    "what they posted, writes the reply, checks it, I read it and approve it, and it gets sent. "
    "The sending part is a real request, built by the real code, with the real login headers.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "But that request goes to a little pretend LinkedIn I wrote, running on my own machine. "
    "<b>Not to the actual LinkedIn.</b> We still have no LinkedIn account we're allowed to test "
    "against, and nothing in this whole system has ever touched the real thing. That hasn't "
    "changed since week 1, and it's the single most important sentence in this document.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "I could have hidden that behind a fake “it worked!” message. I'd rather the pretend LinkedIn "
    "be obvious, because it means the parts we CAN prove are genuinely proven: the request really "
    "gets built, really gets sent, and the answer really gets read back. That's where the "
    "breakages hide, and a pretend shortcut would have proved none of it.",
    styles["Small"],
))

# ------------------------------------------------------------- 1
story.append(Paragraph("1. The loop runs, end to end, in about fifteen seconds", styles["Body"]))
story.append(Paragraph(
    "One command does the lot: find the people, find their posts, write the comments, flag them, "
    "show me the queue, take my approval, and send. There's a “practice mode” that does everything "
    "except the sending — I ran that first, which is how most of today's problems got found before "
    "anything was recorded.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 2
story.append(Paragraph("2. The biggest thing I found: a whole step was missing", styles["Body"]))
story.append(Paragraph(
    "The system can't comment on a post unless it knows what the post says. Fair enough. But "
    "<b>nothing in the system was ever going and getting the post.</b> It only worked if a human "
    "had already typed the post into the spreadsheet by hand.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "It looked like a finished feature because every test and every script we'd written happened "
    "to supply the post itself. You only notice when you try to run the real thing with nothing "
    "but a list of profile links — which is what a real list looks like. So I built that step "
    "today. Give it a column of links, it goes and finds out who those people are and what they "
    "recently posted. It only reads, it never posts anything, and it won't offer up a post we've "
    "already commented on.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 3
story.append(Paragraph("3. Our own rulebook had never been typed into the code", styles["Body"]))
story.append(Paragraph(
    "Back on 25 August I wrote down a list of banned phrases and marked it “easy, do this week, "
    "no new code needed.” It never got done. So for ten days the written rule and the actual "
    "check were two different documents.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "The run made that obvious in about a second: <b>three of the first five comments opened with "
    "“You make a solid point…”</b>, which is right there on my banned list, and the checker said "
    "nothing at all. Now it's wired in, plus a test that fails if any of those phrases ever quietly "
    "stops being checked.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 4
story.append(Paragraph("4. My own test rig lied to me, so I made it argue with itself", styles["Body"]))
story.append(Paragraph(
    "The very first practice run said “no problems found” — while approving a comment that started "
    "by flattering the person and ended with the exact copy-paste question my August audit is "
    "named after. Scored 100 out of 100. Green light.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "A test that can wave that through isn't testing anything. So now, after the comment is "
    "approved, the run grades it a second time using the completely separate scoring I wrote in "
    "August — which knows nothing about the main checker. <b>When the two disagree, the run records "
    "it as a problem.</b> They've disagreed on every single run since, which is exactly the point.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 5
story.append(Paragraph("5. Everything that broke — twelve things, written down", styles["Body"]))
story.append(Paragraph(
    "You said the break list is worth more than the demo, and honestly it was. Six of them I fixed "
    "today with tests; five are written up with what I'd do about them and who needs to decide; "
    "one isn't really a bug at all. A few of the good ones:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph(
        "A rule that catches “<i>have</i> you <i>noticed</i> any…” didn't catch “<i>did</i> you "
        "<i>notice</i> any…” — same sentence, different tense. Fixed.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "“NRR?” got flagged as SHOUTING but plain “NRR” didn't — a question mark was tipping a "
        "three-letter abbreviation over a length limit. Fixed, and I added the abbreviations our "
        "own customers actually use.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "The bot wrote “At Champions Ranch, we've seen…” into a stranger's comment thread — "
        "advertising ourselves, which my own rules ban — and nothing stopped it. Not fixed: the "
        "checker doesn't currently know our own company name. Written up.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "If you skip a comment and then refresh the page within five seconds, <b>the skip silently "
        "doesn't happen</b> and the comment comes back. I only found this because it happened to me "
        "while recording. Written up with a fix.", styles["BodyIndent"])),
    ListItem(Paragraph(
        "Importing a plain list of profile links gives you an empty queue and no explanation, "
        "because the system scores people before it knows anything about them. Written up.",
        styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

# ------------------------------------------------------------- 6
story.append(Paragraph("6. The thing I most want you to know", styles["Body"]))
story.append(Paragraph(
    "The moment I banned “You make a solid point”, the very next run came back with <b>four out of "
    "five comments opening with “It's interesting how…”</b> instead. Same job, same canned feeling, "
    "not on any list.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "That's my August argument happening in front of me inside one working day: banning exact "
    "phrases is whack-a-mole, and banning the <i>shape</i> of the sentence is the thing that "
    "actually holds. It's why next week I'd rather widen the shape rule than keep adding words to "
    "a list.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ------------------------------------------------------------- 7
story.append(Paragraph("7. The video — 2 minutes 19", styles["Body"]))
story.append(Paragraph(
    "Real screen, real comments the model wrote this morning, real posts the system went and found. "
    "It shows me skipping one that's flagged, typing why, approving a clean one, and then the one "
    "from earlier that went all the way. The words on screen are what I'm thinking, not what the "
    "buttons do. It ends on the pretend-LinkedIn caveat, on purpose.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "Two honest notes. It's captions, not my voice — I've written the script out separately if you "
    "want it read aloud. And it's a .webm file, not .mp4, because the video tool on this machine "
    "can't make mp4s; it plays fine in any browser or VLC.",
    styles["Small"],
))
story.append(Paragraph(
    "I had to re-record it twice. First take, the script approved a comment while my own caption "
    "said “this one's clean” — it wasn't, it had two flags on it. A demo whose narration argues "
    "with its own screen is worse than no demo, so I made the script read the real queue and pick "
    "a genuinely bad one and a genuinely good one before it says a word.",
    styles["Small"],
))

# ------------------------------------------------------------- 8
story.append(Paragraph("8. Where everything is", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Week2_Demo_Walkthrough.webm</b> — the video", styles["BodyIndent"])),
    ListItem(Paragraph("<b>BREAK_LIST.md</b> — all twelve, with evidence for each", styles["BodyIndent"])),
    ListItem(Paragraph("<b>WEEK2_REPORT.md</b> — the week 2 report, gaps first", styles["BodyIndent"])),
    ListItem(Paragraph("<b>docs/DEMO_NARRATION.md</b> — the script, timed, if you want voice", styles["BodyIndent"])),
    ListItem(Paragraph("<b>scripts/staging_run.py</b> — the whole loop, re-runnable, with practice mode", styles["BodyIndent"])),
    ListItem(Paragraph("<b>staging_run/</b> — what the last run did, and every LinkedIn call it made", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "277 tests pass, including 13 new ones today. Nothing is committed or pushed yet — it's all "
    "sitting here, tested and running. Say the word and I'll push it.",
    styles["Small"],
))
story.append(Paragraph(
    "And the one thing I need from you, not from more of my time: a burner LinkedIn account we're "
    "allowed to break, so next week that pretend LinkedIn can become the real one.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Week 2 — demo, breaks and report (2026-09-04)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
