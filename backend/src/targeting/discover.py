"""
Post discovery: find the thing a prospect actually said, so a comment can be
about it.

Why this module exists
----------------------
The copywriter and the quality gate both lean hard on ``target.context``
carrying ``post_text`` — ``copy.py:99`` feeds it to the model as the grounding
fact, ``quality.py`` R3 uses it to decide whether a draft references anything
real, and ``suggest.py:298`` will not even propose a ``comment`` action for a
target without a ``post_urn``. Until now nothing in the outreach loop ever
*put* it there: it had to arrive pre-filled on the import payload, or the
comment path silently never fired. The only code that fetched a prospect's
posts lived inside the warm-up runner (``src/warmup/runner.py:213``) and went
straight to creating its own suggestion, bypassing the review queue entirely.

This is that missing step, as its own stage: given targets that have a
``member_urn``, ask LinkedIn what they recently posted and store the newest one
we haven't already engaged with.

It reads. It never writes to LinkedIn. The worst case for a failure here is a
target with no post, which the suggestion engine already handles by not
proposing a comment.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.transports.base import TransportError
from src.targeting.models import OutreachTarget

logger = logging.getLogger(__name__)

# One fetch per target is one Voyager read. The default keeps a single sweep
# well inside the fetch_profile allowance in src/accounts/caps.py (150/day)
# rather than trusting the caller to pick a sane number.
DEFAULT_LIMIT = 25


async def refresh_posts(
    db: AsyncSession,
    account: Any,
    *,
    targets: Optional[List[OutreachTarget]] = None,
    client: Any = None,
    live: Any = None,
    limit: int = DEFAULT_LIMIT,
    refresh_existing: bool = False,
) -> Dict[str, Any]:
    """
    Attach each target's most recent post to ``target.context``.

    ``targets`` defaults to this account's targets that don't have a post yet.
    Pass ``refresh_existing=True`` to re-check targets that already have one —
    a post from three weeks ago is not something to comment on today.

    Returns a summary dict: how many were checked, how many gained a post, and
    why the rest didn't. The failure reasons are the point of the return value;
    a scrape stage that says "done" without saying what it couldn't reach is
    how you end up with an empty queue and no idea why.
    """
    from src.accounts.service import load_live_account

    if live is None:
        live = await load_live_account(db, str(account.id))
    if client is None:
        from src.infrastructure.api_client import get_transport

        client = get_transport(live)

    if targets is None:
        targets = await _targets_needing_posts(
            db, account, limit=limit, refresh_existing=refresh_existing
        )

    summary: Dict[str, Any] = {
        "checked": 0,
        "updated": 0,
        "no_posts": 0,
        "already_engaged": 0,
        "failed": 0,
        "errors": [],
    }

    engaged = await _already_engaged_urns(db, account)

    for target in targets:
        if not target.member_urn:
            # Nothing to ask LinkedIn about. Counted, not silently dropped.
            summary["failed"] += 1
            summary["errors"].append(f"{target.full_name or target.id}: no member_urn")
            continue

        summary["checked"] += 1
        try:
            result = await client.fetch_activity(live, target.member_urn)
        except TransportError as exc:
            summary["failed"] += 1
            summary["errors"].append(f"{target.full_name or target.id}: {exc}")
            logger.debug("Activity fetch failed for %s: %s", target.member_urn, exc)
            continue

        if not result.success:
            summary["failed"] += 1
            summary["errors"].append(
                f"{target.full_name or target.id}: {result.error or 'fetch_activity failed'}"
            )
            continue

        posts = (result.detail or {}).get("posts") or []
        fresh = [p for p in posts if p.get("urn") and p.get("text")]
        if not fresh:
            summary["no_posts"] += 1
            continue

        unseen = [p for p in fresh if p["urn"] not in engaged]
        if not unseen:
            # They have posts, we've already commented on all of them. Not a
            # failure -- a different outcome, and one worth counting separately
            # so "the queue is empty" has an explanation.
            summary["already_engaged"] += 1
            continue

        newest = unseen[0]
        context = dict(target.context or {})
        context.update(
            {
                "post_urn": newest["urn"],
                "post_text": newest["text"],
                "post_seen_at": datetime.now(timezone.utc).isoformat(),
                "post_source": (result.detail or {}).get("shape") or result.via,
            }
        )
        target.context = context
        summary["updated"] += 1

    await db.commit()
    for target in targets:
        if target in db:
            await db.refresh(target)
    return summary


async def refresh_profiles(
    db: AsyncSession,
    account: Any,
    *,
    targets: Optional[List[OutreachTarget]] = None,
    client: Any = None,
    live: Any = None,
    limit: int = DEFAULT_LIMIT,
) -> Dict[str, Any]:
    """
    Fill in name and headline for targets imported as bare handles.

    A prospect list in the wild is usually a column of profile URLs. Everything
    downstream -- the ICP scoring in ``scoring.py``, the copywriter's grounding
    facts, R3's personalization check -- needs the actual headline, and until
    now the only way to get it was for whoever built the CSV to have typed it
    in. This resolves it from the handle instead, through the same transport
    the rest of the product uses.

    Only fills blanks. A value that came in on the import is trusted over one
    scraped later; the human who built the list may know something we don't.
    """
    from src.accounts.service import load_live_account

    if live is None:
        live = await load_live_account(db, str(account.id))
    if client is None:
        from src.infrastructure.api_client import get_transport

        client = get_transport(live)

    if targets is None:
        stmt = (
            select(OutreachTarget)
            .where(OutreachTarget.account_id == account.id)
            .limit(limit)
        )
        targets = list((await db.execute(stmt)).scalars().all())

    summary: Dict[str, Any] = {"checked": 0, "updated": 0, "failed": 0, "errors": []}

    for target in targets:
        handle = target.public_id or target.member_urn
        if not handle:
            continue
        if target.headline and target.full_name:
            continue  # already known -- don't spend a request re-learning it

        summary["checked"] += 1
        try:
            result = await client.fetch_profile(live, handle)
        except TransportError as exc:
            summary["failed"] += 1
            summary["errors"].append(f"{handle}: {exc}")
            continue
        if not result.success:
            summary["failed"] += 1
            summary["errors"].append(f"{handle}: {result.error or 'fetch_profile failed'}")
            continue

        detail = result.detail or {}
        changed = False
        if not target.full_name and detail.get("display_name"):
            target.full_name = detail["display_name"]
            target.first_name = target.first_name or str(detail["display_name"]).split()[0]
            changed = True
        if not target.headline and detail.get("headline"):
            target.headline = detail["headline"]
            changed = True
        if detail.get("member_urn"):
            context = dict(target.context or {})
            context["profile_urn"] = detail["member_urn"]
            target.context = context
            changed = True
        if changed:
            summary["updated"] += 1

    await db.commit()
    return summary


async def _targets_needing_posts(
    db: AsyncSession, account: Any, *, limit: int, refresh_existing: bool
) -> List[OutreachTarget]:
    """This account's targets, newest-scored first, that could use a post."""
    from src.targeting.models import TargetStatus

    stmt = (
        select(OutreachTarget)
        .where(
            OutreachTarget.account_id == account.id,
            OutreachTarget.status.in_(
                [TargetStatus.NEW, TargetStatus.SCORED, TargetStatus.SUGGESTED]
            ),
        )
        .order_by(OutreachTarget.relevance_score.desc())
        .limit(limit * 4)  # over-fetch: most rows get filtered out below
    )
    rows = list((await db.execute(stmt)).scalars().all())

    picked = []
    for row in rows:
        context = row.context if isinstance(row.context, dict) else {}
        if context.get("post_urn") and not refresh_existing:
            continue
        picked.append(row)
        if len(picked) >= limit:
            break
    return picked


async def _already_engaged_urns(db: AsyncSession, account: Any) -> set:
    """Post URNs this account has already acted on — never comment twice."""
    from src.warmup.models import AccountActivity

    rows = (
        await db.execute(
            select(AccountActivity.subject_urn).where(
                AccountActivity.account_id == account.id,
                AccountActivity.subject_urn.is_not(None),
            )
        )
    ).scalars().all()
    return {r for r in rows if r}
