# Operator runbook

Written for whoever picks up the reviewer seat next — you should be able to
clear the queue today with nothing but this page open. If a question comes up
that this page doesn't answer, that's a gap in the page, not in you; see
[How to report a gap](#how-to-report-a-gap) at the bottom.

This is the day-to-day operating guide. For connecting a new account and the
warm-up stages, see [`CONNECTING_AN_ACCOUNT.md`](CONNECTING_AN_ACCOUNT.md) —
this page assumes an account is already connected and picks up from there.

---

## 1. How to clear the queue

**Approvals** is the whole job. Nothing reaches LinkedIn without going through
this screen — not a queued item, not a scheduled one, not a retry.

1. Open **Approvals**. It defaults to items awaiting a decision, best matches
   first (the strongest fits are shown before the marginal ones, because your
   attention is the limited resource, not screen space).
2. Each card shows: who the person is, why they matched, the drafted text,
   and any quality flags (see §2). Read the post or profile it's responding
   to, not just the draft — a flag-free draft can still be wrong for reasons
   the gate can't see (see §2, "what the flags can't catch").
3. Pick one of four actions, bottom-right of the card:

   | Button | What it does | Reversible? |
   |---|---|---|
   | **Approve & schedule** | Sends the draft as-is, on the account's normal pacing (business hours, cooldowns, randomised gaps). | No — it will go out. |
   | **Edit**, then **Approve edit & schedule** | Your edited text is re-run through the same quality gate the original draft went through before it's scheduled — editing never bypasses the rules. | No, once approved. |
   | **Skip** | Leaves this person alone for now. Nothing is recorded against them; they can be suggested again later. | Yes — no lasting effect. |
   | **Never contact** | Two-tap, on purpose: click once, confirm once. Suppresses this person permanently — the system will never suggest or draft for them again. | **No.** This is the one irreversible non-send action on the screen. |

4. An item with a **blocker** flag (red, §2) cannot be approved until it's
   edited to clear the blocker — the Approve button stays disabled. A
   **warning** or **advisory** flag can still be approved; it's shown so you
   can make the call, not to stop you.
5. Filter the queue by failure type (top of screen) to work through one kind
   of issue at a time instead of context-switching between them — useful when
   you're clearing a backlog rather than reviewing a fresh batch.
6. If the queue is empty, the screen tells you why: **"Nothing generated
   yet"** (nothing has run on this account) reads differently from **"You're
   caught up"** (plenty has run and all of it is decided). If you expected
   items and see either message, check the account's status on **Accounts**
   before assuming the queue is broken.

### What happens after you approve

Approving schedules the item; it does not send it immediately. At send time
the system re-checks the quality gate, the account's warm-up permissions, and
the rate limiter one more time — an approval from an hour ago can still be
declined at send time if, say, the daily cap filled up from other activity in
between. That's expected, not a bug: approval means "a human wants this to go
out," not "guaranteed delivery regardless of what else happened since."

---

## 2. What each flag means

Every flag comes from one shared rule table (`backend/src/outreach/quality.py`), so a
flag is named the same thing in the queue, in the filter, and in any report
built from it. Three severities:

- **Blocker** (red) — cannot be approved or sent until rewritten. Always
  something that's *always* wrong (an empty draft, a leaked placeholder, a
  booking link).
- **Warning** (amber) — deducts from the 0–100 quality score shown on the
  card. Usually wrong; your call whether this instance is fine.
- **Advisory** (grey) — shown for awareness only. Never blocks, never
  changes the score. Mostly gaps the spec names but the shared gate doesn't
  enforce yet (see the note at the end of this section).

