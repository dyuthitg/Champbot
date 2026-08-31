# System Trace: Data, Pipeline & Model Usage

*An end-to-end walkthrough of the Social-Bot-LinkedIn codebase — how data is stored, what flows in and out, and how the AI model is used per client.*

---

## The Trace Cycle (one message's journey)

```
CSV/LinkedIn export upload
   → OutreachTarget row (Postgres)
   → rule-based ICP scoring (0–100)            [src/targeting/scoring.py]
   → 6 suggestion gates                        [src/outreach/suggest.py]
       (floor, suppression, dedupe, capacity, budget, copy quality)
   → LLM drafts copy via OpenRouter            [src/outreach/copy.py]
   → deterministic quality gate + retries      [src/outreach/quality.py]
   → human approve/edit/reject in React UI     [frontend/src/pages/Approvals.tsx]
   → pacing + Redis rate limits + warm-up gates
   → send via LinkedIn Voyager API (Playwright browser fallback)
   → reply-sync cancels follow-ups if the person replies
```

---

## 1. How is the data stored, and in what format?

**Two stores, one format convention:**

### PostgreSQL (permanent memory)

SQLAlchemy ORM models on a shared declarative `Base`, migrated via Alembic (`src/database/`, `alembic/`). SQLite is used for tests. Key tables:

| Table | Contents | Format notes |
|---|---|---|
| `organizations` / `users` | Tenancy spine (Clerk auth, org settings) | `settings` is a JSON column for org-level config |
| `connected_accounts` | LinkedIn accounts | Session cookie (`li_at`) stored **encrypted** (`src/accounts/crypto.py`) |
| `icp_profiles` | Targeting criteria per client | Criteria as JSON lists (titles, keywords, industries, exclusions…) |
| `outreach_targets` | Prospects | Profile fields as text columns + a `context` JSON blob (recent post, how found) + `relevance_reasons` JSON list |
| `outreach_suggestions` | The unit of review | Draft/final text, `quality_warnings` JSON, `result` JSON; status lifecycle: `pending → approved → scheduled → sent / rejected / cancelled` |
| `campaigns` / `campaign_tasks` | Campaign config | `target_urls`, `account_ids`, `actions` all stored as JSONB |
| `account_activity` | Audit ledger | Every attempted action, warm-up stage, variant, error |

**Format:** structured relational rows, with **JSON/JSONB columns** for anything flexible. Cross-dialect `Uuid`/`JSON` types so the same schema runs on Postgres (prod) and SQLite (tests).

### Redis (scratchpad)

Rate-limit counters per account (hour / day / rolling-week windows), shared across app replicas. Not a document store — purely counters/state.

**In short:** structured relational data + JSONB blobs, not files or a vector store. Encrypted secrets. Redis for counters.

---

## 2. What's the input, and what's the output?

### Inputs

- **A list of prospects** — CSV upload, LinkedIn search export, WhatsApp link scans, or post engagement (`source` field: `whatsapp_link | post_engagement | csv | manual`). Each becomes an `OutreachTarget` with name, title, company, headline, industry, location, plus a `context` JSON (e.g. recent post text).
- **The user's ICP definition** — target titles, seniorities, industries, keywords, exclusions, locations, a `value_proposition`, and free-text `instructions` that get injected into the AI prompt.
- **The user's LinkedIn session cookie** (`li_at`) per connected account — never a password.
- **Human decisions** in the approvals inbox (approve / edit / reject).

### The pipeline

1. Prospects scored 0–100 by **plain matching rules** (`src/targeting/scoring.py`) — deliberately *not* AI
2. Six gates filter them (`src/outreach/suggest.py`): score floor, suppression, duplicates, capacity, approval budget, copy quality
3. AI drafts a message (`src/outreach/copy.py`), graded 0–100 by a **deterministic** quality gate (`src/outreach/quality.py`) — also not AI — with up to 3 rewrites
4. **A human approves/edits/rejects** in the Approvals UI — nothing sends without this
5. Pacing picks a natural send time; rate limits re-checked at send time
6. Delivered via LinkedIn's internal Voyager "mobile" API, with Playwright browser as fallback

### Outputs

**Primary output:** an approval inbox of drafted, quality-scored `OutreachSuggestion`s —

- Connection notes (<300 chars), first messages (<500 chars), post comments (<300 chars)
- Each with a relevance score (0–100), human-readable reasons ("Title matches 'Head of Growth'"), a quality score with warnings, and which model/template generated it (`generated_by`)

**Then:** actual LinkedIn actions (connection notes, messages, comments, likes), plus funnel tracking back in the DB (`invited → accepted → replied → booked`).

If a prospect replies, all queued messages to them are cancelled automatically.

---

## 3. What model is used, and how does it adapt per client?

**Provider: OpenRouter** (OpenAI-compatible API), with **two model slots** (`src/infrastructure/llm/provider.py`):

| Slot | Default model | Purpose |
|---|---|---|
| `CONTENT` | `anthropic/claude-3.5-sonnet` (temp 0.7, 512 tokens) | Writes the outreach copy |
| `CLASSIFICATION` | `meta-llama/llama-3.1-8b-instruct` (temp 0.0, 64 tokens) | Fast/cheap labels & intent |

Both are overridable via env vars (`OPENROUTER_CONTENT_MODEL`, `OPENROUTER_CLASSIFICATION_MODEL`). If no API key exists, it falls back to plain templates — the product degrades, never breaks.

### Per-client approach — the key design point

**No fine-tuning and no per-client model.** One shared model is personalized entirely **at the prompt level**, in this resolution order (`provider.py` docstring):

```
per-org override (OrgModelSettings — wired in a later phase)
  → backend env-config default
    → hard-coded fallback
```

The `Organization.settings` JSON column and an async `settings_resolver(org_id, slot)` hook already exist so each client org can eventually pick its own models; `org_id` is already threaded through every LLM call.

### Per-client behavior today comes from prompt construction (`copy.py:build_messages`)

- The client's ICP **value proposition** and **free-text instructions** are injected into the system prompt (*"these override the defaults where they conflict"*)
- A **sender brief** — the account's name/headline (writing *as that person*)
- A **recipient brief** built from the prospect's real profile data (title, company, headline, recent post, shared group)

### What the model deliberately does *not* do

Scoring and spam-checking are **rule-based**, because (as the code says):

> *"a model asked 'is this spammy?' will happily approve its own output."*

The LLM only writes copy for the small set of prospects that survive the deterministic gates.
