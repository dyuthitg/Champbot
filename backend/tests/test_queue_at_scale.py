"""
The review queue when it isn't small.

The Sep 11 go-live commitment is "the broken-day scenarios are handled: empty
queue, 400 things waiting, a blocked comment, a dropped connection." These are
the 400-things-waiting ones, plus the repetition check that paging could
quietly have broken.
"""

from __future__ import annotations

import time
import uuid
from types import SimpleNamespace

import pytest

from src.api.middleware.clerk import RequestContext
from src.api.routes.outreach import list_suggestions
from src.outreach import similarity
from src.outreach.models import OutreachSuggestion, SuggestionStatus
from src.targeting.models import OutreachTarget

TEMPLATE = (
    "This matches what I keep seeing, {name} — the hard part is usually getting "
    "everyone to agree on it first. How did you handle that?"
)

DISTINCT = [
    "Cutting the signup form from nine fields to two is a bold call, {name}. "
    "What convinced you the other seven were not buying anything?",
    "Deleting the second onboarding screen is the detail I keep coming back to, "
    "{name} — most teams would have added a tooltip instead.",
    "Net revenue retention as the only number you trust is a strong position, "
    "{name}. Did the board take convincing?",
    "The week-two gap nobody builds for is exactly right, {name}. What ended up "
    "being the reason to come back on day nine?",
]


async def _fill(db, org, account, count, *, templated: bool, status=SuggestionStatus.PENDING):
    organization, _ = org
    made = []
    for i in range(count):
        name = f"Person{i:03d}"
        target = OutreachTarget(
            id=uuid.uuid4(),
            org_id=organization.id,
            account_id=account.id,
            member_urn=f"urn:li:fs_profile:{name}",
            public_id=name.lower(),
            profile_url=f"https://www.linkedin.com/in/{name.lower()}",
            full_name=name,
            first_name=name,
            title="Head of Growth",
            company="Northwind",
            headline="Head of Growth at Northwind",
            relevance_score=100 - (i % 40),
        )
        db.add(target)
        text = (TEMPLATE if templated else DISTINCT[i % len(DISTINCT)]).format(name=name)
        suggestion = OutreachSuggestion(
            id=uuid.uuid4(),
            org_id=organization.id,
            account_id=account.id,
            target_id=target.id,
            action="comment",
            status=status,
            draft_text=text,
            relevance_score=100 - (i % 40),
            quality_score=100,
            quality_warnings=[],
        )
        db.add(suggestion)
        made.append(suggestion)
    await db.commit()
    return made


def _ctx(org):
    organization, user = org
    return RequestContext(
        user_id=str(user.id),
        org_id=str(organization.id),
        clerk_user_id="scale-test",
        clerk_org_id=None,
        email="scale@example.com",
        role="owner",
    )


async def _page(db, org, account, *, limit=50, offset=0, status=SuggestionStatus.PENDING):
    return await list_suggestions(
        account_id=str(account.id),
        suggestion_status=status,
        limit=limit,
        offset=offset,
        ctx=_ctx(org),
        db=db,
    )


# ----------------------------------------------------------------------
# 400 things waiting
# ----------------------------------------------------------------------


async def test_total_counts_the_queue_not_the_page(db, org, warm_account):
    """
    ``total`` used to be ``len(suggestions)`` — the page size. A screen showing
    50 of 400 had no way to know, or say, that 350 more existed.
    """
    await _fill(db, org, warm_account, 120, templated=False)

    page = await _page(db, org, warm_account, limit=50)

    assert page.total == 120
    assert len(page.suggestions) == 50
    assert page.offset == 0
    assert page.has_more is True


async def test_paging_reaches_every_item_exactly_once(db, org, warm_account):
    """Ordering has to be stable or pages overlap and items go missing."""
    await _fill(db, org, warm_account, 130, templated=False)

    seen, offset = [], 0
    while True:
        page = await _page(db, org, warm_account, limit=50, offset=offset)
        seen.extend(s.id for s in page.suggestions)
        if not page.has_more:
            break
        offset += len(page.suggestions)

    assert len(seen) == 130
    assert len(set(seen)) == 130, "a page overlapped another — items seen twice"


async def test_the_last_page_says_it_is_the_last(db, org, warm_account):
    await _fill(db, org, warm_account, 60, templated=False)

    last = await _page(db, org, warm_account, limit=50, offset=50)

    assert len(last.suggestions) == 10
    assert last.has_more is False
    assert last.total == 60


