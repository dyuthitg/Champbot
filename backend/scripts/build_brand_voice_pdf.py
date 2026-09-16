"""
Generates Brand_Voice_As_Config.pdf -- written like a personal note, first
person, plain sentences, simple words. No report formatting.

Run: python scripts/build_brand_voice_pdf.py
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

OUT_PATH = "Brand_Voice_As_Config.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Quote", fontSize=10.5, leading=15, spaceAfter=6, leftIndent=22, textColor=INK, fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Brand voice, as a form a marketer can fill in", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-10",
    styles["SubTitle"],
))

story.append(Paragraph(
    "Today's brief was different from the others this week: no bug to chase, no spec to enforce. "
    "The ask was taste, and the test of it is a marketer adding a third brand with no engineer in "
    "the room. So that's what I built toward, in this order: a schema, two real brands filled into "
    "it, the empty states, and a pass to make the accent colour mean one thing everywhere it "
    "appears. All four are done and I ran every one of them for real, not just read the code back "
    "to myself.",
    styles["Body"],
))

# ----------------------------------------------------------------- 1
story.append(Paragraph("1. The schema is a folder of files, not a screen in the code", styles["Body"]))
story.append(Paragraph(
    "<b>config/brand_voices/</b>. Six fields decide a brand's voice: how formal it is, the hard "
    "cap on sentences, how often emoji shows up, the words it should never say, and at least two "
    "real example comments written the way that brand actually talks. Three more are optional -- "
    "preferred phrases, tone words, how a comment is allowed to end.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "The example comments matter more than every setting combined. I wrote the README to say that "
    "in plain words, because a marketer will otherwise spend their time tuning a dropdown and skip "
    "the two lines that actually carry the voice.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "To add a brand: copy <b>_template.yaml</b>, fill in the blanks, save it in the folder. No "
    "deploy, no pull request, no me. A typo or a missing field just gets skipped -- the account "
    "falls back to the plain default voice, so a bad edit here can never take outreach down.",
    styles["Small"],
))

# ----------------------------------------------------------------- 2
story.append(Paragraph("2. Two brands, filled in for real, deliberately as different as two brands get", styles["Body"]))
story.append(Paragraph(
    "<b>Lake B2B</b> -- formal, two sentences max, never an emoji, no name used. <b>Loopwork</b> "
    "-- casual, one sentence, emoji allowed, addresses people by first name, ends on a direct "
    "question. If the same six fields can hold both of these without either one reading like a "
    "compromise, the schema generalises. Here is one example from each, verbatim from the files:",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "Lake B2B, replying to a VP of Marketing whose intent-data vendor returned 40% duplicate contacts:",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "“40% duplicates points at a hygiene problem upstream, not the vendor itself -- worth "
    "checking how the source list was deduped before switching providers.”",
    styles["Quote"],
))
story.append(Paragraph(
    "Loopwork, replying to a founder who cancelled all recurring meetings for a month:",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "“Priya, a month with zero recurring meetings sounds like a horror movie for middle "
    "management and a dream for literally everyone else” (plus one laughing emoji, the file's "
    "own base font can't render it here)",
    styles["Quote"],
))
story.append(Paragraph(
    "Both live at <b>config/brand_voices/lake-b2b.yaml</b> and <b>config/brand_voices/loopwork.yaml</b>.",
    styles["Small"],
))

# ----------------------------------------------------------------- 3
story.append(Paragraph("3. Picking a brand voice is now part of setting up who to target", styles["Body"]))
story.append(Paragraph(
    "The Targeting screen's “Define the right person” form has a new field, <b>Brand "
    "voice</b>, sitting right under the standing instructions box. It lists whatever is in the "
    "folder -- today that's “Lake B2B (formal)” and “Loopwork (casual)” -- plus "
    "“Default” for the plain voice every account has always had.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "Underneath, the copywriter takes whatever brand is picked and turns the six fields into the "
    "same kind of plain-English instruction it already follows for everything else, layered on "
    "top of the existing rules -- never replacing them. A brand can change how something is said. "
    "It can never turn off the rule against inventing a fact, or the one against asking for a "
    "meeting. Those apply no matter which brand is picked, and nothing in a brand's file can "
    "override them.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "One honest limit: this only reaches comments written by the model. The offline template "
    "fallback -- what fires when no LLM key is configured -- is plain and generic on every "
    "account today, brand or no brand, and that was already true before this. Not something I "
    "changed, but worth saying so it isn't a surprise later.",
    styles["Small"],
))

# ----------------------------------------------------------------- 4
story.append(Paragraph("4. The three empty moments in the queue, each saying something different", styles["Body"]))
story.append(Paragraph(
    "Before today the queue had one blank-state message no matter why it was empty. Now it tells "
    "the three moments apart, because they are not the same feeling:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("<b>First run</b> -- this account has never had anything suggested. “Nothing generated yet,” with a sparkle icon and a button to draft the first batch. A next step, not a congratulation for work that hasn't started.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>All clear</b> -- suggestions existed and every one has a decision now. “You're caught up,” with a shield icon, the real count of how many were generated, and a button to ask for more. This is the good outcome after real work, and it says so.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Filtered to nothing</b> -- already existed, kept as-is: a quieter dashed box with “Clear filters,” because this one is a dead end you back out of, not a milestone.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "I'd like to put the first two in front of Deep without explaining which is which first, "
    "the way the brief asked. If they read as two different moments without a caption, that's "
    "the actual test passing.",
    styles["Small"],
))

# ----------------------------------------------------------------- 5
story.append(Paragraph("5. The visual pass -- what I actually touched, and what I deliberately didn't", styles["Body"]))
story.append(Paragraph(
    "I went looking for every place a page was still hand-mixing a raw purple or green shade "
    "instead of using the <b>accent</b> / <b>success</b> tokens from the 09-04 design system. Two "
    "real ones: the shared <b>.input / .btn-primary / .btn-approve</b> styles every page's form "
    "fields and buttons are built from were still spelling the same colour the old way, and the "
    "match-score slider on the Targeting page had its own hard-coded purple. Both now read the "
    "token, so the one accent colour used on the new brand-voice dropdown, the new empty states, "
    "and every existing button is provably the same colour, not four different pickers that "
    "happen to look close.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "What I did not touch: Dashboard, Accounts, Campaigns, Warm-up and Agents were built before "
    "the token system existed and still carry their own raw colours in dozens of places. Retheming "
    "five pages I can't fully exercise today, on top of everything else due today, was more risk "
    "than the day could carry safely. Flagging it now rather than letting “the whole surface” "
    "quietly mean less than it sounds like.",
    styles["BodyIndent"],
))

# ----------------------------------------------------------------- 6
story.append(Paragraph("6. Tested it for real, not just read the code back to myself", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("23 new tests on the schema loader: both real brand files parse, every required field is actually required, a bad enum value is rejected, a broken file degrades to the default voice instead of raising, the two brands are asserted to actually differ.", styles["BodyIndent"])),
    ListItem(Paragraph("Ran the full migration test -- a database built from migrations matches the models exactly, byte for byte -- and the existing outreach and quality-gate suites, 98 tests total, all passing, nothing I touched broke anything already there.", styles["BodyIndent"])),
    ListItem(Paragraph("Started the real backend and frontend locally, created an ICP through the actual screen, picked Lake B2B from the dropdown, saved it, and read it back from the database with brand_voice_id sitting on the row -- not a mock, the real save path.", styles["BodyIndent"])),
    ListItem(Paragraph("Opened the Approvals screen in a browser against a brand-new seeded account and saw “Nothing generated yet”; switched to an account with five reviewed suggestions and saw “You're caught up -- 5 generated so far”. Both screenshots, not descriptions.", styles["BodyIndent"])),
    ListItem(Paragraph("Type-checked and production-built the frontend clean. Caught my own mistake this way once already today -- a stray */ inside a CSS comment broke the whole stylesheet, and the build said so immediately instead of me finding it later.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

# ----------------------------------------------------------------- 7
story.append(Paragraph("7. Where it all lives, if you want to look", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>config/brand_voices/</b> -- the schema (schema.json), the marketer README, the template, and the two real brands", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/outreach/brand_voice.py</b> -- loads and validates a profile, turns it into the instructions the writer follows", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/outreach/copy.py</b> -- layers the brand's voice on top of the existing safety rules, never replacing them", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/targeting/models.py, schemas.py, service.py</b> and <b>alembic/versions/0003_icp_brand_voice.py</b> -- the new brand_voice_id field on a target profile", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/api/routes/targeting.py</b> -- GET /targeting/brand-voices, reading the folder directly, no database table", styles["BodyIndent"])),
    ListItem(Paragraph("<b>frontend/src/pages/Targeting.tsx</b> -- the Brand voice dropdown", styles["BodyIndent"])),
    ListItem(Paragraph("<b>frontend/src/pages/Approvals.tsx</b> -- the three empty states", styles["BodyIndent"])),
    ListItem(Paragraph("<b>frontend/src/index.css</b> -- the token fix on the four shared button/input styles", styles["BodyIndent"])),
    ListItem(Paragraph("<b>tests/test_brand_voice.py</b> -- the 23 new tests", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

# ----------------------------------------------------------------- 8
story.append(Paragraph("8. What I haven't done, so it's not a surprise later", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>I haven't watched Deep look at the empty states yet.</b> That's the actual test asked for today, and it's not mine to grade myself on. Everything above is me being confident it'll land, not proof that it did.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>The other five pages still don't use the design tokens.</b> Named honestly in section 5 -- a real follow-up, not something I'm quietly calling done.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>A marketer still edits a YAML file by hand,</b> not a form in the app. That was the fastest way to prove the schema today; a real in-app editor for it is a reasonable next step if this direction gets a yes.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Nothing is committed or pushed.</b> It's all sitting in the working copy, tested and running. Say the word and I'll push it.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 14))
story.append(Paragraph(
    "The honest summary: a brand's voice used to be one free-text box, which meant every brand "
    "sounded exactly as considered as whoever typed into it that day. Now it's six fields and two "
    "real examples, sitting in a file a marketer owns outright -- and the two moments in the queue "
    "that used to say nothing now say something true.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Brand voice as config -- 2026-09-10",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
