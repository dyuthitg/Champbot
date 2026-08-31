# Ramp Week Report

**Role:** Brand voice / social copy auditor
**Week of:** 2026-08-17 – 2026-08-21
**Author:** Dyuthi T G

## This week

Objective: get from zero visibility into the bot's LinkedIn comments to a scored, ranked failure taxonomy Harshil and Deep can act on.

- **Day 1 (08-20):** No audit-log export existed and no comment history was reachable in a live account. Built `scripts/audit_run.py` to generate a real 58-comment batch through the actual production pipeline (targeting → copywriter → quality gate) against synthetic prospects, wired up the LLM writer (it was silently falling back to templates), and exported the audit log. Built `scripts/score_audit.py` and a first-pass structural taxonomy. Scored all 58, including the good ones.
- **Day 2 (08-21, today):** Turned the raw scores into a ranked failure taxonomy (frequency × severity, not raw count), added a one-line cause guess per failure type, and wrote **Bot Output Audit v1** — including a specific, code-level criticism of the quality gate Deep built, not just a summary of the numbers.

## Headline finding

The bot writes one comment — validate → restate → "have you found any specific strategies?" — and stamps it on every post. 74% of comments end with that exact question shape. The deterministic quality gate scored all 58 of them 100/100; it has a specific blind spot (detailed in the audit) that lets this pass every time.

## Shipping today

| Deliverable | What it is |
|---|---|
| **`BOT_OUTPUT_AUDIT_V1.md`** | Primary deliverable — ranked taxonomy, verdict split, verbatim worst/best, and a specific criticism + fix for `quality.py`'s personalization check |
| **This report** | Week summary + demo script |
| `audit_log_scored.csv` / `audit_report.md` | Underlying data and the raw scorer output (evidence, not the pitch) |

## 15-minute demo script

**0:00–0:02 — Setup.** One sentence: 58 real comments through the real pipeline, scored by hand against a structural taxonomy, because the product's own quality gate passed all 58 at 100/100.

**0:02–0:05 — The number that matters.** Put the ranked taxonomy table on screen. Lead with `formulaic_strategy_question` at 43/58 (74%) and `template_3beat` at 25/58 — say the freq×severity ranking out loud, not just the raw counts.

**0:05–0:09 — Read the three worst comments aloud, verbatim, with a pause after each one.** Don't summarize them — read them as if you were the recipient seeing it on your own post. This is the fastest way to make the room agree without arguing the taxonomy:

> "You nailed it with the team aspect of activation. I've seen how alignment between product and marketing can significantly boost retention. What strategies have you found effective in fostering that collaboration at Trackr?"

> "You're spot on about the ICP issue. It's interesting how a narrow focus can actually improve both activation and retention. Have you found any specific strategies that work well for refining ICP in a B2B context?"

> "Interesting approach, Felix. I've seen similar results with simplified messaging in onboarding processes. Did you notice any specific trends in user behavior after switching to the winning version?"

**0:09–0:12 — The criticism.** Show `quality.py:300-338` side by side: the headline check stoplists generic words before crediting a match; the post-text check three lines below does not, so any 6+ letter word shared with the post — "activation," "retention," "onboarding" — auto-passes personalization. That's the specific reason all 58 scored 100/100. Name it as Deep's code, name the exact gap, don't soften it into "the gate could be more robust."

**0:12–0:15 — What I'd fix first, in order, and ask for a decision.** Three items, already in the audit doc. Ask: does the stoplist fix (item 1) go in this sprint, or does someone want to argue the taxonomy first?

## Blockers / asks

- No real audit-log CSV export exists yet — everything here is synthetic-prospect data through the real pipeline, not a live account. If a live-account dump becomes reachable, re-run `score_comments.py` in `audit/` against it to confirm the pattern holds outside synthetic data.
- Need a decision on whether the quality-gate fix (item 1 in the audit) is mine to ship or goes to whoever owns `src/outreach/quality.py`.

## Next week

- If greenlit: patch the `_personalization_signals` post-text stoplist gap and re-score the same 58 comments to confirm the gate now catches what it missed.
- Scope the account-level repetition check (item 2) — needs a decision on where it runs (pre-send gate vs. a periodic account health check).
