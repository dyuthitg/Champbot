# Review SLA and escalation path

**Status:** Standing document. **Version:** 1 · **Date:** 2026-09-17 · **Owner:** Dyuthi T G. **Next review:** 2026-10-01, or immediately if the pilot's account count or volume changes (see `Week3_And_Go_Live_Checklist.pdf` §6).

This exists so "how fast should the queue be cleared" and "who covers when I'm away" have one written answer instead of a different guess each time someone asks. `docs/OPERATOR_RUNBOOK.md` is how to clear the queue; this is how fast, and what happens when it doesn't get cleared.

---

## 1. The SLA

| Queue state | Target | Why |
|---|---|---|
| New items sitting with no decision | Cleared within **1 business day** of appearing | Slower than this and the "why did this match" reasoning goes stale in the reviewer's head, which is how rubber-stamping starts. |
| Blocker-flagged item | Not sent, ever, until edited and re-cleared | Not a speed target — a hard gate. `Approve` stays disabled; see `OPERATOR_RUNBOOK.md` §1. |
| Queue depth | Should not exceed **~50 pending items** at any check-in | Past that, the person clearing it is triaging a backlog instead of reviewing fresh matches — a real signal to pause sourcing, not just work faster. |
| Session-validity check | Once per operating day, first thing | Per `OPERATOR_RUNBOOK.md` §3 — an expired session silently stops everything downstream until someone notices. |

**What this SLA does not promise:** same-day sends. Approval on day N can still land on day N+1's pacing window if the account's caps or quiet hours push it there — that's the warm-up and rate-limit system working as designed, not a miss against this SLA.

## 2. Coverage — who clears the queue when I'm away

There is currently **one reviewer: Dyuthi.** No second approver is provisioned today. That's a real gap, not an oversight kept off the page — naming it here is what makes it a plan instead of a hope:

- **Planned covering reviewer:** none yet. This needs a name before the pilot widens past one account (Section 6 of `Week3_And_Go_Live_Checklist.pdf` already requires 100% human review with no exceptions — a gap in coverage is a gap in that rule, not a separate problem).
- **Until a second reviewer exists:** if I'm out for more than one business day, the queue holds — nothing auto-approves, nothing gets waved through by someone unfamiliar with the flag table. A held queue is the safe failure mode; an unreviewed send is not.
- **Action owed before Month 2:** propose a second reviewer and have them shadow one real session (same shape as the Sep 15 dry run) before they're trusted solo. Tracked in the Month 2 proposal (`Sep18_Month1_Review_And_Month2_Proposal.pdf`).

## 3. Escalation path

Same table as `OPERATOR_RUNBOOK.md` §4, restated here with expected response time. One name per row, on purpose.

| Situation | Escalate to | Expected response |
|---|---|---|
| Account banned, restricted, won't validate, warm-up stuck | Dyuthi | Same day — it's the one thing that stops the queue entirely. |
| Infra: Redis down, `ENCRYPTION_KEY` / `/healthz` failing, deploy issue | Hemang or Deep | Same day for a down system; next business day for a config gap that isn't actively blocking sends. |
| A flag or rule seems wrong, or the same warning keeps getting overridden | Dyuthi first (owns the spec and `quality.py`'s rule table); Harshil if it's go/no-go-level | 2 business days — this is a judgment call, not an outage. |
| Queue is confusing or an action's effect isn't clear before taking it | Kethan or Dyuthi | 2 business days — usability gaps compound, so they're worth a real look, not a same-day scramble. |
| Widening the blast radius — more accounts, batches, less than 100% review | Harshil and Deep jointly | Not a response-time item — it's a scheduled go/no-go, currently Sep 18. |

**If you're not sure who owns something:** ask Dyuthi rather than guessing. Routing it to the wrong person costs more time than one extra message — same line as the runbook, because it's the same reason.

## 4. What breaks this SLA in week six

The known way this quietly regresses: attention moves to the next thing, the 1-business-day target slips to "whenever," and nobody notices until the queue depth is the first signal instead of the calendar. The check against that: queue depth (row 2 of §1) gets looked at on the same cadence as the session-validity check, not only when something already feels backed up.
