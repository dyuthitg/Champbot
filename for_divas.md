# LinkedIn Outreach Bot — Explained for a Newbie

## TL;DR

A LinkedIn outreach assistant for a salesperson. You tell it who you want to meet, it finds matching people, writes a personal-sounding message to each, shows you **every message for approval**, then sends them slowly and naturally — like a human — so LinkedIn never realizes software is involved.

The key word is **approval**. Almost every line of code is a *brake*, not an accelerator. The product isn't "send lots of messages" — it's *"send few enough, slowly enough, personally enough that neither LinkedIn nor the recipient can tell it's software."*

**Parts** (the office analogy): React screens = storefront. FastAPI = front desk. `src/targeting|outreach|warmup|accounts` = the managers. Transports = the hands that touch LinkedIn. Postgres = filing cabinet. Redis = tally counter. AI (OpenRouter) = freelance copywriter.

**Journey of one message**: connect account via session cookie (encrypted) → define ideal customer → score everyone 0–100 by plain rules → survive 6 gates → AI writes draft → plain-rules spam filter grades it (instant block on placeholders/booking links; −30 for "Hi there"; −25 for no personal detail) → **human approves/edits/rejects** → pacing picks a human-like send time (working hours, random wobble) → re-checks everything at send moment → shared Redis counters enforce hourly/daily/weekly limits → delivered via LinkedIn's own mobile API, fallback to a real browser.

**Warm-up**: new accounts walk a 3-week probation (observe → react → converse → publish → connect → full). Early stages make actions *impossible*, not just limited. Poor results move the account *backwards*.

**Listening**: sync checks who accepted/replied. A real reply **cancels everything** queued to that person.

**One idea to take away**: writing a script that sends 500 messages is fifty lines. This codebase's real product is the discipline — the brakes, the human review, the pacing.

---

## The full walkthrough

### What it is, in one sentence

It's a tool that helps a salesperson find the right people on LinkedIn, write a personal-sounding message to each one, get a human to approve it, and then send those messages slowly and carefully over days and weeks so LinkedIn never suspects a robot is involved.

### The office analogy

Think of the whole system as a small office building:

| Part | Code | Analogy |
|---|---|---|
| **Frontend** | `frontend/` (React) | The storefront — screens you click: dashboard, approvals inbox, accounts page |
| **API** | `src/api/` (FastAPI) | The front desk — every click comes here, gets understood, routed onward |
| **Business logic** | `src/targeting/`, `src/outreach/`, `src/warmup/`, `src/accounts/` | The managers doing actual thinking: who to contact, what to say, when it's safe |
| **Hands** | `src/infrastructure/transports/` | The only part that actually *touches* LinkedIn |
| **Database (Postgres)** | `src/database/`, `src/campaigns/` | The filing cabinet — permanent memory: people, messages, approvals |
| **Redis** | `src/infrastructure/rate_policy.py` | A tally counter on the door — "how many invites has this account sent this hour/day/week?" |
| **AI writer** | `src/infrastructure/llm/` (via OpenRouter) | The freelance copywriter you pay per message |
| **Scheduler** | `src/scheduler/` | The night-shift manager who walks the floor every few minutes |
| **Login** | Clerk (third-party identity service) | The security guard at the building entrance |

Each customer company ("tenant") gets its own sealed filing cabinet (`src/tenancy/`) so no two companies see each other's data.

### The journey of one message, start to finish

**Step 1 — Connect an account** (`src/accounts/`)
You don't give your password. You give a **session cookie** (`li_at`) — the "already logged in" badge your browser holds. The app immediately asks LinkedIn "who am I?" — if no answer, the account is marked broken *right then*, not discovered dead three days later. The cookie is **encrypted** before storage, decrypted only when used. Each account also gets a permanent fake "device fingerprint" — LinkedIn trusts an account that always looks like the same phone, and distrusts one that looks like a different device every day.

**Step 2 — Describe your ideal customer** (`src/targeting/`)
You fill an ICP form (job titles, industries, keywords, locations, things to *exclude*), then upload a list of people (CSV).

**Step 3 — Score everyone out of 100** (`src/targeting/scoring.py`)
Title match → 35 pts, industry → 20, keywords → 20, seniority → 15, location → 10. Notably: **no AI here**, on purpose — rules you can *read and explain* beat an AI "similarity score" that explains nothing, and scoring runs on thousands of people cheaply. One banned keyword = score zeroed. An empty form matches **nobody**, not everybody — so it can't accidentally mean "message the whole database."

**Step 4 — Six gates before someone is even suggested** (`src/outreach/suggest.py`)
Below score floor? Dropped. Ever marked "never contact"? Untouchable forever. Duplicate? Never messaged twice. Account capacity? No more than legally sendable. **Approval budget**: a hard daily cap on how many suggestions you see — because a queue of 200 gets rubber-stamped, which would silently destroy the value of human review. The app tells you honestly: *"Reviewed 40, suggesting 6: 12 below floor, 8 already suggested."*

**Step 5 — AI writes the message** (`src/outreach/copy.py`)
Given everything known about the recipient, plus a hard prohibition list: no flattery, no invented facts, no links, no emoji, no "I hope this finds you well," no asking for a meeting. No AI key configured? Falls back to plain templates — duller, never broken.

