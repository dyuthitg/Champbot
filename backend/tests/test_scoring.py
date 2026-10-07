"""
Relevance scoring tests.

The scorer decides who gets contacted at all, so the cases that matter most are
the ones where it must say *no*: exclusions, near-misses on word boundaries, and
the empty ICP that would otherwise match the world.
"""

from types import SimpleNamespace

from src.targeting.scoring import score_target


def icp(**kw):
    base = dict(
        titles=[],
        seniorities=[],
        industries=[],
        keywords=[],
        excluded_keywords=[],
        excluded_titles=[],
        locations=[],
        relevance_floor=60,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def person(**kw):
    base = dict(
        title=None, headline=None, company=None, industry=None, location=None
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_full_match_scores_high_and_explains_itself():
    result = score_target(
        person(
            title="Head of Growth",
            company="Northwind",
            industry="SaaS",
            location="London",
            headline="Head of Growth at Northwind | scaling B2B SaaS",
        ),
        icp(
            titles=["head of growth"],
            industries=["saas"],
            keywords=["b2b", "scaling"],
            locations=["london"],
        ),
    )

    assert result.score == 100
    assert not result.excluded
    # Every reason is human-readable, not a bare number.
    assert any("Title matches" in r for r in result.reasons)
    assert any("Industry matches" in r for r in result.reasons)
    assert any("Located in" in r for r in result.reasons)


def test_partial_match_is_scored_only_on_dimensions_the_icp_defines():
    # ICP names only titles, so a title match is a full match -- it isn't
    # penalized for the fields the user left blank.
    result = score_target(
        person(title="Head of Growth"),
        icp(titles=["head of growth"]),
    )
    assert result.score == 100


def test_missing_dimension_reduces_score_proportionally():
    result = score_target(
        person(title="Head of Growth", industry="Logistics"),
        icp(titles=["head of growth"], industries=["saas"]),
    )
    # Title (35) earned out of title+industry (55) available.
    assert 60 <= result.score <= 65


def test_excluded_keyword_is_absolute():
    """A perfect match is still excluded if it trips an exclusion."""
    result = score_target(
        person(
            title="Head of Growth",
            industry="SaaS",
            headline="Head of Growth | freelance recruiter",
        ),
        icp(titles=["head of growth"], industries=["saas"], excluded_keywords=["recruiter"]),
    )
    assert result.excluded
    assert result.score == 0
    assert "recruiter" in result.exclusion_reason


def test_excluded_title_blocks_even_with_other_matches():
    result = score_target(
        person(title="Student", headline="Student at LSE, interested in SaaS growth"),
        icp(keywords=["saas", "growth"], excluded_titles=["student"]),
    )
    assert result.excluded


def test_word_boundaries_prevent_false_positives():
    """'ai' must not match 'chair'; 'cto' must not match 'director'."""
    result = score_target(
        person(title="Chair of the Board", headline="Director of Operations"),
        icp(titles=["ai", "cto"]),
    )
    assert result.score == 0


def test_multi_word_titles_match_as_phrases():
    result = score_target(
        person(headline="VP of Engineering at Acme"),
        icp(titles=["vp of engineering"]),
    )
    assert result.score == 100


def test_empty_icp_matches_nobody():
    """An ICP with no criteria must fail closed, not target everyone."""
    result = score_target(person(title="Anyone", headline="Anything"), icp())
    assert result.excluded
    assert result.score == 0
    assert result.exclusion_reason == "empty ICP"


def test_seniority_inferred_from_headline():
    result = score_target(
        person(headline="Co-Founder & CEO at Northwind"),
        icp(seniorities=["founder"]),
    )
    assert result.score == 100
    assert any("Seniority" in r for r in result.reasons)


def test_keyword_partial_credit_scales_with_hits():
    one = score_target(
        person(headline="We do b2b sales"), icp(keywords=["b2b", "plg", "retention"])
    )
    many = score_target(
        person(headline="b2b plg retention specialist"),
        icp(keywords=["b2b", "plg", "retention"]),
    )
    assert 0 < one.score < many.score
    assert many.score == 100


def test_scoring_accepts_plain_dicts():
    """Duck typing: dicts work as well as ORM rows, so the API can score
    unsaved input from the ICP preview endpoint."""
    result = score_target(
        {"title": "Head of Growth"}, {"titles": ["head of growth"], "relevance_floor": 60}
    )
    assert result.score == 100
