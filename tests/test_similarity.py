"""
Repetition-detection tests.

Built from the actual Aug 21 2026 audit pattern: the bot's real failure
wasn't one bad comment, it was the same template stamped on 43 of 58
different people. These tests prove the detector actually catches that
shape, not a synthetic stand-in for it.
"""

from types import SimpleNamespace

from src.outreach.similarity import find_similar


def suggestion(id, action, text, first_name, full_name):
    return SimpleNamespace(
        id=id,
        action=action,
        draft_text=text,
        final_text=None,
        target=SimpleNamespace(first_name=first_name, full_name=full_name),
    )


def test_the_actual_audit_template_is_flagged_across_three_people():
    """The real skeleton from the Aug 21 audit, stamped on three different
    names -- exactly the pattern nothing in the product could see before."""
    template = "This matches what I keep seeing, {name} — the hard part is usually getting everyone to agree on it first. How did you handle that?"
    items = [
        suggestion("1", "comment", template.format(name="Amaya"), "Amaya", "Amaya Reyes"),
        suggestion("2", "comment", template.format(name="Tom"), "Tom", "Tom Okafor"),
        suggestion("3", "comment", template.format(name="Marcus"), "Marcus", "Marcus Bell"),
    ]
    result = find_similar(items)

    assert set(result.keys()) == {"1", "2", "3"}
    assert "Tom Okafor" in result["1"]
    assert "Marcus Bell" in result["1"]
    assert "Amaya Reyes" in result["2"]


def test_genuinely_different_comments_are_not_flagged():
    items = [
        suggestion(
            "1", "comment",
            "Rewriting empty states to explain the product upfront is such an "
            "underrated lever -- did conversion move more than you expected?",
            "Priya", "Priya Sharma",
        ),
        suggestion(
            "2", "comment",
            "Cutting the signup form from nine fields to two is a bold call. "
            "What made you confident the extra fields weren't buying you anything?",
            "Daniel", "Daniel Hunt",
        ),
    ]
    result = find_similar(items)
    assert result == {}


def test_similar_text_on_different_actions_is_not_cross_flagged():
    """A formulaic comment and a formulaic connection note aren't the same
    failure just because both happen to be short and generic."""
    text = "Great to see your work on activation -- would love to connect."
    items = [
        suggestion("1", "comment", text, "Amaya", "Amaya Reyes"),
        suggestion("2", "connect", text, "Tom", "Tom Okafor"),
    ]
    result = find_similar(items)
    assert result == {}


def test_a_single_suggestion_has_nothing_to_compare_against():
    items = [suggestion("1", "comment", "Anything at all here.", "Amaya", "Amaya Reyes")]
    assert find_similar(items) == {}


def test_suggestions_without_draft_text_are_skipped_not_crashed_on():
    items = [
        suggestion("1", "comment", None, "Amaya", "Amaya Reyes"),
        suggestion("2", "comment", "", "Tom", "Tom Okafor"),
    ]
    assert find_similar(items) == {}


def test_final_text_is_compared_when_present_not_the_stale_draft():
    """Once an operator edits a draft, the edit is what should be compared
    -- not the original template it started from."""
    items = [
        suggestion("1", "comment", "This matches what I keep seeing, Amaya.", "Amaya", "Amaya Reyes"),
        suggestion("2", "comment", "This matches what I keep seeing, Tom.", "Tom", "Tom Okafor"),
    ]
    items[1].final_text = "I actually read your post twice -- the point about churn timing stuck with me."
    result = find_similar(items)
    assert result == {}
