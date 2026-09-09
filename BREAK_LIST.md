# Break list — first end-to-end run

**What this is:** everything that broke, was missing, or turned out to be wrong
while running the whole loop — scrape, generate, flag, review, approve, post —
on a staging account for the first time. **Date:** 2026-09-04. **Author:**
Dyuthi T G.

Twelve entries. Six are fixed and have tests; five are open with a recommendation;
one is a finding rather than a defect. Nothing here was found by reading the
code — every entry came out of a run, and every entry names the evidence.

Reproduce any of it with:

```
python scripts/staging_run.py --dry-run    # everything except the post
python scripts/staging_run.py              # including the post
```

---

## Fixed today

### 1. There was no scrape stage at all
**Severity:** blocker for the whole comment path.

`suggest.py:298` refuses to propose a `comment` for any target without a
`post_urn`, and `copy.py:99` feeds `post_text` to the model as its grounding
fact. Nothing in the outreach loop ever *set* either one. The only code in the
repo that fetched a prospect's posts lived inside the warm-up runner
(`src/warmup/runner.py:213`) and went straight to creating its own suggestion,
bypassing the review queue entirely.

So the comment path only ever fired when whoever built the import file happened
to paste a post in by hand. It looked like a working feature because the test
fixtures and the August audit script both supplied post text themselves.

**Fixed:** `src/targeting/discover.py::refresh_posts`. Reads through the real
transport, never writes, skips posts the account has already commented on, and
returns counts explaining every target it didn't update. Tests in
`tests/test_discover.py`.

### 2. Profile enrichment didn't exist either
**Severity:** blocker for a realistic prospect list.

A prospect list in the wild is a column of profile URLs. ICP scoring
(`scoring.py`), the copywriter's grounding facts, and R3's personalization check
all need the headline, title and name — and the only way to get them was for a
human to have typed them into the CSV.

**Fixed:** `src/targeting/discover.py::refresh_profiles`. Fills blanks only; a
value that came in on the import wins over a scraped one.

### 3. The spec's banned-phrase list was never wired into the code
**Severity:** high. This is the one that would have been embarrassing on camera.

`COMMENT_QUALITY_SPEC_V1.md` has carried an R4 list since 2026-08-25, filed
under *"This week, no new logic: wire the extended R4 banned-phrase list into
`_TIRED_PHRASES`."* It never got wired. Eleven phrases were in the written rule
and not in the enforced one for ten days.

**Evidence from the run:** three of the five comments the model wrote in the
first pass opened with *"You make a solid point…"* or *"That's a solid
insight…"* — both on the spec's list — and R4 stayed silent on all three.

**Fixed:** the eleven missing phrases are now in `_TIRED_PHRASES`. The two the
spec deliberately excludes (*"it's interesting how"*, *"i've seen teams"*) are
still excluded. `tests/test_guardrail_flags.py` now walks the spec's list and
fails if any entry stops being enforced.

### 4. R5 only matched one tense of each verb
**Severity:** medium.

R5's test names five verbs — *found, find, noticed, seen, tried* — in one tense
each. The run produced *"Did you **notice** any specific trends…"*, which is the
same rule being broken as *"Have you **noticed** any specific trends…"*, and it
sailed through.

**Fixed:** the verb pattern now covers the inflections of the verbs the spec
already chose. Adding *new* verbs or new topic nouns would be chasing a dataset;
that stays entry #7 below.

### 5. `NRR?` was shouting, `NRR` was not
**Severity:** low, but it fires on our own ICP's vocabulary.

The gate flagged *"…for boosting NRR?"* as shouting in caps. Two causes, both
real:

- the length test ran on the **unstripped** token, so a trailing question mark
  pushed a three-letter acronym over the four-character threshold — whether an
  acronym counted as shouting depended on where it landed in the sentence;
- `NRR` wasn't in the allow-list, while `ARR` and `MRR` two entries above it
  were.

**Fixed:** punctuation is stripped before both tests, and the allow-list gained
the metrics our ICP actually posts about. Two regression tests.

### 6. The harness said "no breaks" while shipping bad copy
**Severity:** high — this one hides all the others.

The first dry run reported zero breaks while approving:

> *"That's a fascinating approach, Amaya. It's interesting how simplifying the
> onboarding process can lead to such significant improvements. Have you noticed
> any other elements that users found confusing before the update?"*

A validation opener wrapped around the exact question shape the August audit is
named after — scored 100/100, no flags, green run.

**Fixed:** `stage_second_opinion` now re-grades the approved comment with the
August audit's own taxonomy (`scripts/score_audit.py`), which was written
independently of the gate and knows nothing about it. When the two graders
disagree, the run records a break. It has fired on every run since — see #10.

---

## Open, with a recommendation

### 7. R5's topic-noun list is still too narrow — and now there's data
**Severity:** medium. **Owner:** needs a decision, not a patch.

The spec logs this honestly as a v2 item: broaden topic-noun detection *"once
there's a second batch of data to validate against, not before."* That batch now
exists. Across three staging runs the model produced, all in the R5 shape and
all missed:

- "Have you noticed any other **elements** that users found confusing"
- "What kind of **feedback** did you get from users"
- "Have you noticed any changes in user **engagement** or **retention**"

