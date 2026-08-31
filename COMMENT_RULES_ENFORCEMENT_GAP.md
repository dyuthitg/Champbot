# Comment Rules: Rules-vs-Reality Gap Table

**Scope:** Do the documented comment rules actually get enforced by the code, or only by asking the model nicely?
**Where the rules live in code (not `services/comment_generator.py` — that path doesn't exist in this repo; flag for Harshil in case it's a rename or a different service):**
- **Prompt** — `src/outreach/copy.py`: `_STYLE_RULES` (lines 37–52, general voice rules for every action) and `_task_for()` (lines 119–144, the comment-specific instruction).
- **Review pass** — `src/outreach/quality.py`: `check_copy()` (lines 151–297) and `_personalization_signals()` (lines 300–338), run on every draft before a human or LinkedIn ever sees it.

Every row below cites a file:line or a real comment from `BOT_OUTPUT_AUDIT_V1.md` / `audit_log_scored.csv`. No row rests on opinion alone.

## The gap table

| Rule | Enforced in code? | Evidence |
|---|---|---|
| **1–3 short sentences** | **No.** No sentence-counting logic exists anywhere in `check_copy()`. | `quality.py:151-297` — the only length checks are char count (`len(body)`) and word count (`len(words) < 8`, line 194). Nothing splits on `.`/`?`/`!` to count sentences. The prompt itself undersells the rule too: `copy.py:139` tells the model "**One or two** sentences," not one to three. |
| **Hard cap ~3 lines** | **Only by proxy, and the proxy is ~2x looser.** | `COMMENT_MAX = 400` (`quality.py:34`), enforced as a blocker at `quality.py:186-189`. At a realistic ~65 chars/line, 400 chars is closer to 6 lines than 3. No code ever counts lines or `\n`. |
| **Banned phrase list** | **Mechanism works; coverage doesn't.** The list is checked and does dock score — but the phrases that actually show up in output aren't on it. | `_TIRED_PHRASES` (`quality.py:38-70`) is checked at `quality.py:228-231`. It contains no entry for "spot on," "nailed it," "have you found any specific strategies," or "great post" — the exact phrases in the audit's worst comments, e.g. *"You're spot on about the ICP issue... Have you found any specific strategies that work well..."* (`BOT_OUTPUT_AUDIT_V1.md`, "Three worst"). The comment-specific ban "Never 'Great post!'" (`copy.py:142`) has zero corresponding entry in any enforced list. |
| **Must reference something specific** | **Enforced for the headline signal, silently bypassed for the post-text signal.** | `_personalization_signals()` stoplists generic vocabulary before crediting a headline match via `_GENERIC_HEADLINE_WORDS` (`quality.py:323-327`) — but applies **no stoplist** to the `their_post` match three lines later (`quality.py:330-336`). Result: all 58 audited comments scored personalization as satisfied, including the 43/58 that end in the identical formulaic question (`BOT_OUTPUT_AUDIT_V1.md`, "The gate has a specific, fixable hole"). |
| **No flattery / never mention own product** | **Not enforced at all.** No code path checks for either. | `check_copy()` has no product-mention detector and no flattery-specific check distinct from `_TIRED_PHRASES`. Sycophancy phrases ("you nailed it," "spot on") appear in neither `_TIRED_PHRASES` nor `_GENERIC_OPENERS` — hence the audit's `sycophancy` tag on 10/58 comments (`BOT_OUTPUT_AUDIT_V1.md`, ranked taxonomy). |

## Sorted by what it takes to fix

**Prompt problems — fixable this week, no new logic:**
- Extend `_TIRED_PHRASES` / `_GENERIC_OPENERS` (`quality.py:38-70, 110`) with the phrases actually found in output: "spot on," "nailed it," "have you found any specific strategies," "great post." The list mechanism already exists and already runs — this is data entry, not engineering. (Already flagged as fix #3 in `BOT_OUTPUT_AUDIT_V1.md`.)
- Fix the prompt text mismatch at `copy.py:139` — it says "one or two sentences," the documented rule says one to three. One line.

**Missing-code problems — need a design decision and whoever owns `quality.py` (Hemang), not a solo edit:**
- No sentence-count check exists at all (row 1). Needs new parsing logic added to `check_copy()`.
- The char-cap-as-line-cap proxy (row 2) is shared across `connect`/`message`/`comment` (`_limit_for()`, `quality.py:143-148`) — tightening it isn't isolated to comments, so it needs someone who owns the blast radius across all three actions.
- The post-text personalization stoplist gap (row 4) is a small code change, but `quality.py` isn't mine to edit unilaterally — `RAMP_WEEK_REPORT.md` already logs this as an open ask ("Need a decision on whether the quality-gate fix is mine to ship or goes to whoever owns `src/outreach/quality.py`").
- A real flattery/own-product detector (row 5) doesn't exist in any form and needs design — e.g. what counts as "own product" requires knowing the account's product/company name to check against, which today isn't wired into `check_copy()` at all.

**Bottom line:** the rules are good. Three of five are enforced by mechanism only in name — the code checks for the shape of a violation, not for the actual violations happening in production. That's a fixable-this-week problem for two of them, and a "needs Hemang + a booked slot" problem for the rest.
