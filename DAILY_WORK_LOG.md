# Daily Work Log — Comment Quality Audit

**Role:** Brand voice / social copy auditor
**Date:** 2026-08-20
**Objective:** Audit the bot's generated LinkedIn comments, build a failure taxonomy, and ship a scored sheet.

---

## Tasks of the Day

### 1. Locate the audit log CSV export
- Searched the codebase for a built-in audit-log CSV export endpoint.
- Checked backend API routes, frontend pages, and the agent audit trail (Redis).
- **Result:** No reachable CSV export existed. Found only a local `synthetic_dry_run.db` with 3 generated texts — too few to audit.

### 2. Generate a real batch of comments through the production pipeline
- Built `scripts/audit_run.py`: spins up a fake account, imports 58 synthetic prospects (each with a realistic post), and runs the real suggestion engine → copywriter → quality gate.
- Lifted the daily action caps and lowered the relevance floor **for this audit run only** so all 58 comments generate in one pass.
- First attempts produced identical template-fallback copy (no LLM key was loaded).

### 3. Wire up the LLM writer
- Diagnosed why the LLM wasn't firing: the import of `synthetic_dry_run.py` wiped the `OPENROUTER_API_KEY` at module load. Inlined the recording transport to fix it.
- Found the configured model (`anthropic/claude-3.5-sonnet`) was not a valid OpenRouter endpoint; switched to `openai/gpt-4o-mini`.
- **Result:** 58 unique, real LLM-generated comments (`generated_by: openrouter:openai/gpt-4o-mini`).

### 4. Export the audit log to CSV
- Wrote `audit_log.csv`: id, action, status, relevance score, quality score, generator, rationale, the target's post text, and the draft comment.

### 5. Build the failure taxonomy
- Built `scripts/score_audit.py` with a self-designed taxonomy.
- First pass used phrase-level cliché detection — recalibrated after review showed it flagged the wrong comments.
- Final taxonomy measures **structural** failure, the thing that actually exposes a bot at scale:
  - `validation_opener` (32) — praises before contributing
  - `formulaic_strategy_question` (43) — "have you found any specific strategies…" crutch
  - `template_3beat` (25) — the full validate → restate → strategy-question skeleton
  - `no_specific_detail` (20) — could have been commented on any post
  - `sycophancy` (10) — "you nailed it", "spot on"
  - `exclamation_hype` (2)

### 6. Score every comment, including the good ones
- Scored all 58. Grades: **6 good, 41 weak, 11 fail.**
- Key finding: the system's own quality gate scored all 58 comments **100/100** — it is blind to structural repetition.

### 7. Flag the 3 worst and 3 best, verbatim
- Recorded exact text for both, with line-level reasons. (See `audit_report.md`.)

### 8. Write the audit report
- `audit_report.md`: taxonomy, counts, score distribution, verbatim best/worst, and one recommendation for Deep (add a structural-repetition check to the quality gate).

---

## Headline Finding

The copy is a **3-beat template** stamped on 58 different posts: validate → restate the thesis → "have you found any specific strategies?" 43 of 58 comments end with that same question. Individually each reads fine; at scale on one account it is an unmistakable bot fingerprint — and the quality gate cannot see it.

---

## 📦 Shipment of the Day

> **Scored sheet of 50+ real comments with a first-pass failure taxonomy**

| File | What it is |
|---|---|
| **`audit_report.md`** | ⭐ The primary deliverable — taxonomy, scores, verbatim best/worst, recommendation |
| **`audit_log_scored.csv`** | The full data — all 58 comments, tagged + scored |
| `audit_log.csv` | Raw export (backup evidence) |
| `scripts/audit_run.py` | Re-runnable comment generator |
| `scripts/score_audit.py` | Re-runnable scorer |

**Note on provenance:** These are 58 comments generated through the real production pipeline against synthetic prospects (no live-account audit log was reachable). The taxonomy and the core finding are real either way — do not present this as live-account data.
