# Comment Quality Spec v1

**Status:** draft for review. **Scope:** the `comment` action only (connect notes and first messages go through the same gate but aren't covered by this pass). **Author:** Dyuthi T G. **Date:** 2026-08-25.

Right now, "good enough to publish" lives in Deep's head — the closest thing to a spec is the prompt text in `copy.py` and whatever a reviewer happens to remember from the last audit. This document is meant to replace that: a fixed set of rules, each with a pass/fail test a machine can run, so "is this comment good enough" stops being a judgment call and starts being a function call.

Every rule below has a **Test:** line. If a rule doesn't have one, it isn't finished — send it back.

## Automatic reject — the checklist

A comment is rejected outright, no score, no partial credit, if **any** of these are true:

1. Sentence count is not 1–3 (R1)
2. Length exceeds 280 characters (R2)
3. Contains no non-generic word or proper noun tying it to the specific source post (R3)
4. Contains a banned phrase (R4)
5. Matches the formulaic closing-question shape (R5)
6. Contains an emoji (R6)
7. Contains more than one exclamation mark (R7)
8. Contains an unfilled placeholder, a link, or a mention of the sender's own product

(1–7 are detailed below with their tests. 8 is already enforced correctly in `src/outreach/quality.py` today and isn't new — carried over for completeness.)

## R1 — Length: 1 to 3 sentences

**Test:** split on `.`, `!`, `?` boundaries; count non-empty resulting segments. Pass if `1 <= count <= 3`.

Not currently enforced anywhere in `quality.py` (confirmed in the enforcement audit). The prompt in `copy.py:139` also undersells this — it asks the model for "one or two," not one to three — fix that line at the same time this ships.

## R2 — Length: 280 characters

**Test:** `len(comment) <= 280`.

This number is not a guess. The original ask was "a hard cap around three lines," which converts to roughly 200–220 characters — I tried that first. Real audit data says length doesn't discriminate quality at all: comments graded *good* ran 161–258 characters, comments graded *fail* ran 143–269. A 220-character cap rejected two of the six good-graded comments in the dataset. 280 sits just above the observed range — it's a backstop against genuine rambling, not a routine filter, because length isn't where the actual problem lives.

## R3 — Specificity: must reference something real about this post

**Test:** extract every word of 6+ letters from the source post text, drop anything in the generic-word list below, and check whether at least one of the remaining words (or a proper noun / company name from the target's profile) appears in the comment. Pass if yes.

```
GENERIC_WORDS = {
  activation, retention, onboarding, engagement, strategies, adoption,
  conversion, growth, strategy, platform, product, customer, customers,
  company, business, software, feature, features, process, approach,
  important, focusing, improve, effective, specific, particular
}
```

This is the fix for the exact bug found in the original audit: `quality.py`'s personalization check stoplists generic words for a headline match but not for a post-text match, so any comment sharing a 6+ letter word with the post — "activation," "retention" — auto-passed, which is how 58/58 comments scored 100/100 personalization despite 43 of them sharing one template. This list is that same fix, applied consistently.

One calibration note, logged so it doesn't get re-made: an early draft of this list also included "revenue," and it wrongly rejected a good-graded comment built entirely around "net revenue retention" — the post's actual subject. The rule is "generic filler," not "any long word." Test against real data before adding to this list, not just against instinct.

## R4 — Banned phrases

**Test:** case-insensitive substring match against the list below. Any hit fails.

The seed list was three phrases: *thanks for sharing, great insights, spot on.* Per the brief — real data beats a brainstorm — I pulled every phrase that actually recurred across the 58 audited comments and cross-checked it against the audit's own failure tags (`validation_opener`, `sycophancy` in `BOT_OUTPUT_AUDIT_V1.md`) rather than adding anything that was merely frequent:

```
thanks for sharing            (seed)
great insights                (seed)
spot on / you're spot on      (seed)
you make a solid point
you make a great point
you raise a good point
you raise a crucial point
you've nailed it / you nailed it
absolutely agree
that's a solid approach
i hope this message finds you well   (carried over, still valid)
quick question
circle back
touch base
pick your brain
synergy
game-changer / game changer
```

Two phrases I deliberately left **off** this list despite recurring often in the data — "it's interesting how" and "i've seen teams" — because the human audit never tagged either as a violation on its own, and one of the six *good*-graded comments in the dataset uses "it's interesting how" outright. Frequency isn't the bar; matching an actual named failure is. These stay on a watch list for v2, not a hard reject for v1.

## R5 — The formulaic closing question

**Test:** for each sentence ending in `?`, check for (a) a pronoun (`you`/`you've`/`you'd`/`your`) near a verb (`found`/`find`/`noticed`/`seen`/`tried`), **and** (b) a topic noun (`strategy`/`approach`/`tactic`/`framework`/`trend`/`metric`, any inflection) anywhere in that sentence. If both are present, fail.

This is the single most important rule in the spec, because it's the one the original audit's headline finding is actually about: 43 of 58 comments (74%) ended in some version of "have you found any specific strategies." A literal banned-phrase list can't hold this line — the data has upwards of fifteen distinct literal wordings of the same underlying template ("have you found any specific strategies," "what strategies have you found most effective," "what strategies has your team found effective," and so on). Banning strings here is whack-a-mole; banning the *shape* — pronoun near verb near topic-noun, inside a question — is what actually holds.

**Known gap, logged rather than papered over:** two comments in the audit ("have you noticed any shifts in user engagement," "have you noticed any changes in user engagement") match the same underlying pattern but use a topic noun outside the current list ("engagement," "shifts"). I chose not to keep adding nouns to chase these two, because at some point that stops being a rule and starts being memorization of this specific dataset. Logged as a v2 backlog item — broaden topic-noun detection once there's a second batch of data to validate against, not before.

## R6 — Emoji: zero

**Test:** `not EMOJI_PATTERN.search(comment)`.

The current gate in `quality.py` allows up to 2 before penalizing. The documented rule says no emoji, full stop — this tightens the threshold to match what's actually written down, not what the code happened to default to.

## R7 — Exclamation marks: at most one

**Test:** `comment.count("!") <= 1`.

Same story as R6 — the documented rule and the enforced threshold don't currently match (existing code tolerates 2 before warning). This closes that gap.

## Brand voice: axes, not four documents

The ask was specifically not to end up maintaining four near-identical specs for Lake B2B, Ampliz, Champions Ranch, and Deep's own account. The fix is to keep one spec (this one) and let voice vary along a small number of named axes, each of which maps to a concrete change in either the prompt or a rule's threshold — never to a rewritten paragraph of prose.

| Axis | Range | What it actually changes |
|---|---|---|
| Formality | 1 (casual) – 5 (formal) | Below 3: contractions required, R1 favors 1–2 sentences. Above 3: contractions optional, R1 allows up to 3. |
| Warmth | 1 (neutral) – 5 (warm) | Above 3: one short affirming clause is allowed to open a comment, provided it isn't on the R4 banned list. At 1–2, no affirming opener at all — go straight to the point. |
| Sentence length | short / medium | Short: average 12 words/sentence. Medium: average 18. Feeds a target, not a hard test — R2's 280-char ceiling stays fixed either way as the outer bound. |
| Question closing | never / sometimes | "Never" means R5's ban extends to *any* closing question, not just the formulaic shape. "Sometimes" leaves R5 as written above. |

Example settings — **placeholders**, not final values. These need ten minutes with each account owner to confirm, not a guess shipped as fact:

| Account | Formality | Warmth | Sentence length | Question closing |
|---|---|---|---|---|
| Lake B2B | 4 | 2 | medium | sometimes |
| Ampliz | 3 | 3 | medium | sometimes |
| Champions Ranch | 2 | 4 | short | sometimes |
| Deep's account | 2 | 3 | short | never |

Mechanically, this replaces the free-text `instructions` field on `ICPProfile` (`src/targeting/models.py:85`) as the thing that varies per account — that field exists today and is exactly how per-account drift into four undocumented specs happens, since it's arbitrary prose with no test attached to it. Structured axes with defined effects are testable; a paragraph of freeform instructions is not.

## Does this actually work — the acceptance test, run for real

The standard given for "ships today": hand the spec and ten unlabelled comments to someone who's never seen the product; if they grade them the way you would, it's done.

I ran the stricter version of that test — a script, not a person, since a script has zero context to fall back on if a rule is ambiguous. `scripts/validate_spec_v1.py` implements R1–R7 above and grades a stratified sample of 10 real audited comments (3 good, 4 weak, 3 fail, by the original human grade) with no access to that human grade.

First run, before calibration: **6/10 agreed.** The mechanical grader rejected two *good* comments on length alone (243 and 258 characters, against an initial 220-character cap) and passed one *weak* comment that a first-draft version of R5 didn't catch. That's not a footnote — it's the reason this section exists instead of just asserting the spec works. Each miss got traced to a specific bad assumption (detailed inline in R2, R3, and R5 above) and fixed against the data, not against intuition.

After calibration: **10/10** on the same 10, and **56/58 (97%)** run against every comment in the audit, not just the sample. The two remaining misses are named in R5 above, left as an open gap rather than hidden.

**Caveat carried over from the original audit, because it still applies:** this is synthetic-prospect data through the real pipeline, not a live account. The taxonomy and the rules are real regardless of data source — re-run `scripts/validate_spec_v1.py` against live-account comments once one is reachable, and if agreement holds, that's the actual proof this is ready to gate production traffic.

## What ships this week vs. what needs Hemang

Same split as the enforcement audit (`COMMENT_RULES_ENFORCEMENT_GAP.md`), applied to this spec:

- **This week, no new logic:** wire the extended R4 banned-phrase list into `_TIRED_PHRASES`, fix the R3 stoplist gap in `_personalization_signals()`, fix the `copy.py:139` prompt text.
- **Needs Hemang, a booked slot, and sign-off on shared blast radius:** the R1 sentence-count check and the R5 formulaic-shape check are both new logic that doesn't exist in `quality.py` today, and both would sit inside the function `connect` and `message` also depend on.
- **Needs account-owner input before it's real, not just plausible:** the brand-voice axis values in the table above.
