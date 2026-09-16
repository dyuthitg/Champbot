"""
Sequence and reply-detection tests.

The property under test throughout: **a reply stops the sequence**. An
automated follow-up landing after someone has already answered is the clearest
possible tell that they were talking to software, and it costs the meeting the
sequence existed to book.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.outreach import sequences
from src.outreach.models import SuggestionStatus
from src.outreach.quality import check_copy
from src.targeting.models import TargetStatus



def target(status=TargetStatus.SCORED, last_touched=None, **kw):
    base = dict(
        id="t-1",
        status=status,
        last_touched_at=last_touched,
        first_name="Dana",
        full_name="Dana Whitfield",
        company="Northwind",
        title="Head of Growth",
        headline="Head of Growth at Northwind",
        context={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------
# Sequence progression
# ----------------------------------------------------------------------


def test_a_new_target_starts_with_an_invitation():
    step = sequences.advance(target(), completed=set())
    assert step
    assert step.step.key == "invite"
    assert step.step.action == "connect"


def test_no_follow_up_until_the_invitation_is_accepted():
    """A contacted-but-not-accepted person gets nothing further."""
    result = sequences.advance(target(status=TargetStatus.CONTACTED), completed={"invite"})
    assert not result


def test_accepted_target_gets_a_welcome_after_a_delay():
    """Messaging the instant an invite is accepted is an obvious tell."""
    just_accepted = datetime.now(timezone.utc)
    result = sequences.advance(
        target(status=TargetStatus.CONNECTED, last_touched=just_accepted),
        completed={"invite"},
    )
    assert result.step.key == "welcome"
    assert result.blocked_reason == "waiting"
    assert result.due_at > just_accepted


def test_welcome_becomes_due_once_the_wait_has_passed():
    accepted = datetime.now(timezone.utc) - timedelta(days=3)
    result = sequences.advance(
        target(status=TargetStatus.CONNECTED, last_touched=accepted),
        completed={"invite"},
    )
    assert result.step.key == "welcome"
    assert result.blocked_reason == ""


def test_a_reply_stops_the_sequence_dead():
    """The headline guarantee of this module."""
    result = sequences.advance(
        target(status=TargetStatus.REPLIED, last_touched=datetime.now(timezone.utc)),
        completed={"invite", "welcome"},
    )
    assert not result
    assert "replied" in result.blocked_reason.lower()


def test_every_downstream_status_also_stops_automation():
    for status in (
        TargetStatus.REPLIED,
        TargetStatus.INTERESTED,
        TargetStatus.BOOKED,
        TargetStatus.NOT_INTERESTED,
        TargetStatus.SUPPRESSED,
    ):
        result = sequences.advance(target(status=status), completed={"invite"})
        assert not result, status


def test_the_automated_sequence_ends_rather_than_nagging_forever():
    old = datetime.now(timezone.utc) - timedelta(days=90)
    result = sequences.advance(
        target(status=TargetStatus.CONNECTED, last_touched=old),
        completed={"invite", "welcome", "value", "ask"},
    )
    assert not result
    assert "complete" in result.blocked_reason.lower()


def test_qualification_steps_are_offered_only_when_asked_for():
    replied = target(status=TargetStatus.REPLIED)

    assert not sequences.advance(replied, completed={"invite", "welcome"})

    manual = sequences.advance(
        replied, completed={"invite", "welcome"}, include_manual=True
    )
    assert manual.step.key == "qualify"
    assert manual.step.manual_only


def test_booking_step_requires_an_interested_prospect():
    interested = target(status=TargetStatus.INTERESTED)
    result = sequences.advance(
        interested, completed={"invite", "welcome", "qualify"}, include_manual=True
    )
    assert result.step.key == "book"
    assert result.step.allow_scheduler_link


# ----------------------------------------------------------------------
# Scheduler links: blocked early, allowed once earned
# ----------------------------------------------------------------------


def test_scheduler_link_is_blocked_in_every_automated_step():
    for step in sequences.AUTOMATED_STEPS:
        assert not sequences.allows_scheduler_link(step.key), step.key


def test_scheduler_link_is_allowed_only_at_the_booking_step():
    assert sequences.allows_scheduler_link("book")
    assert not sequences.allows_scheduler_link("welcome")
    assert not sequences.allows_scheduler_link(None)


def test_quality_gate_blocks_a_calendar_link_by_default():
    report = check_copy(
        "Hi Dana, grab a time with me at calendly.com/me/30min to discuss Northwind.",
        "message",
        target(),
    )
    assert not report.passed
    assert any("booking link" in b.lower() for b in report.blockers)


def test_quality_gate_permits_a_calendar_link_at_the_booking_step():
    """Same link, different moment — after a reply it's what they asked for."""
    report = check_copy(
        "Great — here's my calendar, Dana: calendly.com/me/30min. "
        "Thursday afternoon works well on my side if that suits Northwind.",
        "message",
        target(),
        allow_scheduler_link=True,
    )
    assert report.passed, report.all_issues


def test_asking_for_time_is_fine_at_the_booking_step():
    report = check_copy(
        "Happy to walk you through it, Dana — shall we schedule a call for "
        "Thursday? Here's my calendar: cal.com/me",
        "message",
        target(),
        allow_scheduler_link=True,
    )
    assert report.passed, report.all_issues


# ----------------------------------------------------------------------
# Reply detection against the database
# ----------------------------------------------------------------------


