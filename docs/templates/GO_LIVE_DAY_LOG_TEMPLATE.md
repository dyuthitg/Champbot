# Go-live day log — {{DATE}}

**Account:** {{ACCOUNT NAME / ID — the one disposable account, not anyone's real profile}}
**Operator (approving live):** {{NAME}}
**Blast-radius plan referenced:** Week3_And_Go_Live_Checklist.pdf, Section 6

---

## 0. Written agreement on record

Before the first real send, paste or link the actual written yes here — a reply,
an email, a message — not a memory of a conversation.

- **Account confirmed by:** {{NAME}}, {{DATE}}, {{LINK OR QUOTE}}
- **Blast-radius limits confirmed by:** {{NAME}}, {{DATE}}, {{LINK OR QUOTE}}
  (one account, one send at a time, 100% human review, scheduler off, caps/quiet
  hours/warm-up at normal settings — per Section 6)

If either line above is blank, nothing below should have happened yet.

---

## 1. Preflight

- [ ] `validate_account.py` run against this account — whoami / profile / inbox / activity all green
- [ ] `/healthz` reports `credentials_encryption: ok`
- [ ] `/healthz` reports `redis: ok`
- [ ] Account enrolled in warm-up at stage zero (no stage skipped)

## 2. The twenty (or more) real items

One row per item. Fill it in live, in order, as it happens — not reconstructed afterward.

| # | Target / post | Drafted comment (or link to it) | Decision | Hesitation? (see §3) | Notes |
|---|---|---|---|---|---|
| 1 | | | approve / edit / reject | y/n | |
| 2 | | | | | |
| 3 | | | | | |
| … | | | | | |
| 20 | | | | | |

**Running total approved and actually sent:** {{N}} / 20

## 3. Hesitation log

Every place you paused to think, not just every place something broke. If you
had to stop and figure out what to do, that pause is the finding — write it
down before you forget it, not at the end of the day from memory.

| Item # | What made you pause | How long (rough) | What would remove the pause |
|---|---|---|---|
| | | | |

## 4. Issue list

Same shape as `BREAK_LIST.md` — one entry per thing that broke, was missing, or
was wrong, found live on this account. Severity + evidence, not vibes.

### Entry N — {{short name}}
**Severity:** blocker / high / medium / low
**What happened:** {{evidence — item #, exact text, screenshot, log line}}
**Fixed today?** yes (link the fix) / no (recommendation)

---

## 5. Dry-run vs. live — what actually differed

One paragraph: what showed up on the real account that never showed up in
staging or synthetic runs. This is the actual point of today — twenty real
items teaching more than two hundred staging ones.

## 6. Go/no-go input

- **Zero embarrassing comments?** yes / no — if no, name the item number and quote it.
- **Everything in §2 was human-approved, no exceptions?** yes / no
- **Recommendation for the Sep 18 go/no-go:** {{one paragraph, plain}}
- **Signed off by:** {{NAME}}, {{DATE}}
