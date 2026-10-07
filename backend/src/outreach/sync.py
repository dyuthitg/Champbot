"""
Pull state back from LinkedIn: who accepted, and who replied.

Everything else in this system decides what to *send*. This module is the only
one that listens, and it is what makes the sequence engine safe. Without it the
system would keep following up with people who already answered — the single
most damaging thing an outreach tool can do.

Two signals are synced:

- **Acceptance.** An invited target that now appears as a connection has
  accepted. This flips them to ``connected``, which unlocks the follow-up steps
  *and* feeds the acceptance-rate governor that decides whether it is safe to
  keep inviting at all.
- **Replies.** Any inbound message from a target stops their sequence dead and
  hands the conversation to a human.

Sync is deliberately conservative: an ambiguous signal is treated as "they
replied" rather than "carry on". A false positive costs one unsent follow-up; a
false negative costs the relationship.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.outreach.models import OutreachSuggestion, SuggestionStatus
from src.targeting.models import HUMAN_OWNED, OutreachTarget, TargetStatus

logger = logging.getLogger(__name__)


async def sync_account(
    db: AsyncSession,
    account,
    *,
    transport: Any = None,
    live: Any = None,
) -> dict:
    """
    Refresh acceptance and reply state for one account.

    Returns a summary of what changed. Transport failures are reported rather
    than raised: a sync that can't reach LinkedIn should leave the system in
    its previous (safe) state, not crash the scheduler.
    """
    from src.accounts.service import load_live_account

    live = live or await load_live_account(db, str(account.id))
    client = transport or _default_transport(live)

    summary = {"accepted": 0, "replied": 0, "errors": []}

    try:
        inbox = await client.fetch_inbox(live)
    except Exception as exc:
        summary["errors"].append(f"inbox: {exc}")
        inbox = None

    targets = await _tracked_targets(db, account)
    by_urn = {}
    for target in targets:
        by_urn[_norm(target.member_urn)] = target
        if target.public_id:
            by_urn[_norm(target.public_id)] = target

    now = datetime.now(timezone.utc)

    # --- Replies -------------------------------------------------------
    if inbox is not None and inbox.success:
        for participant in _inbound_participants(inbox.detail or {}):
            target = by_urn.get(_norm(participant))
            if target is None or target.status in HUMAN_OWNED:
                continue
            _mark_replied(target, now)
            summary["replied"] += 1

    # --- Acceptances ---------------------------------------------------
    # A reply implies acceptance, so replies are folded in first and only
    # still-invited targets need checking.
    try:
        connections = await client.fetch_connections(live)
    except AttributeError:
        connections = None  # transport predates connection listing
    except Exception as exc:
        summary["errors"].append(f"connections: {exc}")
        connections = None

    if connections is not None and connections.success:
        connected = {
            _norm(u) for u in (connections.detail or {}).get("member_urns", []) if u
        }
        for target in targets:
            if target.status != TargetStatus.CONTACTED:
                continue
            if _norm(target.member_urn) in connected or _norm(target.public_id or "") in connected:
                _mark_accepted(target, now)
                summary["accepted"] += 1

    if summary["accepted"] or summary["replied"]:
        await _stop_sequences(db, account, targets)

    await db.commit()
    return summary


async def mark_replied(
    db: AsyncSession, target: OutreachTarget, *, at: Optional[datetime] = None
) -> OutreachTarget:
    """Record a reply and halt this person's sequence."""
    _mark_replied(target, at or datetime.now(timezone.utc))
    await _cancel_pending_for_target(db, target)
    await db.commit()
    await db.refresh(target)
    return target


async def mark_accepted(
    db: AsyncSession, target: OutreachTarget, *, at: Optional[datetime] = None
) -> OutreachTarget:
    """Record an invitation acceptance, unlocking the follow-up steps."""
    _mark_accepted(target, at or datetime.now(timezone.utc))
    await db.commit()
    await db.refresh(target)
    return target


