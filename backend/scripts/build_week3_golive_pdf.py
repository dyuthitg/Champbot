"""
Generates Week3_And_Go_Live_Checklist.pdf -- written like a personal note,
first person, plain sentences, simple words. Covers: this week's before/after
numbers, what shipped, the demo plan, the go-live checklist (named owners,
no team names), the risks stated honestly, and the first-account/blast-radius
proposal.

Run: python scripts/build_week3_golive_pdf.py
"""

import csv
import os
from collections import Counter

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

HERE = os.path.abspath(os.path.dirname(__file__))
GOLDEN_DIR = os.path.join(HERE, "..", "docs", "golden_set")
OUT_PATH = "Week3_And_Go_Live_Checklist.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")
RISK_RED = colors.HexColor("#8a2c2c")
GOOD_GREEN = colors.HexColor("#2f6f4f")
LINE = colors.HexColor("#d8d8d8")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="H1", fontSize=14, leading=18, spaceBefore=16, spaceAfter=8, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="H2", fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=4, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=16.5, spaceAfter=10, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=16.5, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=10, leftIndent=14))
styles.add(ParagraphStyle(name="RiskHead", fontSize=11.5, leading=15, spaceBefore=10, spaceAfter=3, fontName="Helvetica-Bold", textColor=RISK_RED))
styles.add(ParagraphStyle(name="Cell", fontSize=9.3, leading=12.5, textColor=INK))
styles.add(ParagraphStyle(name="CellHead", fontSize=9.3, leading=12.5, textColor=colors.white, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="Quote", fontSize=10, leading=15, leftIndent=14, spaceAfter=10, textColor=INK, fontName="Helvetica-Oblique"))


def grid(rows, col_widths, header_bg=INK):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("FONTSIZE", (0, 0), (-1, -1), 9.3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f6f6")]),
    ]))
    return t


