"""
End-to-end tests for the outreach loop:

    connect account -> import targets -> generate suggestions
    -> human approves -> paced send under global caps

These are the tests that answer "does the vertical slice actually work", and
equally importantly "does it refuse to work when it should".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.accounts import caps as caps_policy
from src.outreach import execute as executor
from src.outreach import suggest as engine
from src.outreach.models import SuggestionAction, SuggestionStatus
from src.targeting.models import TargetStatus
from src.targeting.schemas import TargetImportItem
from src.targeting.service import import_targets



GOOD_FIT = TargetImportItem(
    profile_url="https://www.linkedin.com/in/dana-whitfield",
    full_name="Dana Whitfield",
    title="Head of Growth",
    company="Northwind",
    industry="SaaS",
    headline="Head of Growth at Northwind | B2B activation",
    location="London",
)
POOR_FIT = TargetImportItem(
    profile_url="https://www.linkedin.com/in/sam-taylor",
    full_name="Sam Taylor",
    title="Warehouse Supervisor",
    company="Logistix",
    industry="Logistics",
    headline="Warehouse Supervisor at Logistix",
)
EXCLUDED = TargetImportItem(
    profile_url="https://www.linkedin.com/in/alex-reed",
    full_name="Alex Reed",
    title="Head of Growth",
    company="TalentCo",
    industry="SaaS",
    headline="Head of Growth at TalentCo | technical recruiter",
)


async def _import(db, org, account, icp, items):
    organization, _ = org
    created, duplicates = await import_targets(
        db,
        org_id=str(organization.id),
        account_id=str(account.id),
        items=items,
        icp=icp,
    )
    return created, duplicates


# ----------------------------------------------------------------------
# Account connection
# ----------------------------------------------------------------------


async def test_connecting_an_account_verifies_it_against_linkedin(account, transport):
    assert account.status == "active"
    assert account.display_name == "Test User"
    assert account.linkedin_member_urn == "urn:li:fs_profile:ACoAAATEST"
    assert ("whoami",) in transport.calls


async def test_credentials_are_encrypted_at_rest(account):
    """The raw cookie must never be recoverable from the stored column."""
    assert "a" * 40 not in (account.auth_blob or "")
    from src.accounts.crypto import decrypt_auth

    assert "a" * 40 in decrypt_auth(account.auth_blob)


async def test_account_response_never_leaks_credentials(account):
    from src.accounts.service import to_response

    payload = to_response(account).model_dump()
    serialized = str(payload)
    assert "a" * 40 not in serialized
    assert "auth_blob" not in payload
    assert payload["has_credentials"] is True


async def test_a_rejected_cookie_marks_the_account_auth_required(db, org):
    from src.accounts.schemas import AccountConnect
    from src.accounts.service import connect_account
    from tests.conftest import RecordingTransport

    organization, user = org
    broken = RecordingTransport(fail_with="session rejected")
    record = await connect_account(
        db,
        org_id=str(organization.id),
        user_id=str(user.id),
        payload=AccountConnect(li_at="b" * 40, jsessionid="ajax:1"),
        transport=broken,
    )
    assert record.status == "auth_required"


# ----------------------------------------------------------------------
# Account health / run status: what someone checks at 9am to know the bot
# is alive.
# ----------------------------------------------------------------------


async def test_dashboard_shows_when_a_session_expired_and_why(db, org, account):
    """
    Break something on purpose: an expired session must be visible with a
    timestamp, not just a status word -- that's the difference between "check
    the dashboard" and "go read logs".
    """
    from types import SimpleNamespace

    from src.accounts.service import check_health
    from src.api.routes.outreach import dashboard
    from tests.conftest import RecordingTransport

    organization, _ = org

    before = await dashboard(_fake_request(), ctx=_fake_ctx(organization), db=db)
    row = before.accounts[0]
    assert row.status == "active"
    connected_since = row.status_since
    assert connected_since is not None  # connecting is itself a status change

    broken = RecordingTransport(fail_with="session no longer valid")
    result = await check_health(db, account, transport=broken)
    assert result["ok"] is False
    assert account.status == "auth_required"

    after = await dashboard(_fake_request(), ctx=_fake_ctx(organization), db=db)
    row = after.accounts[0]
    assert row.status == "auth_required"
    # The stamp moves with the transition -- this is what lets the UI say
    # "expired 2 hours ago" instead of "recently, we think".
    assert row.status_since is not None
    assert row.status_since > connected_since


async def test_dashboard_shows_the_last_run_and_its_error(db, org, account):
    """
    A scheduler sweep's outcome must survive on the account, not just in a log
    line -- otherwise a dead scheduler and a quiet one look identical here too.
    """
    from src.accounts.service import record_run_outcome
    from src.api.routes.outreach import dashboard

    organization, _ = org

    await record_run_outcome(db, account, errors={"sync": "TransportError: timed out"})

    result = await dashboard(_fake_request(), ctx=_fake_ctx(organization), db=db)
    row = result.accounts[0]
    assert row.last_run_at is not None
    assert row.last_run_ok is False
    assert row.last_error == "sync: TransportError: timed out"
    assert row.last_error_at is not None

    await record_run_outcome(db, account, errors=None)
    result = await dashboard(_fake_request(), ctx=_fake_ctx(organization), db=db)
    row = result.accounts[0]
    assert row.last_run_ok is True
    # A resolved run doesn't erase the record of what broke earlier.
    assert row.last_error == "sync: TransportError: timed out"


async def test_dashboard_does_not_report_a_failed_cap_read_as_healthy(db, org, account):
    """
    A Redis read that raises must not render as "0 used" -- that's
    indistinguishable from a genuinely healthy, quiet account, which is
    exactly the failure this view exists to make loud instead of silent.
    """
    from types import SimpleNamespace

    from src.api.routes.outreach import dashboard

    organization, _ = org

    class _BrokenRedis:
        def pipeline(self):
            raise RuntimeError("redis unavailable")

    broken_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=_BrokenRedis()))
    )

    result = await dashboard(broken_request, ctx=_fake_ctx(organization), db=db)
    row = result.accounts[0]
    assert row.caps_today["connect"]["tracked"] is False
    assert row.caps_today["connect"]["used"] == 0


def _fake_request():
    from types import SimpleNamespace

    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(redis=None)))


def _fake_ctx(organization):
    from types import SimpleNamespace

    return SimpleNamespace(org_id=str(organization.id))


# ----------------------------------------------------------------------
# Targeting
# ----------------------------------------------------------------------


async def test_import_scores_targets_and_skips_duplicates(db, org, warm_account, icp):
    created, duplicates = await _import(db, org, warm_account, icp, [GOOD_FIT, POOR_FIT])
    assert len(created) == 2
    assert duplicates == 0

    # Re-importing the same people must not create a second round of outreach.
    _, duplicates = await _import(db, org, warm_account, icp, [GOOD_FIT])
    assert duplicates == 1

    by_name = {t.full_name: t for t in created}
    assert by_name["Dana Whitfield"].relevance_score >= 60
    assert by_name["Sam Taylor"].relevance_score < 60


async def test_excluded_targets_are_marked_skipped_on_import(db, org, warm_account, icp):
    created, _ = await _import(db, org, warm_account, icp, [EXCLUDED])
    assert created[0].status == TargetStatus.SKIPPED


# ----------------------------------------------------------------------
# Suggestion generation
# ----------------------------------------------------------------------


async def test_only_good_fit_targets_become_suggestions(db, org, warm_account, icp):
    await _import(db, org, warm_account, icp, [GOOD_FIT, POOR_FIT, EXCLUDED])

    result = await engine.generate_suggestions(db, warm_account, icp)

    assert len(result["created"]) == 1
    suggestion = result["created"][0]
    assert suggestion.action == SuggestionAction.CONNECT
    assert suggestion.status == SuggestionStatus.PENDING
    assert result["considered"] == 3
    assert result["skipped"]["below_relevance_floor"] == 1
    assert result["skipped"]["excluded_by_icp"] == 1


async def test_generated_copy_passes_the_quality_gate(db, org, warm_account, icp):
    """With no OpenRouter key configured this exercises the template fallback,
    which must still produce copy good enough to send."""
    await _import(db, org, warm_account, icp, [GOOD_FIT])
    result = await engine.generate_suggestions(db, warm_account, icp)

    suggestion = result["created"][0]
    assert suggestion.status == SuggestionStatus.PENDING
    assert suggestion.quality_score >= 70
    assert "Dana" in suggestion.draft_text
    assert len(suggestion.draft_text) <= 300
    assert suggestion.rationale


async def test_suggestions_explain_why_this_person(db, org, warm_account, icp):
    await _import(db, org, warm_account, icp, [GOOD_FIT])
    result = await engine.generate_suggestions(db, warm_account, icp)

    suggestion = result["created"][0]
    assert suggestion.relevance_reasons
    assert any("Title matches" in r for r in suggestion.relevance_reasons)


async def test_the_source_post_is_returned_with_the_suggestion(db, org, warm_account, icp):
    """
    Regression test for the 2026-09-01 gap: an operator can't judge a
    comment without seeing what it replies to, and the API used to drop
    the source post on the floor -- TargetSummary simply had no field for
    it, even though it's stored right there on the target.
    """
    from src.api.routes.outreach import _serialize

    created, _ = await _import(db, org, warm_account, icp, [GOOD_FIT])
    created[0].context = {
        "post_urn": "urn:li:activity:900001",
        "post_text": "We rebuilt onboarding around one metric.",
    }
    await db.commit()

    result = await engine.generate_suggestions(db, warm_account, icp)
    suggestion = result["created"][0]

    response = await _serialize(db, suggestion)
    assert response.target.post_text == "We rebuilt onboarding around one metric."
    assert response.target.post_urn == "urn:li:activity:900001"


async def test_the_same_person_is_never_suggested_twice(db, org, warm_account, icp):
    await _import(db, org, warm_account, icp, [GOOD_FIT])

    first = await engine.generate_suggestions(db, warm_account, icp)
    second = await engine.generate_suggestions(db, warm_account, icp)

    assert len(first["created"]) == 1
    assert len(second["created"]) == 0
    assert second["skipped"]["already_suggested"] == 1


async def test_daily_suggestion_budget_caps_the_review_queue(db, org, warm_account, icp):
    """Approval fatigue is a real failure mode: the queue stays reviewable."""
    warm_account.daily_caps = {**(warm_account.daily_caps or {}), "suggestion_budget": 2}
    await db.commit()

    many = [
        TargetImportItem(
            profile_url=f"https://www.linkedin.com/in/person-{i}",
            full_name=f"Person{i} Example",
            title="Head of Growth",
            company=f"Company{i}",
            industry="SaaS",
            headline="Head of Growth | B2B activation",
        )
        for i in range(6)
    ]
    await _import(db, org, warm_account, icp, many)

    result = await engine.generate_suggestions(db, warm_account, icp)
    assert len(result["created"]) == 2
    assert result["skipped"]["daily_suggestion_budget"] >= 1


async def test_no_icp_means_no_suggestions(db, org, account):
    """Without a definition of the right person, we target nobody."""
    result = await engine.generate_suggestions(db, account, None)
    assert result["created"] == []
    assert "No ICP" in result["message"]


async def test_an_account_that_can_comment_but_not_connect_still_gets_suggestions(
    db, org, account, icp
):
    """
    Regression test for the Aug 26 2026 UI audit finding: an account in the
    "converse" (Commenting) warm-up stage can comment but not yet connect or
    message. The gate used to check only connect/message, so this account got
    zero suggestions and a message blaming 'connect' -- an action nobody was
    trying to use -- even with comment-eligible targets waiting.
    """
    from src.warmup import planner, program

    planner.set_stage(account, "converse")
    await db.commit()
    await db.refresh(account)

    created, _ = await _import(db, org, account, icp, [GOOD_FIT])
    created[0].context = {
        "post_urn": "urn:li:activity:1",
        "post_text": "We rebuilt onboarding around one metric.",
    }
    await db.commit()

    result = await engine.generate_suggestions(db, account, icp)

    assert len(result["created"]) == 1
    assert result["created"][0].action == SuggestionAction.COMMENT
    assert "connect" not in (result.get("message") or "")


async def test_capacity_is_read_from_the_live_rate_limiter(
    db, org, warm_account, icp, rate_limiter
):
    """Invitations already sent today reduce how many we suggest."""
    caps = caps_policy.caps_for(warm_account, "connect")
    for _ in range(caps.per_day):
        await rate_limiter.check_and_consume(
            str(warm_account.id), "connect", per_hour=999, per_day=999, cooldown_seconds=0
        )

    await _import(db, org, warm_account, icp, [GOOD_FIT])
    result = await engine.generate_suggestions(db, warm_account, icp, rate_limiter=rate_limiter)

    assert result["created"] == []
    assert result["skipped"]["no_connect_capacity_today"] == 1


# ----------------------------------------------------------------------
# Approval
# ----------------------------------------------------------------------


async def _one_suggestion(db, org, warm_account, icp, item=GOOD_FIT):
    await _import(db, org, warm_account, icp, [item])
    result = await engine.generate_suggestions(db, warm_account, icp)
    return result["created"][0]


async def test_approving_schedules_the_send_with_pacing(db, org, warm_account, icp):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    approved = await executor.approve(db, suggestion, account=warm_account)

    assert approved.status == SuggestionStatus.SCHEDULED
    assert approved.scheduled_for is not None
    assert approved.final_text == approved.draft_text
    assert approved.reviewed_at is not None


async def test_a_user_edit_is_re_checked_by_the_quality_gate(db, org, warm_account, icp):
    """Human approval supplies intent, not an exemption from the safety rules."""
    suggestion = await _one_suggestion(db, org, warm_account, icp)

    with pytest.raises(executor.ExecutionBlocked) as exc:
        await executor.approve(
            db,
            suggestion,
            account=warm_account,
            edited_text="Hi Dana, book a call with me here: calendly.com/me",
        )
    assert "booking link" in str(exc.value).lower()
    assert suggestion.status == SuggestionStatus.BLOCKED


async def test_a_good_edit_is_accepted(db, org, warm_account, icp):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    approved = await executor.approve(
        db,
        suggestion,
        account=warm_account,
        edited_text=(
            "Hi Dana — the activation work you're doing at Northwind is exactly "
            "the problem I spend my time on. Would be glad to connect."
        ),
    )
    assert approved.status == SuggestionStatus.SCHEDULED
    assert "activation work" in approved.final_text


async def test_rejecting_with_suppression_blocks_all_future_contact(
    db, org, warm_account, icp
):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.reject(
        db, suggestion, account=warm_account, suppress_target=True, reason="not a fit"
    )

    assert suggestion.status == SuggestionStatus.REJECTED

    # The person is now out of reach of every future generation run.
    again = await engine.generate_suggestions(db, warm_account, icp)
    assert again["created"] == []


async def test_reject_reason_is_required_by_the_schema():
    """
    The 2026-09-02 brief: the reject reason is not optional, it is the data
    that improves the prompt later. Enforced at the request boundary so no
    caller -- not just the review screen -- can skip it.
    """
    from pydantic import ValidationError

    from src.outreach.schemas import RejectRequest

    with pytest.raises(ValidationError):
        RejectRequest(suppress_target=False, reason="")

    with pytest.raises(ValidationError):
        RejectRequest(suppress_target=False, reason="   ")

    with pytest.raises(ValidationError):
        RejectRequest(suppress_target=False)

    ok = RejectRequest(suppress_target=False, reason="too generic")
    assert ok.reason == "too generic"


async def test_approve_writes_one_ledger_entry_and_a_second_approve_is_refused(
    db, org, warm_account, icp
):
    """
    2026-09-02 ship criteria: run the flow twice on the same item. It must
    not double-post or duplicate an audit entry.
    """
    from sqlalchemy import select

    from src.warmup.models import AccountActivity

    _, user = org
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account, reviewer_id=str(user.id))

    rows = (
        await db.execute(
            select(AccountActivity).where(
                AccountActivity.action == "approve",
                AccountActivity.target_id == suggestion.target_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].detail["suggestion_id"] == str(suggestion.id)
    assert rows[0].detail["reviewer_id"] == str(user.id)

    # Running it again on the same, now-scheduled item must not double-post
    # or write a second ledger entry.
    with pytest.raises(executor.ExecutionBlocked):
        await executor.approve(db, suggestion, account=warm_account)

    rows_after = (
        await db.execute(
            select(AccountActivity).where(
                AccountActivity.action == "approve",
                AccountActivity.target_id == suggestion.target_id,
            )
        )
    ).scalars().all()
    assert len(rows_after) == 1


async def test_reject_writes_the_reason_to_the_ledger_and_a_second_reject_is_refused(
    db, org, warm_account, icp
):
    from sqlalchemy import select

    from src.warmup.models import AccountActivity

    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.reject(
        db, suggestion, account=warm_account, reason="comment reads generic"
    )

    rows = (
        await db.execute(
            select(AccountActivity).where(
                AccountActivity.action == "reject",
                AccountActivity.target_id == suggestion.target_id,
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].detail["reason"] == "comment reads generic"

    with pytest.raises(executor.ExecutionBlocked):
        await executor.reject(db, suggestion, account=warm_account, reason="again")

    rows_after = (
        await db.execute(
            select(AccountActivity).where(
                AccountActivity.action == "reject",
                AccountActivity.target_id == suggestion.target_id,
            )
        )
    ).scalars().all()
    assert len(rows_after) == 1


# ----------------------------------------------------------------------
# Execution
# ----------------------------------------------------------------------


async def test_approved_suggestion_sends_via_the_transport(
    db, org, warm_account, icp, transport, rate_limiter
):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)

    sent = await executor.execute_suggestion(
        db,
        suggestion,
        transport=transport,
        rate_limiter=rate_limiter,
        account=warm_account,
        force=True,
    )

    assert sent.status == SuggestionStatus.SENT
    assert sent.sent_at is not None
    action, member_urn, note = transport.calls[-1]
    assert action == "connect"
    assert member_urn == "dana-whitfield"
    assert "Dana" in note


async def test_sending_consumes_the_global_cap(
    db, org, warm_account, icp, transport, rate_limiter
):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)
    await executor.execute_suggestion(
        db, suggestion, transport=transport, rate_limiter=rate_limiter,
        account=warm_account, force=True,
    )

    usage = await rate_limiter.usage(str(warm_account.id), "connect")
    assert usage["day_used"] == 1


async def test_the_daily_cap_is_enforced_at_send_time(
    db, org, warm_account, icp, transport, rate_limiter
):
    """Even an approved action is refused once the account is out of allowance."""
    caps = caps_policy.caps_for(warm_account, "connect")
    for _ in range(caps.per_day):
        await rate_limiter.check_and_consume(
            str(warm_account.id), "connect", per_hour=999, per_day=caps.per_day,
            cooldown_seconds=0,
        )

    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)

    with pytest.raises(executor.ExecutionBlocked) as exc:
        await executor.execute_suggestion(
            db, suggestion, transport=transport, rate_limiter=rate_limiter,
            account=warm_account, force=True,
        )

    assert "rate limited" in str(exc.value)
    assert transport.calls[-1][0] == "whoami"  # nothing new was sent
    assert suggestion.status != SuggestionStatus.SENT


async def test_an_unapproved_suggestion_can_never_be_sent(
    db, org, warm_account, icp, transport, rate_limiter
):
    """The core safety property: no approval, no send."""
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    assert suggestion.status == SuggestionStatus.PENDING

    with pytest.raises(executor.ExecutionBlocked) as exc:
        await executor.execute_suggestion(
            db, suggestion, transport=transport, rate_limiter=rate_limiter,
            account=warm_account, force=True,
        )
    assert "not approved" in str(exc.value)


async def test_outside_active_hours_the_send_is_rescheduled_not_dropped(
    db, org, warm_account, icp, transport, rate_limiter
):
    # A window that cannot contain "now".
    now_hour = datetime.now(timezone.utc).hour
    closed = ((now_hour + 2) % 24, (now_hour + 3) % 24)
    warm_account.daily_caps = {**(warm_account.daily_caps or {}), "active_hours": list(closed)}
    await db.commit()

    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)

    with pytest.raises(executor.ExecutionBlocked) as exc:
        await executor.execute_suggestion(
            db, suggestion, transport=transport, rate_limiter=rate_limiter,
            account=warm_account, force=True,
        )

    assert "active hours" in str(exc.value)
    assert suggestion.scheduled_for is not None
    assert suggestion.status != SuggestionStatus.FAILED


async def test_a_challenge_pauses_the_account(db, org, warm_account, icp, rate_limiter):
    """A verification wall must stop the account, not retry into a restriction."""
    from src.infrastructure.transports.base import TransportChallenge
    from tests.conftest import RecordingTransport

    challenged = RecordingTransport(raise_with=TransportChallenge("checkpoint"))

    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)

    with pytest.raises(executor.ExecutionBlocked):
        await executor.execute_suggestion(
            db, suggestion, transport=challenged, rate_limiter=rate_limiter,
            account=warm_account, force=True,
        )

    assert warm_account.status == "rate_limited"
    assert suggestion.status == SuggestionStatus.FAILED


async def test_run_due_only_sends_what_is_actually_due(
    db, org, warm_account, icp, transport, rate_limiter
):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(
        db,
        suggestion,
        account=warm_account,
        send_at=datetime.now(timezone.utc) + timedelta(hours=6),
    )

    result = await executor.run_due(
        db, warm_account, transport=transport, rate_limiter=rate_limiter
    )
    assert result["sent"] == []

    # Once it is due, it goes.
    suggestion.scheduled_for = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db.commit()

    result = await executor.run_due(
        db, warm_account, transport=transport, rate_limiter=rate_limiter
    )
    assert result["sent"] == [str(suggestion.id)]


async def test_a_sent_connection_marks_the_target_contacted(
    db, org, warm_account, icp, transport, rate_limiter
):
    suggestion = await _one_suggestion(db, org, warm_account, icp)
    await executor.approve(db, suggestion, account=warm_account)
    await executor.execute_suggestion(
        db, suggestion, transport=transport, rate_limiter=rate_limiter,
        account=warm_account, force=True,
    )

    from sqlalchemy import select

    from src.targeting.models import OutreachTarget

    target = (
        await db.execute(
            select(OutreachTarget).where(OutreachTarget.id == suggestion.target_id)
        )
    ).scalar_one()
    assert target.status == TargetStatus.CONTACTED
    assert target.last_touched_at is not None
