"""
Post-discovery tests.

The scrape stage is new, and it is the stage the whole comment path silently
depended on without anyone owning it: ``suggest.py`` refuses to propose a
comment for a target with no ``post_urn``, so before this module existed the
comment path only fired when whoever built the import file happened to paste a
post in by hand. These tests pin the behaviour that matters — it finds the
post, it never comments on the same post twice, and it explains itself when it
can't reach someone.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from src.infrastructure.transports.base import TransportResult, TransportUnavailable
from src.targeting import discover
from src.targeting.models import OutreachTarget, TargetStatus


class FakeClient:
    """Stands in for the transport. Records what it was asked for."""

    def __init__(self, posts=None, profiles=None, fail_for=()):
        self.posts = posts or {}
        self.profiles = profiles or {}
        self.fail_for = set(fail_for)
        self.asked = []

    async def fetch_activity(self, live, member_urn):
        self.asked.append(("fetch_activity", member_urn))
        if member_urn in self.fail_for:
            raise TransportUnavailable("voyager said no")
        return TransportResult(
            success=True,
            action="fetch_activity",
            via="mobile",
            detail={"shape": "gql-contentCollections", "posts": self.posts.get(member_urn, [])},
        )

    async def fetch_profile(self, live, handle):
        self.asked.append(("fetch_profile", handle))
        if handle in self.fail_for:
            raise TransportUnavailable("voyager said no")
        return TransportResult(
            success=True,
            action="fetch_profile",
            via="mobile",
            detail=self.profiles.get(handle, {}),
        )


async def _target(db, account, handle, **kw):
    target = OutreachTarget(
        id=uuid.uuid4(),
        org_id=account.org_id,
        account_id=account.id,
        member_urn=handle,
        public_id=handle,
        profile_url=f"https://www.linkedin.com/in/{handle}",
        status=TargetStatus.SCORED,
        relevance_score=80,
        **kw,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target


# ----------------------------------------------------------------------
# refresh_posts
# ----------------------------------------------------------------------


async def test_the_newest_post_is_attached_to_the_target(db, org, warm_account):
    target = await _target(db, warm_account, "amaya", full_name="Amaya Reyes")
    client = FakeClient(
        posts={
            "amaya": [
                {"urn": "urn:li:activity:111", "text": "We deleted the second onboarding screen."},
                {"urn": "urn:li:activity:110", "text": "An older post nobody cares about."},
            ]
        }
    )

    summary = await discover.refresh_posts(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert summary["updated"] == 1
    assert target.context["post_urn"] == "urn:li:activity:111"
    assert "second onboarding screen" in target.context["post_text"]
    # Provenance: which endpoint shape this came from, so a parsing regression
    # is traceable to a shape rather than to "the scrape".
    assert target.context["post_source"] == "gql-contentCollections"


async def test_a_post_we_already_commented_on_is_never_offered_again(
    db, org, warm_account
):
    """The one mistake that is publicly embarrassing: two comments from the
    same account on the same post."""
    from src.warmup.models import AccountActivity

    db.add(
        AccountActivity(
            id=uuid.uuid4(),
            org_id=warm_account.org_id,
            account_id=warm_account.id,
            action="comment",
            status="sent",
            subject_urn="urn:li:activity:111",
        )
    )
    await db.commit()

    target = await _target(db, warm_account, "amaya", full_name="Amaya Reyes")
    client = FakeClient(
        posts={"amaya": [{"urn": "urn:li:activity:111", "text": "Already commented on this."}]}
    )

    summary = await discover.refresh_posts(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert summary["already_engaged"] == 1
    assert summary["updated"] == 0
    assert not (target.context or {}).get("post_urn")


async def test_someone_with_no_posts_is_counted_not_failed(db, org, warm_account):
    """"They haven't posted" and "we couldn't reach them" are different
    answers, and an empty queue needs to be able to tell you which."""
    target = await _target(db, warm_account, "quiet", full_name="Quiet Person")
    client = FakeClient(posts={"quiet": []})

    summary = await discover.refresh_posts(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert summary["no_posts"] == 1
    assert summary["failed"] == 0


async def test_a_transport_failure_is_reported_with_the_name(db, org, warm_account):
    target = await _target(db, warm_account, "broken", full_name="Broken Fetch")
    client = FakeClient(fail_for=["broken"])

    summary = await discover.refresh_posts(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert summary["failed"] == 1
    assert any("Broken Fetch" in err for err in summary["errors"])


async def test_a_target_that_already_has_a_post_is_not_re_fetched(db, org, warm_account):
    """Default sweep skips them; refresh_existing=True is the opt-in."""
    target = await _target(
        db,
        warm_account,
        "amaya",
        full_name="Amaya Reyes",
        context={"post_urn": "urn:li:activity:999", "post_text": "Yesterday's post."},
    )
    client = FakeClient(posts={"amaya": [{"urn": "urn:li:activity:111", "text": "Newer."}]})

    await discover.refresh_posts(db, warm_account, client=client, live=object())
    assert ("fetch_activity", "amaya") not in client.asked

    await discover.refresh_posts(
        db, warm_account, client=client, live=object(), refresh_existing=True
    )
    assert ("fetch_activity", "amaya") in client.asked


# ----------------------------------------------------------------------
# refresh_profiles
# ----------------------------------------------------------------------


async def test_a_bare_handle_gets_a_name_and_headline(db, org, warm_account):
    """The realistic import is a column of profile URLs and nothing else."""
    target = await _target(db, warm_account, "amaya")
    assert target.full_name is None

    client = FakeClient(
        profiles={
            "amaya": {
                "member_urn": "urn:li:fsd_profile:amaya",
                "display_name": "Amaya Reyes",
                "headline": "Head of Growth at Northwind",
            }
        }
    )
    summary = await discover.refresh_profiles(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert summary["updated"] == 1
    assert target.full_name == "Amaya Reyes"
    assert target.first_name == "Amaya"
    assert target.headline == "Head of Growth at Northwind"


async def test_details_from_the_import_win_over_scraped_ones(db, org, warm_account):
    """Whoever built the list may know something LinkedIn's headline doesn't."""
    target = await _target(
        db, warm_account, "amaya", full_name="Amaya R.", headline="Growth, ex-Stripe"
    )
    client = FakeClient(
        profiles={"amaya": {"display_name": "Amaya Reyes", "headline": "Head of Growth"}}
    )

    await discover.refresh_profiles(
        db, warm_account, targets=[target], client=client, live=object()
    )

    assert target.full_name == "Amaya R."
    assert target.headline == "Growth, ex-Stripe"
    assert ("fetch_profile", "amaya") not in client.asked  # not even asked


async def test_scraping_never_writes_to_linkedin(db, org, warm_account):
    """
    A read stage must stay a read stage. If this ever fails, something in the
    scrape path grew the ability to act on an account without a human seeing it.
    """
    target = await _target(db, warm_account, "amaya", full_name="Amaya Reyes")
    client = FakeClient(posts={"amaya": [{"urn": "urn:li:activity:1", "text": "A post."}]})

    await discover.refresh_profiles(db, warm_account, targets=[target], client=client, live=object())
    await discover.refresh_posts(db, warm_account, targets=[target], client=client, live=object())

    write_actions = {"comment", "connect", "send_message", "like", "follow", "create_post"}
    assert not [a for a, _ in client.asked if a in write_actions]
