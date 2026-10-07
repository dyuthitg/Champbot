# Quality measurement method

How "is the copy any good" turns into one number, so that number survives
past the week it was produced. Three pieces, each already in the repo — this
page is what ties them together and tells you how to rerun the whole thing.

| Piece | File | What it is |
|---|---|---|
| The test set | `docs/golden_set/golden_set.csv` | 30 fixed cases: a real-shaped post, the person it's from, and a hand-written `ideal_comment`. |
| The rubric | `docs/golden_set/RUBRIC.md` | How a human scores any candidate comment against a case, 0–3, with worked anchors. |
| The runner | `backend/scripts/run_golden_set.py` | Runs the real copywriter against all 30 cases through the real model, applies a deterministic version of the rubric, and writes a CSV. |

## The golden set

30 cases in `golden_set.csv`, one row per case: `id`, `category`, the
person's name/title/company/industry, the `source_post` they supposedly
wrote, a hand-written `ideal_comment`, `hooks` (see below), a `tone_risk`
flag, and `skip` (1 for the 3 cases where the correct action is *no
comment at all* — see `RUBRIC.md`'s opening question).

The set is fixed on purpose. Changing it invalidates any before/after
comparison that used the old version — if a case is wrong, fix it and note
the change (date + reason) rather than silently editing it, the same way any
other test fixture would be versioned.

## The rubric — human judgment, anchored

`RUBRIC.md` is the full spec: one question first ("should this post have
gotten a comment at all?"), then four anchors, 0 through 3, each with
concrete examples of what does and doesn't qualify. Read it in full before
scoring anything by hand — it's short and the anchors are the whole point.

It also documents a **blind calibration test**: before trusting your own
scoring, give 3 of the source posts to a second person with no access to the
`ideal_comment` column, have them write comments blind, score those against
the rubric yourself, then check whether they agree with your number. Do this
once, and redo it any time the rubric changes or a score on real output feels
off in a way you can't explain in one sentence.

## The runner — same rubric, applied by code, reproducibly

`run_golden_set.py` operationalizes the rubric's anchors as concrete,
deterministic rules so the same candidate text always lands on the same
score — no re-reading required to reproduce a number someone else quotes:

- **0** — a `skip` case that got a comment anyway, OR the draft failed the
  quality gate outright (a blocker, e.g. `TEMPLATE3`), OR a `tone_risk` case
  that used celebratory language ("congrats," "exciting!") on a post that
  called for restraint (a bridge round, a layoff, a sunset announcement).
- **1** — passed the gate but shows no personalization signal at all
  (`quality.py`'s own first-name/company/headline/post-word check comes back
  empty). Could have been posted under a different name.
- **2** — passed the gate, has a personalization signal, but missed the
  case's `hook` (see below).
- **3** — passed the gate and mentions the case's `hook`.

**The `hooks` column is the load-bearing proxy.** It's a hand-picked word or
phrase that only shows up in a comment if it actually engaged with the one
distinctive detail in *that* post, not the general topic. It's a proxy, not a
perfect model of human judgment — a comment can engage with the post in a
different, equally specific way and still miss the exact hook word, which
would under-score it. That's a known, stated limitation, not a hidden one:
the tradeoff is that every hook is sitting in the CSV, auditable by anyone,
rather than living in one person's head as an implicit standard.

## How to rerun it

```
cd backend
python scripts/run_golden_set.py baseline    # before a prompt/rule change
python scripts/run_golden_set.py after       # after it
```

Each run:
1. Loads all 30 cases from `golden_set.csv`.
2. Drafts a real comment for each through the real copywriter
   (`backend/src/outreach/copy.py`) and a real model call — not a mock, not a
   template. Needs a working `OPENROUTER_API_KEY` in `.env`; without one the
   copywriter falls back to template copy and the run will not measure what
   you think it's measuring.
3. Scores every result with the deterministic rubric above.
4. Writes `docs/golden_set/<label>_run.csv` (one row per case, with the
   candidate text, the quality gate's flags, and the rubric score + reason).
5. Prints the aggregate: average rubric score out of 3, the count of
   score-of-0 cases, and the count flagged `R4` or `TEMPLATE3`.

Run `baseline` before your change and `after` once it's in, on the same 30
cases, through the same runner — a before/after comparison is only honest if
both sides went through identical conditions apart from the one thing you
changed. `docs/golden_set/BEFORE_AFTER_MEMO.md` is the write-up format for
reporting the comparison once you have both.

## What this number is, and isn't

It's a real, reproducible measurement of one thing: does the copy engage
with the actual distinctive content of a post, on a fixed set of 30
realistic cases, scored by a rubric a second person has checked their
agreement with. It is not a live-account measurement — every run here is
against the golden set's fixed synthetic-but-realistic posts, not real
targets, and that distinction should stay explicit in anything built from
this number (see `DAILY_WORK_LOG.md`'s note on an earlier 58-comment audit
that was run the same honest way). Treat a golden-set score as "did this
change help in principle," not as a substitute for reviewing real queue
output — the two catch different things.

## When to rerun it

Any change to `backend/src/outreach/copy.py` (the prompt/writer) or
`backend/src/outreach/quality.py` (the gate) that isn't a single, obviously
low-risk phrase addition — see `VOICE_TUNING_GUIDE.md` §2, step 5. If you
changed the writer or the gate and shipped without rerunning this, that's a
gap someone will find in the queue instead of in a CSV, which is a strictly
more expensive place to find it.