async def _target_row(db, org, account, icp, status=TargetStatus.CONTACTED):
    from src.targeting.schemas import TargetImportItem
    from src.targeting.service import import_targets

    organization, _ = org
    created, _ = await import_targets(
        db,
        org_id=str(organization.id),
        account_id=str(account.id),
        items=[
            TargetImportItem(
                profile_url="https://www.linkedin.com/in/dana-whitfield",
                full_name="Dana Whitfield",
                title="Head of Growth",
                company="Northwind",
                industry="SaaS",
                headline="Head of Growth at Northwind | B2B activation",
            )
        ],
        icp=icp,
    )
    row = created[0]
    row.status = status
    await db.commit()
    return row


async def test_marking_a_reply_cancels_queued_follow_ups(db, org, warm_account, icp):
    """Anything already queued for this person is withdrawn, not left to fire."""
    from src.outreach import suggest as engine
    from src.outreach import sync

    await _target_row(db, org, warm_account, icp, status=TargetStatus.SCORED)
    result = await engine.generate_suggestions(db, warm_account, icp)
    suggestion = result["created"][0]
    assert suggestion.status == SuggestionStatus.PENDING

    from sqlalchemy import select

    from src.targeting.models import OutreachTarget

    row = (
        await db.execute(
            select(OutreachTarget).where(OutreachTarget.id == suggestion.target_id)
        )
    ).scalar_one()

    await sync.mark_replied(db, row)

    await db.refresh(suggestion)
    assert suggestion.status == SuggestionStatus.CANCELLED
    assert "replied" in suggestion.error.lower()
    assert row.status == TargetStatus.REPLIED


async def test_a_reply_implies_the_invitation_was_accepted(db, org, warm_account, icp):
    """Otherwise the acceptance rate under-reports and throttles wrongly."""
    from src.outreach import sync

    row = await _target_row(db, org, warm_account, icp)
    await sync.mark_replied(db, row)
    assert row.accepted_at is not None
    assert row.replied_at is not None


async def test_acceptance_unlocks_the_follow_up(db, org, warm_account, icp):
    from src.outreach import sync

    row = await _target_row(db, org, warm_account, icp)
    await sync.mark_accepted(db, row)

    assert row.status == TargetStatus.CONNECTED
    step = sequences.advance(row, completed={"invite"}, last_touch_at=row.accepted_at)
    assert step.step.key == "welcome"


async def test_recording_an_outcome_ends_automation(db, org, warm_account, icp):
    from src.outreach import sync

    row = await _target_row(db, org, warm_account, icp)
    await sync.set_outcome(db, row, "booked")

    assert row.status == TargetStatus.BOOKED
    assert row.booked_at is not None
    assert not sequences.advance(row, completed=set())


async def test_sync_detects_replies_from_the_inbox(db, org, warm_account, icp):
    """An inbound message flips the target and stops the sequence."""
    from src.outreach import sync
    from src.infrastructure.transports.base import TransportResult

    row = await _target_row(db, org, warm_account, icp)
    row.member_urn = "dana-whitfield"
    await db.commit()

    class InboxTransport:
        name = "fake"

        async def fetch_inbox(self, account, since=None):
            return TransportResult(
                success=True,
                action="fetch_inbox",
                via=self.name,
                detail={
                    "conversations": [
                        {
                            "unreadCount": 1,
                            "participants": [{"entityUrn": "dana-whitfield"}],
                            "events": [],
                        }
                    ]
                },
            )

        async def fetch_connections(self, account, since=None):
            return TransportResult(
                success=True, action="fetch_connections", via=self.name,
                detail={"member_urns": []},
            )

    summary = await sync.sync_account(
        db, warm_account, transport=InboxTransport(), live=object()
    )
    await db.refresh(row)

    assert summary["replied"] == 1
    assert row.status == TargetStatus.REPLIED


async def test_sync_detects_acceptances(db, org, warm_account, icp):
    from src.outreach import sync
    from src.infrastructure.transports.base import TransportResult

    row = await _target_row(db, org, warm_account, icp)
    row.member_urn = "dana-whitfield"
    await db.commit()

    class ConnectionsTransport:
        name = "fake"

        async def fetch_inbox(self, account, since=None):
            return TransportResult(
                success=True, action="fetch_inbox", via=self.name,
                detail={"conversations": []},
            )

        async def fetch_connections(self, account, since=None):
            return TransportResult(
                success=True, action="fetch_connections", via=self.name,
                detail={"member_urns": ["urn:li:fs_profile:dana-whitfield"]},
            )

    summary = await sync.sync_account(
        db, warm_account, transport=ConnectionsTransport(), live=object()
    )
    await db.refresh(row)

    assert summary["accepted"] == 1
    assert row.status == TargetStatus.CONNECTED


async def test_sync_survives_a_transport_failure(db, org, warm_account, icp):
    """A sync that can't reach LinkedIn leaves state alone rather than crashing."""
    from src.outreach import sync

    row = await _target_row(db, org, warm_account, icp)

    class BrokenTransport:
        name = "broken"

        async def fetch_inbox(self, account, since=None):
            raise RuntimeError("network down")

        async def fetch_connections(self, account, since=None):
            raise RuntimeError("network down")

    summary = await sync.sync_account(
        db, warm_account, transport=BrokenTransport(), live=object()
    )
    await db.refresh(row)

    assert summary["errors"]
    assert row.status == TargetStatus.CONTACTED  # unchanged
