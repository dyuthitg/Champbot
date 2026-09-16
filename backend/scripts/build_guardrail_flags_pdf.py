"""
Generates Guardrail_Flags_In_The_Queue.pdf — written like a personal note,
first person, plain sentences, simple words. No report formatting.

Run: python scripts/build_guardrail_flags_pdf.py
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

OUT_PATH = "Guardrail_Flags_In_The_Queue.pdf"

MUTED = colors.HexColor("#6b6b6b")
INK = colors.HexColor("#1a1a1a")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleBig", fontSize=19, leading=23, spaceAfter=2, fontName="Helvetica-Bold", textColor=INK))
styles.add(ParagraphStyle(name="SubTitle", fontSize=10, leading=14, textColor=MUTED, spaceAfter=18))
styles.add(ParagraphStyle(name="Body", fontSize=11, leading=17, spaceAfter=12, textColor=INK))
styles.add(ParagraphStyle(name="BodyIndent", fontSize=11, leading=17, spaceAfter=6, leftIndent=14, textColor=INK))
styles.add(ParagraphStyle(name="Small", fontSize=9, leading=13, textColor=MUTED, spaceAfter=14, leftIndent=14))

story = []

story.append(Paragraph("Today's work — you can see why a comment got flagged", styles["TitleBig"]))
story.append(Paragraph(
    "Dyuthi &nbsp;&bull;&nbsp; 2026-09-04 &nbsp;&bull;&nbsp; written in my own words, not a formal report",
    styles["SubTitle"],
))

story.append(Paragraph(
    "The thing I had to ship today: someone who has never read my rules should be able to look at "
    "the review screen and understand why an item got flagged, on their own, without asking me. "
    "So that's what I built. Here it is in plain words.",
    styles["Body"],
))

# ----------------------------------------------------------------- 1
story.append(Paragraph("1. Every comment now says what it broke, right in the list", styles["Body"]))
story.append(Paragraph(
    "Each row in the queue now carries small labels — <b>Too long</b>, <b>Generic phrase</b>, "
    "<b>No specific reference</b>, <b>Formula question</b>, <b>Near-identical to others</b>, and a "
    "few more. Plain English, no codes, no jargon. You don't have to open anything to see them.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "Open a row and the same label is there again, but with the actual detail next to it — not "
    "just “Too long”, but “Too long for a comment: 514 characters (limit 400)”, and then whether "
    "that stops you approving it or just costs points.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ----------------------------------------------------------------- 2
story.append(Paragraph("2. The words come from one place, so they can't drift apart", styles["Body"]))
story.append(Paragraph(
    "This was the part of the ask I cared most about. It would have been easy to type the rule "
    "names into the screen by hand — and then next month the spec says one thing, the code says "
    "another, and the screen says a third. So I wrote the rule names down <b>once</b>, in the "
    "checking code, and the screen just reads them. Same word in the spec, same word in the code, "
    "same word on the chip. There is no second copy to fall out of step.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "I also added a test that fails on purpose if anyone starts hard-coding a rule name back into "
    "the screen. Rules I can't enforce tend not to survive.",
    styles["Small"],
))

# ----------------------------------------------------------------- 3
story.append(Paragraph("3. You can now filter and sort by the type of mistake", styles["Body"]))
story.append(Paragraph(
    "Above the list there's a row of buttons, one per problem, each with a count — “Generic "
    "phrase 14”, “No specific reference 9”, “Nothing flagged 5”. Click one and the list shows "
    "only those. There's also a sort switch: <b>Best match</b> (what it did before) or "
    "<b>Failure type</b>, which puts everything that broke the same rule together, worst first.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "That's the part that saves real time. Fixing fourteen of the same mistake in one pass is one "
    "decision. Meeting the same mistake fourteen separate times, in date order, is fourteen.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "The counts stay put when you filter — they're counted over the whole queue, not the filtered "
    "view, so you can always see what else is waiting and click back out.",
    styles["Small"],
))

# ----------------------------------------------------------------- 4
story.append(Paragraph("4. The writing box counts as you type, and warns before the wall", styles["Body"]))
story.append(Paragraph(
    "When you edit a comment, the line underneath now says something like “268 / 400 characters "
    "· 3 sentences”. It has three states, not two:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("<b>Grey</b> — you're fine, carry on", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Amber</b> — you've gone past 280 characters, which is what the rule asks for, or past 3 sentences. You can still send it. Fix it now and it costs you nothing.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Red</b> — past 400, which is the number that actually blocks. The Approve button goes grey and says so.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "Why two numbers and not one: our written rule says 280, but the code has always blocked at "
    "400. I didn't want the box to pretend 280 blocks when it doesn't — a counter that lies gets "
    "ignored within a week. So it shows you both: the target in amber, the wall in red.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "Small thing I caught while testing: the counter said 515 and the warning underneath said 514, "
    "because the checker trims spaces off the end and the counter didn't. Fixed. A counter that "
    "disagrees with the rule it's counting against is worse than no counter.",
    styles["Small"],
))

# ----------------------------------------------------------------- 5
story.append(Paragraph("5. Two rules that were written down but never shown — now visible, still not blocking", styles["Body"]))
story.append(Paragraph(
    "Two of my rules have never actually been checked by the code: “a comment is 1 to 3 sentences”, "
    "and the big one from the August audit — the “have you found any specific strategies?” ending "
    "that 43 out of 58 comments used.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "I've made both of them <b>visible</b> today, and deliberately not made them block anything. "
    "They show up as grey “heads up” labels, they don't cost the comment any points, and they "
    "don't stop an approval. The reason is that the checker is shared with connection requests and "
    "direct messages, so tightening it changes what gets rejected on those too — that's Hemang's "
    "call, not mine to make alone. But there was no reason the operator couldn't <i>see</i> it in "
    "the meantime. Seeing it costs nothing and risks nothing.",
    styles["BodyIndent"],
))
story.append(Spacer(1, 8))

# ----------------------------------------------------------------- 6
story.append(Paragraph("6. I tested it on real comments, not made-up ones", styles["Body"]))
story.append(Paragraph(
    "I ran all 58 real comments from the August audit — the ones the bot actually wrote — through "
    "the new labels, and compared against the grades I gave them by hand back then:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("All <b>6</b> I graded <b>good</b> came back with <b>zero</b> labels. No false alarms on the good ones.", styles["BodyIndent"])),
    ListItem(Paragraph("All <b>11</b> I graded <b>fail</b> came back with at least one label. It caught every one.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>45 of the 58</b> now carry a visible label — while the old quality score gave <b>54 of those same 58</b> a perfect 100 out of 100.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))
story.append(Paragraph(
    "That last line is the whole point of today. The score was never wrong exactly — it just "
    "couldn't see the thing that was actually wrong. Now the screen says it out loud.",
    styles["Small"],
))

story.append(Paragraph("Then I opened the real app and used it", styles["Body"]))
story.append(Paragraph(
    "Loaded a queue of 30 real comments with 10 different problems mixed in and clicked through it "
    "myself:",
    styles["BodyIndent"],
))
story.append(ListFlowable([
    ListItem(Paragraph("Filtered by “No specific reference” — got exactly those 9, counts stayed put", styles["BodyIndent"])),
    ListItem(Paragraph("Sorted by failure type — blocked ones first, then the repeated ones grouped together", styles["BodyIndent"])),
    ListItem(Paragraph("Opened a 515-character comment: counter went red, Approve went grey, three labels explained why", styles["BodyIndent"])),
    ListItem(Paragraph("Typed one up to 280 characters and watched it go amber, with Approve still available", styles["BodyIndent"])),
    ListItem(Paragraph("Zero errors in the browser console", styles["BodyIndent"])),
    ListItem(Paragraph("264 automatic tests pass (24 of them new today), type-checker clean, production build clean", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

# ----------------------------------------------------------------- 7
story.append(Paragraph("7. Checking the colours caught a real problem", styles["Body"]))
story.append(Paragraph(
    "Since these labels are now the main thing you read, I ran the readability math on them "
    "instead of trusting my eyes. Two of our existing colours failed badly when used as "
    "<i>text</i>: the green measured <b>2.36</b> and the red <b>3.40</b>, where <b>4.5</b> is the "
    "pass mark.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "The cause is simple once you see it: those two colours were only ever picked to sit "
    "<i>behind</i> white text on a button. A colour dark enough to carry white text is far too "
    "dark to be text itself. So each one is now a pair — the button colour stays exactly as it "
    "was, and there's a second, lighter version used only for text. Green is now 6.72, red 4.63. "
    "I also added the amber, which passes everywhere I use it. All of it is written down in the "
    "contrast file with the numbers, so nobody has to redo the maths.",
    styles["BodyIndent"],
))
story.append(Paragraph(
    "It fixed two older spots as a side effect too — the “Never contact” button label and the "
    "match-score badge were both quietly failing the same way.",
    styles["Small"],
))

# ----------------------------------------------------------------- 8
story.append(Paragraph("8. Where it all lives, if you want to look", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>src/outreach/quality.py</b> — the one list of rule names, and the two new checks (sentences, formula question)", styles["BodyIndent"])),
    ListItem(Paragraph("<b>src/api/routes/outreach.py</b> — sends the labels to the screen, re-checked against the text as it stands now, so it stays true after an edit", styles["BodyIndent"])),
    ListItem(Paragraph("<b>frontend/src/pages/Approvals.tsx</b> — the labels, the filter row, the sort switch, the live counter", styles["BodyIndent"])),
    ListItem(Paragraph("<b>frontend/src/lib/guardrails.ts</b> — the display side only. No rule names in here, on purpose.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>tests/test_guardrail_flags.py</b> — the 24 new tests", styles["BodyIndent"])),
    ListItem(Paragraph("<b>docs/CONTRAST_CHECK.md</b> — the colour numbers", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

# ----------------------------------------------------------------- 9
story.append(Paragraph("9. What I have not done, so it's not a surprise later", styles["Body"]))
story.append(ListFlowable([
    ListItem(Paragraph("<b>I haven't sat Harshil in front of it yet.</b> That test is the real one and I can't mark my own homework on it. I built for it — plain words on the labels, the rule number tucked away as a hover, and a one-line explanation of what each severity means — but until I watch him use it and see where he pauses, it's my guess, not a result.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Three of the checks aren't in my written spec yet</b> — the pushy call-to-action one, the generic-opener one, and the repeated-comment one. Rather than dress them up as spec rules, the screen says “not in the spec yet” next to them. That's a v2 job for the spec, not a rename.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>The 1-to-3-sentence rule and the formula-question rule still don't block anything.</b> That needs Hemang and a booked slot, because it changes connection requests and messages too.", styles["BodyIndent"])),
    ListItem(Paragraph("<b>Nothing is committed or pushed.</b> It's all sitting in the working copy, tested and running. Say the word and I'll push it.", styles["BodyIndent"])),
], bulletType="bullet", leftIndent=20))

story.append(Spacer(1, 14))
story.append(Paragraph(
    "The honest summary: the checker always knew why it docked a comment, it just never said so in "
    "a way you could group, count, or act on. Now it does — and the two rules it still can't "
    "enforce, it at least admits to instead of hiding.",
    styles["Small"],
))

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.95 * inch, rightMargin=0.95 * inch,
    topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    title="Guardrail flags in the queue — 2026-09-04",
    author="Dyuthi T G",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