async def test_an_offset_past_the_end_is_empty_not_an_error(db, org, warm_account):
    await _fill(db, org, warm_account, 10, templated=False)

    page = await _page(db, org, warm_account, limit=50, offset=500)

    assert page.suggestions == []
    assert page.total == 10
    assert page.has_more is False


# ----------------------------------------------------------------------
# The hole paging could have opened
# ----------------------------------------------------------------------


async def test_repetition_is_detected_across_pages_not_within_one(db, org, warm_account):
    """
    The subtle one. With one template stamped on 120 people and 50 per page, a
    check that only compared a page against itself would still work — but a
    template stamped on people who happen to land on *different* pages would
    look unique on every page. The comparison set is the whole queue.
    """
    await _fill(db, org, warm_account, 120, templated=True)

    last = await _page(db, org, warm_account, limit=50, offset=100)

    assert len(last.suggestions) == 20
    for item in last.suggestions:
        codes = {f.code for f in item.quality_flags}
        assert "DUP" in codes, "a template went unflagged on a later page"

    dup = next(f for f in last.suggestions[0].quality_flags if f.code == "DUP")
    # The count is of the whole queue, not of this page.
    assert "119 other queued drafts" in dup.detail


async def test_only_a_few_names_are_spelled_out(db, org, warm_account):
    """"Reads like 119 other queued drafts" is the useful sentence. A hundred
    and nineteen names is not."""
    await _fill(db, org, warm_account, 120, templated=True)

    page = await _page(db, org, warm_account, limit=10)
    item = page.suggestions[0]

    assert len(item.similar_to) == similarity.MAX_NAMED
    dup = next(f for f in item.quality_flags if f.code == "DUP")
    assert "and 116 more" in dup.detail


async def test_genuinely_different_drafts_are_not_flagged_at_scale(db, org, warm_account):
    """The false-positive side. Four real shapes across 120 people: each is a
    duplicate of its own kind and of nothing else."""
    await _fill(db, org, warm_account, 120, templated=False)

    page = await _page(db, org, warm_account, limit=50)

    for item in page.suggestions:
        dup = [f for f in item.quality_flags if f.code == "DUP"]
        assert dup, "the four repeated shapes should each be flagged"
        assert "119 other" not in dup[0].detail, "unrelated drafts were clustered together"


# ----------------------------------------------------------------------
# Speed
# ----------------------------------------------------------------------


@pytest.mark.parametrize("templated", [True, False])
def test_repetition_detection_survives_a_four_hundred_item_queue(templated):
    """
    Regression test with a real number attached.

    The original all-pairs comparison took **72 seconds** on a 400-item queue
    built from templates, and 18 seconds at the 200 rows the review screen was
    already asking for — inside every queue load. The bound here is deliberately
    loose (a slow CI box is not a regression) but it is two orders of magnitude
    below where this started.
    """
    template = TEMPLATE if templated else None
    items = []
    for i in range(400):
        name = f"Person{i:03d}"
        text = (template or DISTINCT[i % len(DISTINCT)]).format(name=name)
        items.append(
            SimpleNamespace(
                id=str(i),
                action="comment",
                draft_text=text,
                final_text=None,
                target=SimpleNamespace(first_name=name, full_name=name),
            )
        )

    started = time.perf_counter()
    result = similarity.find_similar(items)
    elapsed = time.perf_counter() - started

    assert len(result) == 400
    assert elapsed < 5.0, f"400-item queue took {elapsed:.1f}s"


def test_a_queue_of_unrelated_drafts_is_fast_too():
    """The other shape of worst case: nothing matches, so nothing clusters and
    every draft becomes its own representative to compare against."""
    items = [
        SimpleNamespace(
            id=str(i),
            action="comment",
            draft_text=(
                f"Point {i} about {'abcdefghij'[i % 10]}quisition and "
                f"{'klmnopqrst'[i % 10]}etention is the one worth pulling on, "
                f"and the {'uvwxyzabcd'[i % 10]}ownstream effect surprised us."
            ),
            final_text=None,
            target=SimpleNamespace(first_name=f"P{i}", full_name=f"P{i}"),
        )
        for i in range(400)
    ]

    started = time.perf_counter()
    similarity.find_similar(items)
    assert time.perf_counter() - started < 5.0
