# Bot Output Audit v1

**Scope:** 58 AI-generated LinkedIn comments, produced by running the real production pipeline (targeting → copywriter → quality gate) against 58 synthetic prospects, each with a realistic SaaS-growth post. **Date:** 2026-08-21. **Data:** `audit_log_scored.csv`. Provenance caveat at the bottom — read it before quoting this externally.

## Headline finding

The bot writes one comment: **validate → restate the thesis → "have you found any specific strategies?"** 43 of 58 comments (74%) end with that exact question shape, and 25 of 58 run the full three-beat skeleton. Individually each comment reads fine. Stamped on 58 different people from one account, it's an unmistakable bot fingerprint — and nothing in the pipeline currently catches it before send.

## The gate has a specific, fixable hole (criticism, not a summary)

`src/outreach/quality.py` — the deterministic gate every comment must pass — scored **all 58 of these comments 100/100.** That's not a calibration issue, it's a bug in one function. `_personalization_signals()` (lines 300–338) already knows generic vocabulary shouldn't count as evidence a profile was read — it stoplists words like "growth," "strategy," and "platform" against `_GENERIC_HEADLINE_WORDS` before crediting a headline match (line 324–327). But the post-text check three lines below it (330–336) applies **no stoplist at all**: any shared 6+ letter word between the comment and the post text is credited as `their_post` personalization. Since every comment here is *about* activation, retention, or onboarding because the post was, and those words are all 6+ letters, this check passes automatically almost every time — including on the "you nailed it... have you found any specific strategies" template. Deep built the right mechanism (the stoplist) and then didn't point it at the input that actually needed it. That's the reason the audit had to be done by hand: the gate that's supposed to make this unnecessary is structurally blind to it.

## Ranked failure taxonomy

Severity = average points below 100 for comments carrying that tag (`100 − avg audit_score`); ranked by **frequency × severity** — total damage contributed to the batch — not raw count. Tags co-occur, so this is a relative ranking, not a clean partition.

| Rank | Failure | n | Severity | Freq×Sev | Likely cause (guess — unverified) |
|---|---|---|---|---|---|
| 1 | `formulaic_strategy_question` | 43 | 56.4 | 2425 | Prompt likely tells the model to close with an engaging question but never bans generic ones, so it defaults to the same low-effort closer regardless of post. |
| 2 | `validation_opener` | 32 | 62.8 | 2010 | Prompt likely pushes a warm/rapport-building tone with no ban on stock affirmation phrases ("you make a great point"), so the model opens the same way every time. |
| 3 | `template_3beat` | 25 | 66.0 | 1650 | Not an independent cause — it's #1 and #2 firing on the same comment. Compounding, not a third defect. |
| 4 | `no_specific_detail` | 20 | 69.2 | 1384 | Likely the model (gpt-4o-mini, swapped in because the configured `claude-3.5-sonnet` isn't a valid OpenRouter slug) paraphrases the post's theme instead of quoting a distinguishing detail, and nothing in the prompt requires a concrete callback. |
| 5 | `sycophancy` | 10 | 61.0 | 610 | Same warmth instruction as #2, pushed one notch further into flattery ("nailed it," "spot on") with no ceiling on praise language. |
| 6 | `exclamation_hype` | 2 | 50.0 | 100 | Too rare to be a prompt pattern — probably just per-generation variance. |

**Read >30% frequency as a pipeline problem, not a copy problem:** three of six labels clear that bar.

## Verdict split

**Good: 6 (10%) · Weak: 41 (71%) · Fail: 11 (19%)** — nothing here is embarrassing on its own; the volume of sameness is the failure.

## Three worst (verbatim)

- **score 5** `validation_opener, formulaic_strategy_question, template_3beat, sycophancy, no_specific_detail`
  > You nailed it with the team aspect of activation. I've seen how alignment between product and marketing can significantly boost retention. What strategies have you found effective in fostering that collaboration at Trackr?
- **score 5** `validation_opener, formulaic_strategy_question, template_3beat, sycophancy, no_specific_detail`
  > You're spot on about the ICP issue. It's interesting how a narrow focus can actually improve both activation and retention. Have you found any specific strategies that work well for refining ICP in a B2B context?
- **score 10** `validation_opener, formulaic_strategy_question, template_3beat, no_specific_detail`
  > Interesting approach, Felix. I've seen similar results with simplified messaging in onboarding processes. Did you notice any specific trends in user behavior after switching to the winning version?

## Three best (verbatim)

- **score 90** `good` — Net revenue retention really does cut through the noise. It's interesting how focusing on existing customers can often yield better insights than chasing new ones. How do you balance retention efforts with acquiring new customers at Cloudrise?
- **score 90** `good` — Your perspective on PLG as a promise resonates. It's interesting how the product's clarity can drive user engagement. How do you see this evolving as user expectations change in the B2B space?
- **score 90** `good` — Rewriting empty states can definitely change the user experience. Have you seen a noticeable impact on activation rates since implementing that change? I'm curious about how you approached the messaging to ensure it resonates with users right from the start.

## What I'd fix first

1. **Stoplist the post-text personalization check** — apply `_GENERIC_HEADLINE_WORDS` (or a domain-specific superset covering "activation," "retention," "onboarding," "strategies") to the `their_post` signal in `quality.py:330-336`, the same way it's already applied to the headline signal three lines up. One-line fix, closes the exact hole above.
2. **Add an account-level repetition check.** `check_copy()` is stateless per call — it cannot see that the same account is about to post the same skeleton on 25 different people. A cheap n-gram/structure-overlap check across an account's last N pending suggestions, run before send, catches what per-comment scoring never will.
3. **Extend `_TIRED_PHRASES` (or a sibling list) to the opener/closer stems found here** — `"you make a great point"`, `"have you found any specific strategies"`, `"spot on"`. The pattern-list mechanism already exists in this file for exactly this purpose; it just wasn't pointed at these phrases.

---
**Method & caveats:** No CSV export of a real audit log exists yet and there's no comment history in a live account, so this run used 58 synthetic prospects through the real suggest → copywriter → quality-gate path, with `gpt-4o-mini` in place of the configured (invalid on OpenRouter) `claude-3.5-sonnet`. The taxonomy and the gate finding are real regardless; the specific phrasing distribution may shift with the intended model. Do not present this as live-account data. Full data: `audit_log_scored.csv`. Re-run: `python scripts/audit_run.py && python scripts/score_audit.py`.