**Step 6 — The spam filter checks its own work** (`src/outreach/quality.py`)
Every draft graded 0–100 by **plain rules, not AI** — the file explains: *a model asked "is this spammy?" will happily approve its own output.* Instant blocks: leftover `{{placeholders}}`, booking links in a first message, over-long text. Points off: tired phrases ("just checking in", "synergy"), generic openers ("Hi there"), SHOUTING, too many `!`, all-me-no-you. And the clever one: **no personal detail at all** → −25 pts ("this could have been sent to anyone"). It checks whether the person's actual name/company/title appears — generic words like "growth" don't count. Fail → tells the AI what's wrong, asks for a rewrite, up to three tries.

**Step 7 — A human says yes or no** (`frontend/src/pages/Approvals.tsx` → `src/outreach/execute.py`)
You see the person, why they were picked, the draft, its quality warnings. Approve / edit / reject. If you **edit** the text, it re-runs the quality filter — *a human typing a booking link is as bad as an AI doing it*. Reject with "never contact again" = suppressed forever.

**Step 8 — It waits for a natural moment** (`src/outreach/pacing.py`)
Approval ≠ send now. Only during working hours in your timezone; weekends reduced but *not zero* (being active exactly Mon–Fri 9–5 is itself a robot signature); a random 45s–15min wobble on every send; minimum gap between sends. The principle: *twenty invites across a Tuesday afternoon is a person; twenty in 90 seconds at 4am is software — even if both stay under the daily limit.*

**Step 9 — Final checks at the moment of sending** (`src/outreach/execute.py`)
The only file that tells LinkedIn to do anything re-checks *everything*: genuinely approved? Still due? Text still passes quality? Account allowed? Working hours? (If not — *reschedule, don't fail*.) Capacity under global limit? The design philosophy in one line: **"A missed send is recoverable; an action that shouldn't have been sent is not."**

**Step 10 — The shared tally counter** (`src/infrastructure/rate_policy.py`)
Limits live in **Redis**, not app memory — with several copies of the app running, each kept its own private count, and "150/day" secretly became 150 × number-of-copies. Now all copies share one counter per account. Three windows checked together: per hour, per day, and per **rolling week** (LinkedIn's real limit is weekly — an account can be under its daily limit every single day and still get restricted by Friday). A slot is only consumed when an action is *allowed* — being refused never burns your allowance.

**Step 11 — Delivery** (`src/infrastructure/transports/`)
Two routes: primary = LinkedIn's own internal **Voyager API** (the one their real mobile app uses), disguised as a mobile client — fast, low risk. Fallback = **Playwright driving a real Chrome window** clicking buttons — slower, riskier, but keeps working when Voyager breaks. A router tries the first, silently falls back to the second.

### The warm-up programme

A brand-new LinkedIn account is the most fragile thing in the system — the #1 ban trigger is a quiet account suddenly sending invites. So every account walks a fixed ~3-week path, like a new employee's probation:

```
observe → react → converse → publish → connect → full
  2d       3d       4d        5d        7d
```

- **Observe** — just signs in, reads the feed, a couple likes. Some days nothing.
- **React** — likes/follows people in your space.
- **Converse** — writes real comments.
- **Publish** — posts its own content.
- **Connect** — first few invites, small volume.
- **Full** — normal outreach.

Two details that matter: during "observe," an invitation isn't rate-limited — it's *impossible*, no code path can produce one. And advancement requires **time AND results**: an account with only 8% invite acceptance moves *backwards* a stage; a LinkedIn verification challenge steps it back immediately. Daily volumes are *probabilities*, not fixed numbers — doing exactly 12 likes every day is as obviously robotic as doing 500.

### Listening, not just sending

Everything else decides what to *send*; `src/outreach/sync.py` *listens*, and it's what makes the system safe. It regularly asks LinkedIn two questions: who accepted my invite? (unlocks follow-ups) — and **who replied? (stops everything immediately)**. That second rule is sacred: the moment someone replies, every queued message to that person is cancelled. An automated follow-up landing after a real person answered is the clearest possible sign they were talking to software. Follow-up sequences are deliberately short — invite + 3 messages after acceptance + stop. Booking links: blocked in every automated message, allowed only *after* a real reply shows interest.

### The honest current state

The repo contains **two generations of code**:

- **Older layer** — `main.py`, `README.md`, `src/agents/`: a grand "multi-agent" marketing story (eight autonomous workers, WhatsApp monitor, Kubernetes, Prometheus). Some is real code, but several "agents" are **empty skeletons** — `scheduler_agent.py` is 21 lines admitting "Phase 0 ships a booting skeleton."
- **Newer layer** — `src/api/`, `src/accounts/`, `src/targeting/`, `src/outreach/`, `src/warmup/`, `src/scheduler/`, and the React frontend: the real, carefully-built product.

The scheduler (`src/scheduler/tick.py`) is a night-shift manager that periodically sweeps every account doing three things in strict order: **sync** (pull replies — first, so a reply cancels sends before a follow-up can fire over it), **warm-up** (cheap likes/follows), **send** (approved, due outreach). Failures are isolated per-account: one expired cookie never stops the other nineteen.

### The one idea to take away

**Every feature is a brake, not an accelerator.** Scoring drops people. Quality blocks messages. Warm-up forbids actions. Pacing delays sends. Rate limits refuse. Reply-sync cancels everything. Writing a script that sends 500 LinkedIn messages is fifty lines — anyone can do it. This codebase's real product is the *discipline*: sending few enough, slowly enough, and personally enough that neither LinkedIn nor the recipient can tell software was involved.