async def set_outcome(
    db: AsyncSession, target: OutreachTarget, outcome: str
) -> OutreachTarget:
    """
    Record a human's qualification verdict on a conversation.

    ``outcome`` is one of ``interested`` / ``booked`` / ``not_interested``.
    Anything other than "interested" ends automation for that person.
    """
    now = datetime.now(timezone.utc)
    mapping = {
        "interested": TargetStatus.INTERESTED,
        "booked": TargetStatus.BOOKED,
        "not_interested": TargetStatus.NOT_INTERESTED,
    }
    if outcome not in mapping:
        raise ValueError(f"unknown outcome: {outcome}")

    target.status = mapping[outcome]
    if outcome == "booked":
        target.booked_at = now
    if target.replied_at is None:
        target.replied_at = now

    await _cancel_pending_for_target(db, target)
    await db.commit()
    await db.refresh(target)
    return target


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------


def _default_transport(live):
    from src.infrastructure.api_client import get_transport

    return get_transport(live)


def _norm(value: Optional[str]) -> str:
    """Compare identities loosely — URNs come back in several flavours."""
    if not value:
        return ""
    text = str(value).strip().lower()
    return text.rsplit(":", 1)[-1].strip("()") if ":" in text else text


async def _tracked_targets(db: AsyncSession, account) -> list:
    """Targets this account has actually contacted or connected with."""
    stmt = select(OutreachTarget).where(
        OutreachTarget.account_id == account.id,
        OutreachTarget.status.in_(
            [TargetStatus.CONTACTED, TargetStatus.CONNECTED, TargetStatus.APPROVED]
        ),
    )
    return list((await db.execute(stmt)).scalars().all())


def _mark_replied(target: OutreachTarget, at: datetime) -> None:
    target.status = TargetStatus.REPLIED
    target.replied_at = target.replied_at or at
    # A reply proves the invitation was accepted, even if the connection sync
    # hasn't caught up yet -- otherwise the acceptance rate under-reports.
    target.accepted_at = target.accepted_at or at


def _mark_accepted(target: OutreachTarget, at: datetime) -> None:
    target.status = TargetStatus.CONNECTED
    target.accepted_at = target.accepted_at or at


def _inbound_participants(detail: dict) -> list:
    """
    Pull the sender identities of inbound messages out of an inbox payload.

    Voyager's conversation shape has changed repeatedly, so this reads
    defensively and prefers missing a conversation over misreading one.
    """
    participants = []
    for conversation in detail.get("conversations", []) or []:
        if not isinstance(conversation, dict):
            continue

        events = conversation.get("events") or []
        has_inbound = False
        sender = None

        for event in events:
            if not isinstance(event, dict):
                continue
            actor = event.get("from") or {}
            if isinstance(actor, dict):
                mini = actor.get("com.linkedin.voyager.messaging.MessagingMember") or actor
                urn = mini.get("entityUrn") or mini.get("miniProfile", {}).get("entityUrn")
            else:
                urn = None
            # Voyager marks the viewer's own events; anything else is inbound.
            if urn and not event.get("subtype") == "SPONSORED_MESSAGE":
                if not mini.get("isSelf") and not event.get("isSelf"):
                    has_inbound = True
                    sender = urn

        if has_inbound and sender:
            participants.append(sender)
        elif conversation.get("unreadCount"):
            # Unread implies someone wrote to us even if the event shape was
            # unreadable. Fall back to any participant we can identify.
            for member in conversation.get("participants", []) or []:
                if isinstance(member, dict):
                    urn = member.get("entityUrn")
                    if urn:
                        participants.append(urn)
                        break

    return participants


async def _stop_sequences(db: AsyncSession, account, targets: list) -> None:
    """Cancel queued work for anyone who is now human-owned."""
    stopped = [t for t in targets if t.status in HUMAN_OWNED]
    for target in stopped:
        await _cancel_pending_for_target(db, target)


async def _cancel_pending_for_target(db: AsyncSession, target: OutreachTarget) -> int:
    """
    Cancel every not-yet-sent suggestion aimed at this person.

    This is the mechanism behind "a reply stops the sequence": anything queued
    or awaiting review is withdrawn rather than left to fire later.
    """
    stmt = select(OutreachSuggestion).where(
        OutreachSuggestion.target_id == target.id,
        OutreachSuggestion.status.in_(
            [
                SuggestionStatus.PENDING,
                SuggestionStatus.APPROVED,
                SuggestionStatus.SCHEDULED,
                SuggestionStatus.BLOCKED,
            ]
        ),
    )
    rows = list((await db.execute(stmt)).scalars().all())
    for row in rows:
        row.status = SuggestionStatus.CANCELLED
        row.error = "Cancelled: the prospect replied, so the sequence stopped"
    return len(rows)