The last one is the exact pair the spec already named as a known gap in August.
Three runs, three misses, same shape.

**Recommendation:** broaden the noun test from a fixed list to "any noun phrase
following *any/specific/other*" inside a question that already matched the
pronoun-and-verb half. Validate against the 58-comment audit set before shipping;
the risk is false positives on genuine questions, and R5's whole value is that it
doesn't have any today.

### 8. Nothing detects a mention of our own product
**Severity:** medium. **Owner:** whoever owns `quality.py` — it needs new inputs.

The spec's automatic-reject list, item 8, includes *"a mention of the sender's
own product."* `COMMENT_RULES_ENFORCEMENT_GAP.md` already recorded that this is
*"not enforced at all"*, and the run confirmed it live: the model wrote

> *"…At **Champions Ranch**, we've seen how tailored follow-ups can boost
> retention after the first week."*

into a comment on a stranger's post, and nothing fired.

**Recommendation:** `check_copy()` doesn't know the account's own company or
product name today — that's the actual blocker, not the string match. Pass the
account's brand terms in alongside `target` and this becomes a five-line check.

### 9. An action inside the undo window is silently lost on reload
**Severity:** medium. **Found:** while recording the demo, which is the only
reason it was found at all.

Approve and Skip are held for five seconds before hitting the API, so Undo can
be real instead of a confirm dialog (`Approvals.tsx:71`, `:236`). If the page is
reloaded or closed inside that window, the timer dies with it and **the action
never happens** — the item quietly reappears in the queue and the operator
believes they dealt with it.

Repro: skip an item, reload within five seconds, look at the queue. The first
take of the walkthrough did exactly this by accident; the skip was gone and the
recording showed a queue that hadn't changed.

**Recommendation:** flush pending actions on `visibilitychange`/`pagehide`
rather than `beforeunload` (which is unreliable), or move the undo server-side —
write immediately and support a real un-reject. In-app navigation is *not*
affected; the timer survives a route change.

### 10. The gate and the audit taxonomy disagree, every single time
**Severity:** this is the finding, not a bug in either one.

On every run, the comment the gate ranked cleanest was graded **weak** by the
August taxonomy. Three separate disagreements, all consistent:

| The comment | Gate | Audit taxonomy |
|---|---|---|
| "It's interesting how much friction can exist in a signup form…" | 100/100, no flags | weak — `validation_opener` |
| "Interesting approach to onboarding! I've seen similar results…" | 100/100, no flags | weak — `validation_opener`, `exclamation_hype` |
| "That's a significant improvement! Have you considered A/B testing…" | 100/100, no flags | weak — `validation_opener`, `exclamation_hype` |

Two concrete rules to settle, not a vague "align them":

- **Validation openers.** The audit taxonomy treats any opener that agrees
  before contributing as a failure. The spec deliberately allows *"it's
  interesting how"*, because one of the six good-graded comments uses it. One of
  those two positions has to move, and I don't think it should be mine by
  default — the taxonomy was built from how the copy reads at scale.
- **Exclamation marks.** The spec's R7 allows one. The taxonomy allows none.
  A one-line disagreement that currently makes every run look like a failure.

**Recommendation:** settle both in the spec's v2, then the second-opinion check
in #6 can become a hard gate instead of a warning.

### 11. `import_targets` scores before the data exists to score with
**Severity:** medium, and it silently produces an empty queue.

`import_targets` runs ICP scoring at import time. A realistic handle-only list
has no headline, title or company yet, so:

- handle-only target scores **0** → below a relevance floor of 60 → filtered out
- the same target after enrichment scores **92**

An operator importing a list of profile URLs would get an empty queue and no
explanation. The staging harness works around it by importing with `icp=None`,
enriching, and scoring afterwards — but the product's own import path can't do
that.

**Recommendation:** have the import endpoint run `refresh_profiles` before
scoring, or defer scoring to first use. The workaround should not stay in a
script.

---

## Not a defect, but the most useful thing the run said

### 12. Banning phrases moves the tic; it doesn't remove it
As soon as R4 started enforcing *"You make a solid point"*, the very next run
produced **four out of five** comments opening with *"It's interesting how…"* —
a phrase that is not on the list, does the identical job, and reads exactly as
canned once you have seen it four times in a row.

This is the August audit's central argument, reproduced live in one working day:
banning strings is whack-a-mole, banning the *shape* is what holds. It is the
strongest argument available for prioritising #7 over adding more phrases to #3.

---

## What the run got right

Worth recording, so the list isn't only failures:

- The transport built genuine Voyager requests — device fingerprint, CSRF
  header, cookie jar, the GraphQL query hashes — and parsed genuine responses.
  The modern "dash" shape was tried first every time and the legacy shapes were
  never reached, which is the ordering the transport is supposed to have.
- The off-ICP prospect with no posts (Sam Taylor, warehouse supervisor) was
  filtered at the relevance floor and reported as such, not silently dropped.
- Approve re-ran the gate, the pacer picked a send time, the caps were consumed
  through the real rate limiter, and the comment reached the far end via the
  `dash` shape with HTTP 201.
- Every LinkedIn call the run made is recorded in
  `staging_run/voyager_requests.jsonl`, credentials redacted.
