"""
Generates Comment_Quality_Spec_v1.pdf — condensed to 2 pages.
Plain memo styling — no color, serif body — matching house style.

Run: python scripts/build_spec_pdf.py
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

OUT_PATH = "Comment_Quality_Spec_v1.pdf"

styles = getSampleStyleSheet()
BODY = "Times-Roman"
BOLD = "Times-Bold"
MONO = "Courier"

styles.add(ParagraphStyle(name="Head", fontName=BOLD, fontSize=15, leading=17, spaceAfter=1))
styles.add(ParagraphStyle(name="SubHead", fontName=BODY, fontSize=9, leading=11))
styles.add(ParagraphStyle(name="Section", fontName=BOLD, fontSize=10.8, leading=13, spaceBefore=9, spaceAfter=3))
styles.add(ParagraphStyle(name="Body", fontName=BODY, fontSize=9, leading=12, spaceAfter=4))
styles.add(ParagraphStyle(name="Cell", fontName=BODY, fontSize=7.6, leading=9.6))
styles.add(ParagraphStyle(name="CellMono", fontName=MONO, fontSize=7.2, leading=9.2))
styles.add(ParagraphStyle(name="CellBold", fontName=BOLD, fontSize=7.8, leading=9.6))

story = []


def h(text):
    story.append(Paragraph(text, styles["Section"]))


def p(text):
    story.append(Paragraph(text, styles["Body"]))


def table(rows, col_widths, mono_col=None):
    data = []
    for r, row in enumerate(rows):
        line = []
        for c, cell in enumerate(row):
            if r == 0:
                style = styles["CellBold"]
            elif mono_col is not None and c == mono_col:
                style = styles["CellMono"]
            else:
                style = styles["Cell"]
            line.append(Paragraph(cell, style))
        data.append(line)
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t)
    story.append(Spacer(1, 5))


# ------------------------------------------------------------------ header
story.append(Paragraph("Comment Quality Spec v1", styles["Head"]))
story.append(Paragraph("Draft for review &middot; comment action only &middot; Dyuthi T G &middot; 2026-08-25", styles["SubHead"]))
story.append(Spacer(1, 5))
story.append(HRFlowable(width="100%", thickness=0.5, color=colors.black))
story.append(Spacer(1, 6))

p("“Good enough to publish” currently lives in Deep's head. This replaces it with rules that "
  "have a pass/fail test a machine can run &mdash; if a rule can't be written as a test, it isn't "
  "finished. <b>Automatic reject</b> if any of: sentence count &ne; 1&ndash;3 &middot; length "
  "&gt;280 chars &middot; no specific reference to the source post &middot; banned phrase &middot; "
  "matches the formulaic closing-question shape &middot; any emoji &middot; &gt;1 exclamation mark "
  "&middot; unfilled placeholder / link / own-product mention (already enforced today).")

# ------------------------------------------------------------------ rules table
h("Rules")
table(
    [
        ["Rule", "Test", "Why"],
        ["R1 &mdash; 1&ndash;3 sentences", "1 &le; sentence_count &le; 3",
         "Not enforced anywhere today; prompt itself only asks for &ldquo;one or two&rdquo; (copy.py:139) &mdash; fix both."],
        ["R2 &mdash; &le;280 characters", "len(comment) &le; 280",
         "Not a guess: good-graded comments ran 161&ndash;258 chars, fail-graded ran 143&ndash;269. Length doesn't predict quality &mdash; this is a rambling backstop, not a filter."],
        ["R3 &mdash; specific to this post", "&ge;1 non-generic 6+ letter word from the post (or a proper noun) appears in the comment",
         "Fixes the audit's core bug: quality.py stoplists generic words for a headline match but not a post-text match, so 58/58 comments scored 100/100 personalization."],
        ["R4 &mdash; no banned phrase", "case-insensitive substring match, list below",
         "Seed list (3 phrases) extended from what actually recurred in the audit, cross-checked against the audit's own failure tags &mdash; not every frequent phrase made the cut."],
        ["R5 &mdash; no formulaic closing question", "in a sentence ending &lsquo;?&rsquo;: pronoun near found/find/noticed/seen/tried, AND a topic noun (strategy/approach/tactic/framework/trend/metric) anywhere in it",
         "43/58 audited comments (74%) ended in a version of this. ~15 literal wordings of one template exist &mdash; banning the shape beats whack-a-mole on strings."],
        ["R6 &mdash; zero emoji", "no emoji characters present", "Gate today allows up to 2; the rule says none."],
        ["R7 &mdash; &le;1 exclamation mark", "comment.count(\"!\") &le; 1", "Gate today allows up to 2; the rule says one."],
    ],
    [1.35 * inch, 2.55 * inch, 2.7 * inch],
)

p("<b>R3 calibration note:</b> an early draft's generic-word list also included &ldquo;revenue,&rdquo; "
  "which wrongly rejected a good-graded comment about &ldquo;net revenue retention&rdquo; &mdash; "
  "the post's own subject. Test against data before adding to a stoplist, not instinct. "
  "<b>R5 known gap:</b> two audited comments (&ldquo;have you noticed any shifts/changes in user "
  "engagement&rdquo;) use the same template with a topic noun outside the current list &mdash; left "
  "as a v2 item rather than chased, to avoid memorizing this one dataset.")

# ------------------------------------------------------------------ banned phrases
h("R4 banned-phrase list")
p(
    "<font face='Courier' size='7.4'>thanks for sharing (seed) &middot; great insights (seed) &middot; "
    "spot on / you're spot on (seed) &middot; you make a solid/great point &middot; you raise a "
    "good/crucial point &middot; you've nailed it / you nailed it &middot; absolutely agree &middot; "
    "that's a solid approach &middot; i hope this message finds you well &middot; quick question "
    "&middot; circle back &middot; touch base &middot; pick your brain &middot; synergy &middot; "
    "game-changer</font>"
)
p("Deliberately left off despite recurring often: &ldquo;it's interesting how,&rdquo; &ldquo;i've "
  "seen teams&rdquo; &mdash; the human audit never tagged either as a violation, and one good-graded "
  "comment uses the first outright. Frequency isn't the bar; matching a named failure is.")

# ------------------------------------------------------------------ brand voice
h("Brand voice: axes, not four documents")
p("One spec; voice varies along axes mapped to concrete rule/prompt changes &mdash; never a "
  "rewritten document per account. Replaces the free-text <font face='Courier' size='7.6'>ICPProfile."
  "instructions</font> field (src/targeting/models.py:85), which is how undocumented per-account "
  "drift happens today.")
table(
    [
        ["Axis", "Range", "Effect", "Lake B2B", "Ampliz", "Champions Ranch", "Deep's acct."],
        ["Formality", "1&ndash;5", "&lt;3: contractions required, R1 favors 1&ndash;2 sent.", "4", "3", "2", "2"],
        ["Warmth", "1&ndash;5", "&gt;3: one non-R4 affirming opener allowed", "2", "3", "4", "3"],
        ["Sentence len.", "short/med", "target words/sentence, R2 cap unchanged", "medium", "medium", "short", "short"],
        ["Question close", "never/sometimes", "&ldquo;never&rdquo; extends R5 to any closing question", "sometimes", "sometimes", "sometimes", "never"],
    ],
    [0.85 * inch, 0.6 * inch, 2.05 * inch, 0.65 * inch, 0.6 * inch, 0.85 * inch, 0.65 * inch],
)
p("Example values above are placeholders pending ten minutes with each account owner &mdash; not shipped as fact.")

# ------------------------------------------------------------------ validation + next steps
h("Validation &mdash; run for real, not asserted")
p("scripts/validate_spec_v1.py grades comments against R1&ndash;R7 with no access to the human grade "
  "already in audit_log_scored.csv. <b>First run, before calibration: 6/10</b> agreement on a "
  "stratified 10-comment sample &mdash; it rejected 2 good comments on an over-tight length guess and "
  "missed a weak one on an under-built R5. Each miss traced to a specific bad assumption and fixed "
  "against data (see notes above), not intuition. <b>After calibration: 10/10 on the sample, 56/58 "
  "(97%) on the full audited set</b>, two named residual misses left open rather than hidden. Caveat: "
  "synthetic prospects through the real pipeline, not a live account &mdash; re-run once one is "
  "reachable before trusting this to gate production traffic.")

h("What ships this week vs. what needs Hemang")
p("<b>This week, no new logic:</b> extend _TIRED_PHRASES with the R4 list, fix the R3 stoplist gap "
  "in _personalization_signals(), fix the copy.py:139 prompt text. <b>Needs Hemang + a booked slot:</b> "
  "R1 and R5 are new logic inside quality.py that connect/message also depend on. <b>Needs account "
  "owners:</b> confirm real values for the brand-voice axis table.")

doc = SimpleDocTemplate(
    OUT_PATH, pagesize=LETTER,
    leftMargin=0.65 * inch, rightMargin=0.65 * inch,
    topMargin=0.6 * inch, bottomMargin=0.6 * inch,
    title="Comment Quality Spec v1",
)
doc.build(story)
print(f"wrote {OUT_PATH}")
