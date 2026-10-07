# Handover note

**Date:** 2026-09-17 · **Written by:** Dyuthi T G · **Next review:** whenever I next touch this project for more than a day, or 2026-10-01, whichever comes first.

This is the "if I vanished tomorrow, what would nobody else know" list. The runbook, the voice guide, and the quality doc cover how the product works. This is the stuff that only lives in my head right now — the parts that would cost someone real time to rediscover.

## The things that aren't written down anywhere else

- **There's only one reviewer, and it's me.** No one else has ever cleared the queue. `docs/REVIEW_SLA.md` §2 says this plainly now, but until today it was just true and unwritten.
- **The Sep 15 live dry run never actually happened.** The plan and the log template are ready (`docs/templates/GO_LIVE_DAY_LOG_TEMPLATE.md`), and the infra status was checked once (`Ship_Today_Task_Map.pdf`), but nobody has approved 20 real items on a real account yet, and I don't have Harshil's written sign-off on record. Anyone picking this up needs to know the go-live claim is "ready to run," not "run."
- **`ENCRYPTION_KEY` still isn't set anywhere I can see.** It's a placeholder in `backend/.env.example` and absent from the real `.env`. That's Hemang's line item, not mine, but if someone assumes it's handled because the pilot is close, it isn't.
- **The repo split into `frontend/` and `backend/` on Sep 16 broke a real script, silently.** `backend/scripts/run_golden_set.py` computed its `docs/golden_set/` path relative to its own folder, which was correct when `scripts/` lived at the repo root and broke the moment it moved under `backend/`. I found and fixed this while verifying today's docs (see the `ROOT = REPO.parent` comment in that file) — but it's the kind of break a path move like that will keep causing. Anything that does `Path(__file__).resolve().parent...` and assumes where `docs/` lives is suspect now; I haven't audited every script for the same bug, only the one I happened to run.
- **The project's own `.venv` has a corrupted package.** `pip show` on it prints `WARNING: Ignoring invalid distribution ~penai` — leftover from an interrupted install. `openai` itself is still installed correctly underneath it (verified: a real golden-set run against the real model works), so this hasn't broken anything yet, but it's exactly the kind of thing that causes a confusing failure for whoever hits it next and doesn't know to ignore the warning.
- **Three quality-gate rules are still weaker than what's written down as the standard.** `COMMENT_QUALITY_STANDARD_V2.md` §3 names all three (sentence-count enforcement, emoji threshold, exclamation-mark threshold) — I didn't quietly fix these while writing the doc, because tightening a live gate is Hemang's call, not something to slip in during a documentation pass.
- **The three-year full history is in one memory, not in any file a new person would find.** Every day's brief and what actually shipped against it — Aug 18 through today — is the closest thing to a project diary this has, and it isn't checked into the repo anywhere. If someone asks "why does X work this way," the answer is very often "because of what day N's brief asked for and what broke that day," and that context doesn't exist in code comments.

## What I'd tell someone in their first hour

Read `docs/OPERATOR_RUNBOOK.md` first, not the PRD — it's written for exactly this moment. Then `docs/REVIEW_SLA.md` for who to escalate to. Don't trust a PDF's date as "this is current state" — several of the ones on the desktop describe a specific day's snapshot and have since been overtaken by a later day's work; the docs in `docs/` are the ones I keep updated, the PDFs are dated ship notes.

## What's genuinely fragile right now

The single-reviewer bottleneck and the un-run live dry run are the two things that would actually stop this project cold if I disappeared. Everything else in this list is a real gap, but survivable; those two aren't — nothing ships to more accounts without a second approver and without proof the human-review process holds up on a real account, and neither of those exists yet outside of a plan.