| Code | Label | Severity | What it caught |
|---|---|---|---|
| `EMPTY` | No draft | blocker | Nothing was generated. |
| `R8.1` | Placeholder left in | blocker | An unfilled `{{merge field}}` or similar made it into the text. |
| `R8.2` | Link | blocker (connect/booking link) or warning (link in a message) | A URL, or a scheduling link outside the one step that's allowed to have one. |
| `R2` | Too long | blocker if over the hard limit; advisory if only over the comment's softer target | Over the character cap for this action (comment 400 / connect note 300 / message 900). |
| `CTA` | Asks for time up front | blocker in a connection note, warning elsewhere | "book a call," "15 minutes of your time," and similar asks in a first touch. |
| `TEMPLATE3` | Formulaic 3-beat template | blocker | The full validate → restate → "have you found any strategies" shape — the pattern the first live audit named as the bot's most recognisable tell. |
| `R4` | Generic phrase | warning | A worn-out outreach phrase ("just checking in," "hope this finds you well," and the audit-sourced additions like "spot on," "you nailed it"). |
| `R3` | No specific reference | warning | Nothing in the draft ties it to *this* person — no name, company, title, or detail from their post. Could have been sent to anyone. |
| `OPENER` | Generic opener | warning | Opens with "hi there" / "hey there" and no other sign the profile was read. |
| `SELF` | All about us | warning | Talks about the sender, not the recipient — "I/we" heavily outweighs "you." |
| `CAPS` | Shouting in caps | warning | A word in all caps that isn't a known acronym (see the allow-list in `quality.py` if a legitimate one gets flagged — add it there, that's a code change). |
| `LEN_SOFT` | Longer than ideal | warning | Under the hard cap but long enough to read poorly (messages only). |
| `THIN` | Too thin | warning | Under 8 words — probably not worth sending. |
| `R7` | Too many exclamations | warning (2+) / advisory (a lone second one) | Reads as hype. |
| `R6` | Emoji | warning (3+) / advisory (1–2) | More emoji than professional outreach should have. |
| `R1` | Too many sentences | advisory | Over 3 sentences (comments only — the spec's rule, shown but not yet enforced). |
| `R5` | Formula question | advisory | Ends on "have you found any specific strategies…" without the validation opener that would make it `TEMPLATE3`. |
| `DUP` | Near-identical to others | warning | Reads like other drafts currently in the queue — computed across the whole pending queue, not just the page you're looking at. Shows who else it resembles. |

**What the flags can't catch:** nothing here understands *whether a post
should get a comment at all* — a bereavement post, a layoff announcement, a
sensitive personal update. That judgment is entirely on you; a completely
flag-free draft on the wrong post is still the wrong call. See
`docs/golden_set/RUBRIC.md`'s "should this post have gotten a comment at all"
framing for how this is scored in testing.

**On the advisory-only rules (`R1`, `R5`, `R6`'s 1–2 case, `R7`'s 1-extra
case):** these exist because the written spec (`COMMENT_QUALITY_SPEC_V1.md`)
and the enforced gate haven't been reconciled yet — that gap is documented in
`COMMENT_RULES_ENFORCEMENT_GAP.md`. If you're seeing a pattern of advisory
flags you think should block, that's a real signal; escalate it (§4) rather
than treating it as noise.

---

## 3. When a session expires

The account's login is a browser cookie, not a password — it can stop
working with no warning: a LinkedIn security check, a sign-out elsewhere, or
just time. Nothing watches for this on its own; you have to notice.

| Symptom | What it means | Do this |
|---|---|---|
| Account badge / Accounts screen shows `auth_required` | LinkedIn rejected or expired the session cookie | Get a fresh `li_at` cookie from a real browser sign-in, then run `python backend/scripts/validate_account.py --account-id <id> --rotate` and confirm all four preflight checks (whoami, profile, inbox, activity) come back green before trusting the account again. Don't just retry with the old cookie. |
| Account shows `rate_limited` | LinkedIn challenged the account (a checkpoint) | Sign in via a real browser, clear the checkpoint by hand, leave invitations off for ~48 hours, then re-verify with `validate_account.py`. |
| `Approve` or `Send` returns a `503` | Redis is down, so caps can't be enforced | Check `/healthz`. Sending fails closed on purpose — this is not a bug to route around; escalate to infra (§4) rather than setting `ALLOW_UNCAPPED_SENDING`. |
| A held item's error says `"account challenged"` | The live send itself got a LinkedIn security challenge mid-attempt | Same as `rate_limited` above — treat the account as needing a manual check before anything else sends. |

Check the account's session validity at the start of every day you're
operating it — this is a checklist line item during the pilot (see
`Week3_And_Go_Live_Checklist.pdf`, Section 4), not an assumption you get to
skip because it worked yesterday.

**Note on the command name:** some earlier planning docs refer to
`--replace`; the actual flag implemented in `validate_account.py` is
`--rotate`. Use `--rotate` — this runbook is the source of truth for the
literal command.

---

## 4. Who to escalate to

One name per row, on purpose — "the team" can't tell you it's fixed, a person
can.

| Situation | Escalate to |
|---|---|
| The account itself — banned, restricted, won't validate, warm-up looks stuck | Dyuthi |
| Infra: Redis down, `ENCRYPTION_KEY` / `/healthz` failures, deploy issues | Hemang or Deep |
| A flag or rule seems wrong, or you're overriding the same warning repeatedly and think the rule should change | Dyuthi first (owns `quality.py` and the spec); if it's a go/no-go-level judgment call, Harshil |
| The queue itself is confusing, slow, or you can't tell what an action will do before you take it | Kethan (the standing "never built this, does it make sense" check) or Dyuthi |
| Whether to widen the blast radius — more accounts, batches, less than 100% review | Harshil and Deep jointly — this is a go/no-go decision, not a unilateral one |

If you're not sure who owns something, ask Dyuthi rather than guessing —
routing it wrong costs more time than one extra message.

---

## How to report a gap

The way this runbook gets better is someone hitting a wall it didn't cover.
If you had to stop, guess, or ask someone something this page should have
answered: say so, specifically — what screen, what you expected, what
happened instead. That's not a complaint, it's the only way a page like this
stops being stale six weeks from now.
