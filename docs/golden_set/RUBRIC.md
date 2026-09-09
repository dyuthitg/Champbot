# Golden-set rubric — one number, 0 to 3

Score a candidate comment against its case's `ideal_comment` in
[`golden_set.csv`](golden_set.csv). One number per comment. No sub-scores,
no weighting across dimensions — a ten-dimension rubric doesn't survive
contact with a real Tuesday afternoon of scoring 30 of these by hand.

Ask yourself one question first, before you even read the anchors:

> **Should this post have gotten a comment at all?**

Three of the thirty cases (`G28`, `G29`, `G30` — one defensive layoff
announcement, two genuine bereavement posts) are marked `SKIP` in the
`notes` column: the honest gold-standard action is *no comment*. If a
candidate produces fluent, on-topic, even well-written text for one of
these, **that is a 0**, full stop, regardless of how good the prose is.
This is the whole point of including them — a bot that writes a polished
comment on a bereavement post has failed in the way that actually costs
you, not in a way word-choice can fix.

For every other case, score with these anchors:

## 3 — Exactly what you'd have written yourself
- Responds to the one specific, distinctive thing in *this* post — not a
  detail that could be swapped into ten other posts in the same category.
- Right tone for the moment (celebratory funding post vs. honest bridge-round
  post vs. layoff post are three different tones, not one "professional"
  register applied uniformly).
- Reads like a specific person actually thought about this post for ten
  seconds. You would post it under your own name, unedited.

## 2 — Good, but you'd tweak one thing
- Clearly read the post and responds to something real in it.
- Tone is appropriate, nothing embarrassing.
- But: slightly generic in one respect (references the topic rather than the
  most distinctive detail), or the question/observation is a little flat, or
  it's marginally too long/short for the moment. You'd edit a phrase, not
  rewrite it.

## 1 — Weak: technically fine, forgettable
- Nothing wrong with it exactly. Also nothing in it that couldn't have been
  posted on a different person's similar update with zero changes.
- Nothing offensive, but no sign the post was actually read closely — echoes
  the general topic ("congrats on the raise!", "exciting news!") rather than
  the one thing that made this post different from the other four in its
  category.

## 0 — Would embarrass you if it went out under your name
- Wrong tone for the moment (upbeat/congratulatory on a layoff, bridge round,
  or sunset-announcement post; generic engagement-bait on a condolence post).
- A formulaic template shape — validate, restate, ask "what strategies have
  you found" — the exact pattern `src/outreach/quality.py`'s `TEMPLATE3` rule
  exists to catch. If your rubric and that rule disagree often, one of them
  is wrong; go find out which.
- Factually tone-deaf (treats a bridge round as a victory lap, treats a
  relaunch-after-failure as a normal launch).
- Or: commented on one of the three `SKIP` cases at all.

## What "clear anchors" buys you that a 10-point scale doesn't

A grader re-scoring the same comment a week later should land on the same
number without re-reading this file closely. If two people's 2s and 3s keep
disagreeing, the fix is sharpening these anchors with a concrete example,
not adding more of them.

---

## Calibrating the rubric: the blind test

Before trusting this rubric on real output, run this once:

1. Pick 3 source posts from `golden_set.csv` — one easy (a standard funding
   or milestone post), one medium (a thought-leadership or product-launch
   post), one hard (a layoff or the bridge-round funding post).
2. Give **only the source posts** to a second person — Harshil, or whoever
   is closest to hand — with no access to this file's `ideal_comment` or
   `notes` columns. Ask them to write a comment for each, blind, the way
   they'd actually comment on LinkedIn.
3. Score their three comments against this rubric yourself.
4. Show them the score and the reason. Ask if they agree.

**If you agree:** the rubric is anchored well enough to trust on the other
27 cases and on real bot output going forward.

**If you don't agree** — you scored their comment a 2 and they think it's
obviously a 3, or vice versa — that's not Harshil being wrong. It means an
anchor above is vague enough that two reasonable people read it differently,
and the fix is to rewrite that anchor with the specific disagreement as the
new example, not to explain why your number was right.

Do this once now. Redo it any time the rubric changes, or any time a score
on real output feels off and you can't articulate why in one sentence.
