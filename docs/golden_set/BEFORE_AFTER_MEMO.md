# Before/after: one prompt change, measured against the golden set

Method, in one paragraph: `scripts/run_golden_set.py` runs the real
copywriter (`src/outreach/copy.py`, a real OpenRouter call, not a template)
against all 30 cases in `golden_set.csv`, grades every result with the
deterministic scorer described at the top of that script (which
operationalizes `RUBRIC.md`'s anchors: 0 = failed the gate or commented on
a SKIP case or wrong tone; 1 = passed but no personalization; 2 = passed
with personalization but missed the post's specific hook; 3 = referenced
the hook), and writes one CSV row per case. Baseline was captured and
frozen (`baseline_run.csv`) before any change was made. Then one prompt
change went in, and the identical script ran again (`after_run.csv`).
Same code, same 30 cases, same scorer, both times — that's what makes the
numbers reproducible rather than a one-off feeling.

## The numbers

| | Baseline | After | Change |
|---|---|---|---|
| **Average rubric score (0-3)** | **1.77** | **1.93** | **+0.16** |
| Score of 3 (hit the specific hook) | 6 / 30 | 10 / 30 | +4 |
| Score of 2 (generic but personalized) | 14 / 30 | 11 / 30 | -3 |
| Score of 1 (no personalization at all) | 7 / 30 | 6 / 30 | -1 |
| Score of 0 (blocked / wrong tone / commented on a SKIP case) | 3 / 30 | 3 / 30 | 0 |
| Generic-phrase failures (R4/TEMPLATE3 flag from the quality gate) | 0 / 30 | 1 / 30 | +1 |

## What actually changed

One prompt instruction in `src/outreach/copy.py`'s `_STYLE_RULES`, going in
as the assumption *before* measuring baseline was that yesterday's
banned-phrase/template-question problem (found via the live demo) would
still be the dominant failure here. Measuring the baseline first proved
that assumption wrong: **zero of the 30 baseline comments tripped a
banned-phrase or 3-beat-template flag.** The real, measured problem was
specificity — 14 comments passed every rule but engaged with the post's
general topic rather than its one distinctive detail, and 7 more showed no
personalization signal at all.

So the one change tested was a new instruction telling the model to find
the single most distinctive, unusual detail in what it was given — a
number, an admission, a concrete consequence — and build the comment
around that, explicitly ruling out industry/job title/general topic as
counting as "specific." Nothing else changed: same banned-phrase list,
same length rules, same everything else.

## The result, honestly

The average moved from 1.77 to 1.93. The clearest shift is the "3" column
nearly doubling (6 to 10) — the change is doing what it was meant to do,
getting the model to lock onto the standout detail more often. It did not
fix everything: 11 cases still land on "2" (missed the hook), and one
comment in the after-run opened with "You make a solid point" — the exact
banned-opener pattern from yesterday's finding — which the R4 rule caught
and flagged, but which this specificity-focused change was never going to
prevent, because it targets a different failure mode. That's not a
contradiction; it's why "change one thing at a time" is the rule. This
change measurably helped specificity and, by design, did nothing for
banned-opener leakage — a separate, still-open change to test next.

The three score-of-0 cases are identical in both runs: the two condolence
posts and the euphemistic layoff post. **The bot has no concept of "don't
comment at all" and this prompt change didn't touch that** — it's a
different, bigger change (teaching the suggestion pipeline to recognize
these posts and suppress the suggestion entirely, before copy is even
drafted) that deserves its own before/after measurement, not a line item
inside this one.

## Reproducing this

```bash
python scripts/build_golden_set.py       # regenerates golden_set.csv from source
python scripts/run_golden_set.py baseline   # before a prompt change
# ... make one prompt change in src/outreach/copy.py ...
python scripts/run_golden_set.py after      # after it
```

Both `*_run.csv` files are in this directory, one row per case, with the
actual candidate text, the quality-gate flags, and the rubric score and
reason — so any number above can be traced back to the exact comment that
produced it.