def _load(label):
    with open(os.path.join(GOLDEN_DIR, f"{label}_run.csv"), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _dist(rows):
    c = Counter(int(r["rubric_score"]) for r in rows)
    return [c.get(i, 0) for i in range(4)]


def _avg(rows):
    scores = [int(r["rubric_score"]) for r in rows]
    return sum(scores) / len(scores)


baseline = _load("baseline")
after = _load("after")
base_avg, after_avg = _avg(baseline), _avg(after)
base_dist, after_dist = _dist(baseline), _dist(after)

story = []

# ============================================================== TITLE ==
story.append(Paragraph("Week 3: the numbers, the checklist, and the first live account", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-11",
    styles["SubTitle"],
))

# ============================================================== SECTION 1 ==
story.append(Paragraph("1. The numbers first, because I've earned that this week", styles["H1"]))
story.append(Paragraph(
    f"The one prompt change I tested this week moved the real quality score from "
    f"<b>{base_avg:.2f}</b> to <b>{after_avg:.2f}</b> out of 3, on the same 30 real "
    f"cases, run through the real model both times, not a guess. The comments that "
    f"actually land on the post's one distinctive detail nearly doubled, "
    f"{base_dist[3]} to {after_dist[3]}. Full numbers are in "
    f"<b>Before_After_Quality_Memo.pdf</b> already on your desktop &mdash; I'm not "
    f"repeating the chart here, just leading with the headline because it's real "
    f"and it's this week's.",
    styles["Body"],
))
story.append(Paragraph(
    "Second number, less flattering but just as real: every single boot of this app "
    "on Railway was crashing before it served one request &mdash; the migration files "
    "just weren't in the image. That's now three small, boring fixes (copy the "
    "migration files in, add the Postgres driver, stop crashing when an old campaign "
    "has no organization) and it boots clean. I'm including it because \"it's up\" is "
    "a before/after number too, and it was false all week until Wednesday.",
    styles["Body"],
))
story.append(Paragraph(
    "Third: brand voice profiles (below) have 23 real tests passing, and the people-and-post "
    "finder from last week has 8. I ran both again this morning before writing this, not "
    "just trusting my memory of the last time they passed.",
    styles["Small"],
))

# ============================================================== SECTION 2 ==
story.append(Paragraph("2. What shipped this week", styles["H1"]))
ships = [
    ("Account &amp; run-status board", "You can now see, per account, when it last ran, what "
     "broke, how much of today's sending limit is used, and whether it's in quiet hours &mdash; "
     "with a loud banner instead of a status dot you have to guess about."),
    ("Targeting discovery", "Give it a profile link and it finds the person and their most "
     "recent post on its own. Before this, someone had to paste the post text in by hand or "
     "the queue came back empty with no explanation."),
    ("Guardrail flags in the queue", "Every held-back comment now says exactly which rule it "
     "broke, in plain words, and you can filter the queue by reason instead of opening each one."),
    ("Brand voice as a config file", "A marketer can now give a brand its own voice &mdash; how "
     "formal, how many sentences, which words to avoid, real example comments &mdash; by saving "
     "a file, no engineer and no deploy involved. Two real ones ship today: one formal (Lake B2B), "
     "one casual (Loopwork), proving the same six settings stretch to cover both. Built and "
     "tested (23 tests, all passing) but not committed yet &mdash; same as always, I'm waiting "
     "on your go-ahead before it goes in."),
    ("Two review-screen states that used to look identical", "\"Nothing generated yet\" (a "
     "brand-new account, nothing has run) and \"You're caught up\" (plenty has run and it's all "
     "decided) used to both show the exact same blank screen. They're now told apart. Built "
     "today and unit-tested; I have <b>not</b> clicked through it live in the browser yet, so "
     "I'm flagging that honestly rather than calling it proven."),
]
for name, body in ships:
    story.append(Paragraph(f"<b>{name}.</b> {body}", styles["BodyIndent"]))

# ============================================================== SECTION 3 ==
story.append(Paragraph("3. The demo, in the order I'd run it", styles["H1"]))
story.append(ListFlowable([
    ListItem(Paragraph("Open the account board first &mdash; it's the thing people were "
                        "squinting at a status dot for last week.", styles["Body"])),
    ListItem(Paragraph("On Targeting, paste in a profile link live and let it find the "
                        "person and their latest post in front of you, not a screenshot of "
                        "it working earlier.", styles["Body"])),
    ListItem(Paragraph("In the queue, filter by one guardrail reason and show a held-back "
                        "comment next to why it was held back.", styles["Body"])),
    ListItem(Paragraph("Pick one target, generate a comment with no brand voice set, then "
                        "set a brand voice on that same profile and generate again &mdash; "
                        "same person, same post, two visibly different comments.", styles["Body"])),
    ListItem(Paragraph("Close on the golden-set number from Section 1. It's the one thing "
                        "in this whole demo that's a measured before/after and not a "
                        "screenshot of a feature.", styles["Body"])),
], bulletType="1", leftIndent=14))
story.append(Paragraph(
    "I'll reuse <b>Account_Health_Live_Walkthrough.webm</b> for step 1 since nothing changed "
    "there, and record fresh for steps 2 through 4 since brand voice and the frontend side of "
    "discovery are new since the last recording.",
    styles["Small"],
))

# ============================================================== SECTION 4 ==
story.append(Paragraph("4. Go-live checklist &mdash; one name per line, on purpose", styles["H1"]))
story.append(Paragraph(
    "Every line below has one person's name, not a team's, because \"Ops\" can't tell me it's "
    "done and a name can. Some of these are mine and some genuinely aren't &mdash; I'm keeping "
    "the ones that aren't in, because a checklist that only lists my own work isn't a checklist, "
    "it's a diary.",
    styles["Body"],
))
checklist_rows = [
    ["Owner", "What"],
    ["Dyuthi", "Create one brand-new, disposable LinkedIn account &mdash; not anyone's real profile."],
    ["Hemang", "Set a real ENCRYPTION_KEY in the environment and confirm /healthz reports credentials_encryption: ok."],
    ["Deep", "Stand up the Redis instance for this environment and confirm /healthz reports redis: ok. Sending stays refused until this is true &mdash; that's by design, not a bug to route around."],
    ["Dyuthi", "Run scripts/validate_account.py against that account's cookies and get all four preflight checks green (whoami, profile, inbox, activity) before anything writes."],
    ["Dyuthi", "Enroll the account in the warm-up program from day zero. No skipping stages because the profile looks established &mdash; that's the exact thing that gets accounts restricted."],
    ["Harshil", "Read and sign off on the blast-radius plan in Section 6 before the first real send happens."],
    ["Dyuthi", "Send the first single comment, approved by a human, and watch it happen live end to end &mdash; not queued and checked later."],
    ["Dyuthi", "Check that account's session is still valid every morning of the pilot. Re-run validate_account.py --replace the moment it isn't, before anything else runs that day."],
    ["Kethan", "Sit through at least one live approval session and say, as someone who didn't build it, whether the queue makes sense."],
    ["Harshil &amp; Deep", "Go/no-go: decide whether to move past one burner account, based on what actually happened, not on the plan."],
]
tbl = grid([[Paragraph(c, styles["CellHead"]) for c in checklist_rows[0]]] +
           [[Paragraph(r[0], styles["Cell"]), Paragraph(r[1], styles["Cell"])]
            for r in checklist_rows[1:]],
           [1.1 * inch, 5.45 * inch])
story.append(tbl)
story.append(Spacer(1, 6))
story.append(Paragraph(
    "If any line above can't get a plain yes or no from the name next to it, it isn't done "
    "&mdash; it's a wish.",
    styles["Small"],
))

# ============================================================== SECTION 5 ==
story.append(Paragraph("5. The risks, stated plainly", styles["H1"]))
story.append(Paragraph(
    "Nothing below is hypothetical. Each one is either something the code already assumes "
    "will happen, or something the golden-set measurement already caught happening.",
    styles["Body"],
))

story.append(Paragraph("Account bans and restriction", styles["RiskHead"]))
story.append(Paragraph(
    "The warm-up pacing, the daily caps, and the acceptance-rate safety net in the code all "
    "exist because LinkedIn restricts accounts that move too fast or too mechanically &mdash; "
    "that's not a maybe, it's the reason those three systems were built before a single live "
    "send. Even with all of them on, the honest position is that a burner account can still "
    "get flagged, and that's why it's a burner: I'm treating the first account as something "
    "we're allowed to lose, not something we're betting on keeping. If it gets restricted "
    "during the pilot, that's the plan working as intended, not the plan failing.",
    styles["BodyIndent"],
))

story.append(Paragraph("Terms-of-service exposure", styles["RiskHead"]))
story.append(Paragraph(
    "This whole tool talks to LinkedIn the way their own app does, not through anything "
    "LinkedIn issued us permission to use. There's no version of this that's inside their "
    "terms &mdash; that's true today, was true in week 1, and doesn't get fixed by more "
    "engineering. It's a business risk to accept with eyes open, not a bug for me to close.",
    styles["BodyIndent"],
))

story.append(Paragraph("Session expiry", styles["RiskHead"]))
story.append(Paragraph(
    "The login is a browser cookie, not a password, and it can stop working with no warning "
    "&mdash; a LinkedIn security check, a logout somewhere else, or just time. Today, nothing "
    "watches for that on its own; a human has to notice and re-run "
    "<b>scripts/validate_account.py --replace</b>. That's why checking it is a daily line item "
    "in the checklist above and not an assumption.",
    styles["BodyIndent"],
))

story.append(Paragraph("A wrong comment on a sensitive post", styles["RiskHead"]))
story.append(Paragraph(
    "Measured, not guessed: in this week's 30-case test, the 3 cases where the right answer "
    "was no comment at all &mdash; two bereavement posts, one layoff announcement written in "
    "euphemisms &mdash; scored 0 in both the baseline and the improved run. The bot has no "
    "concept yet of \"don't comment here,\" and this week's prompt change was never going to "
    "fix that because it's a different problem. Until that's built, a human reviewing every "
    "single comment before it sends isn't a nice-to-have step in the blast-radius plan below "
    "&mdash; it's the only thing standing between the bot and exactly this mistake.",
    styles["BodyIndent"],
))

# ============================================================== SECTION 6 ==
story.append(Paragraph("6. The first live account, and how small I'm keeping the blast radius", styles["H1"]))
story.append(Paragraph(
    "<b>My recommendation: one brand-new, disposable LinkedIn account. Not Kethan's real "
    "profile, not mine, not anyone's real one.</b> It's the account referenced as owner in "
    "Section 4 &mdash; created for this, and nobody minds losing it.",
    styles["Body"],
))
story.append(Paragraph("The blast radius, exactly:", styles["H2"]))
story.append(ListFlowable([
    ListItem(Paragraph("One account. Not a batch, not a small group &mdash; one.", styles["Body"])),
    ListItem(Paragraph("One send at a time. Nothing goes out in bulk during the pilot.", styles["Body"])),
    ListItem(Paragraph("A human approves every single item before it sends. No exceptions for "
                        "\"obviously fine\" ones &mdash; that judgment call is exactly what Section 5's "
                        "last risk says isn't safe to automate yet.", styles["Body"])),
    ListItem(Paragraph("The autonomous scheduler stays off. It already ships off by default; "
                        "the pilot doesn't turn it on.", styles["Body"])),
    ListItem(Paragraph("Daily caps, quiet hours, and the warm-up program's pace all stay on from "
                        "day zero, at their normal settings &mdash; nothing gets loosened to move faster.", styles["Body"])),
], bulletType="bullet", leftIndent=14))
story.append(Paragraph(
    "I'm proposing this as the starting point, not the permanent shape of it. The right time to "
    "widen it &mdash; more accounts, batches instead of one at a time, less than 100% human "
    "review &mdash; is after the Sep 18 go/no-go, and only based on what actually happened "
    "Sep 16&ndash;17, not on how confident the plan reads today. I'd rather earn a bigger blast "
    "radius with a clean pilot than assume one and find out I was wrong on someone else's timeline.",
    styles["Body"],
))

story.append(Spacer(1, 10))
story.append(Paragraph(
    "Nothing new in Section 2 is committed or pushed yet &mdash; same as always, tell me and I'll do it.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.9 * inch, rightMargin=0.9 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Week 3 report and go-live checklist (2026-09-11)",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
