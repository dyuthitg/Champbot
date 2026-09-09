# Week 2 report

**Dyuthi T G · 2026-09-04**

Gaps first, because you'll find them anyway and it's cheaper if I say them.

---

## What does not work yet

### 1. Nothing here has ever run against a live LinkedIn account
This is the big one and it hasn't moved since week 1. The demo shows a comment
going the whole way — found, written, flagged, reviewed, approved, paced, sent —
and the send is a real HTTP request built by the real Voyager transport. But it
goes to `scripts/staging/voyager_stub.py`, a local server on this machine that
speaks LinkedIn's shapes, **not to linkedin.com**.

What that does prove: the request-building, the device fingerprint, the CSRF
header, the GraphQL query hashes, the dash-then-legacy fallback ordering, and
the response parsing all work. Those are where the shape bugs live, and a fake
transport object would have proved none of it.

What it does not prove: that LinkedIn accepts any of it. The query hashes in
`mobile.py` were captured from a browser session in August and rotate without
notice. `.env.example` has said since week 1 that *"the mobile transport has not
been validated against a live account yet"*, and it still hasn't.

**To close it I need three things I don't have:** a burner LinkedIn account
nobody minds losing, an `ENCRYPTION_KEY` so credentials can be stored properly,
and a Redis instance so the daily caps are actually enforced. Plus a decision
from Hemang, because the first live run is the one that can get an account
restricted.

### 2. Two rules the spec has written down still don't block anything
The 1-to-3-sentence rule and the formulaic-question rule are visible in the
queue but advisory — they cost nothing and stop nothing. They sit in a gate
shared with connection requests and direct messages, so tightening them changes
what gets rejected on all three actions. That needs Hemang and a booked slot.

### 3. The quality gate and the August audit disagree on every run
Every single run this week, the comment the gate ranked cleanest was graded
*weak* by the August audit's own taxonomy. Not occasionally — every time. The
disagreement is narrow and settleable (validation openers, and whether one
exclamation mark is allowed), and it's written up as entry #10 of
`BREAK_LIST.md`. Until it's settled I can't turn that second opinion into a
hard gate, which means the gate can still pass copy I'd personally reject.

### 4. Four things the loop needs that the product still can't do
- Detect when a comment name-drops **our own** product. Confirmed live: the
  model wrote *"At Champions Ranch, we've seen…"* into a stranger's thread and
  nothing fired.
- Import a plain list of profile URLs. It scores them before it knows anything
  about them, so everyone lands below the relevance floor and the queue comes
  back empty with no explanation.
- Survive a page reload inside the five-second undo window. The action is
  silently dropped and the operator thinks it happened.
- Discover *who* to contact. Targets still arrive as a list someone else built;
  there's no search.

---

## What now works that didn't on Monday

### The loop runs end to end, and it's re-runnable
`python scripts/staging_run.py` does the whole thing in about fifteen seconds
and writes a transcript, a break list, and a log of every LinkedIn call it made.
`--dry-run` stops before the post. The dry run came first, which is how most of
the break list got found before anything was recorded.

### The scrape stage exists now
It didn't before. `suggest.py` has always refused to propose a comment for a
target with no post attached, and nothing in the outreach loop ever attached
one — so the comment path only worked when a human had pasted the post into the
import file by hand. It looked like a working feature because every test fixture
supplied its own post text.

`src/targeting/discover.py` is that missing stage: hand it a column of profile
URLs, it resolves who those people are and finds what they recently posted. It
reads and never writes, and it won't offer a post the account has already
commented on. Eight tests.

### Guardrail flags are visible and filterable
Shipped earlier this week and now proven under real generated copy: every
comment in the queue carries named labels for what it broke, the operator can
filter and sort by failure type, and the editor counts characters and sentences
live. In the demo you can see the queue say *"Generic phrase 1, Formula question
1, Nothing flagged 3"* before a single comment has been read.

### Six real defects found and fixed
Full detail in `BREAK_LIST.md`. The two worth naming here:

**The spec's banned-phrase list had never been wired into the code.** Eleven
phrases were in the written rule and not in the enforced one, since 25 August,
filed under *"this week, no new logic"*. The run made it obvious immediately:
three of the first five comments opened with *"You make a solid point"* and the
gate said nothing. Now wired, with a test that walks the spec's list and fails
if any entry stops being enforced.

**The harness reported a green run while approving bad copy.** The first dry run
said "no breaks" while approving a validation opener wrapped around the exact
question shape the August audit is named after. The fix was to make the run
re-grade its own output with the audit's independent taxonomy and record a break
when the two disagree. It has fired on every run since — which is the point.

---

## The one thing I'd want you to take away

When R4 started enforcing *"You make a solid point"*, the very next run produced
**four out of five** comments opening with *"It's interesting how…"* instead.
Same job, same canned feeling, not on any list.

That's the August audit's central argument reproduced inside one working day:
banning strings is whack-a-mole, banning the shape is what holds. It's the
reason I'd rather spend next week broadening the shape rule than adding more
phrases to the list — and the reason I haven't broadened it yet is that the spec
says to validate against real data first, and I'd rather do that properly than
guess twice.

---

## Next week, in the order I'd do it

1. **Live-account validation.** Burner account, encryption key, Redis, one
   comment, watched by a human. Everything above is theoretical until this
   happens, and it needs your go-ahead more than it needs my time.
2. **Settle the two disagreements in the spec** (validation openers,
   exclamation marks) so the second-opinion check can become a hard gate.
3. **Broaden R5's shape detection**, validated against the 58-comment audit set
   plus this week's runs.
4. **Own-product detection** — needs the account's brand terms passed into the
   gate, which is the actual blocker.
5. **Fix the import path** so a list of profile URLs doesn't come back as an
   empty queue.

---

## The artefacts

| File | What it is |
|---|---|
| `Week2_Demo_Walkthrough.webm` | The 2:19 walkthrough. Real UI, real generated comments, real scraped posts. |
| `docs/DEMO_NARRATION.md` | The narration, timed, for reading over the top. |
| `BREAK_LIST.md` | Twelve entries: six fixed, five open, one finding. |
| `scripts/staging_run.py` | The loop, re-runnable, with `--dry-run`. |
| `scripts/staging/voyager_stub.py` | The local stand-in for LinkedIn's API. Not LinkedIn. |
| `src/targeting/discover.py` | The scrape stage. |
| `staging_run/transcript.md` | What the last run actually did, stage by stage. |
| `staging_run/voyager_requests.jsonl` | Every LinkedIn call the run made, credentials redacted. |

277 tests pass, including 8 new ones for the scrape stage and 5 new regression
tests for the defects above.
