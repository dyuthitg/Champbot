"""
Copy quality gate tests.

This gate is the thing standing between the product and being a spam cannon,
so the tests are written as "what must never get through".
"""

from types import SimpleNamespace

import pytest

from src.outreach.quality import CONNECT_NOTE_MAX, check_copy


def person(**kw):
    base = dict(
        first_name="Dana",
        full_name="Dana Whitfield",
        title="Head of Growth",
        company="Northwind",
        headline="Head of Growth at Northwind",
        industry="SaaS",
        context={},
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ----------------------------------------------------------------------
# Blockers: these must never reach a recipient
# ----------------------------------------------------------------------


def test_empty_copy_fails():
    report = check_copy("", "connect", person())
    assert not report.passed
    assert report.score == 0


@pytest.mark.parametrize(
    "text",
    [
        "Hi {{first_name}}, saw your work at Northwind and wanted to connect.",
        "Hi [Name], saw your work at Northwind and wanted to connect properly.",
        "Hi Dana, saw your work at XYZ and wanted to connect about growth work.",
        "Hi <first_name>, your growth work at Northwind looked interesting to me.",
    ],
)
def test_unfilled_placeholders_are_blocked(text):
    """A leaked merge field is the single most damaging tell. Never ship one."""
    report = check_copy(text, "connect", person())
    assert not report.passed
    assert any("placeholder" in b.lower() for b in report.blockers)


def test_booking_link_is_blocked_everywhere():
    report = check_copy(
        "Hi Dana, your growth work at Northwind is interesting. "
        "Grab a slot here: calendly.com/me/30min",
        "message",
        person(),
    )
    assert not report.passed
    assert any("booking link" in b.lower() for b in report.blockers)


def test_link_in_a_connection_note_is_blocked():
    report = check_copy(
        "Hi Dana, liked your growth work at Northwind — more at https://example.com",
        "connect",
        person(),
    )
    assert not report.passed
    assert any("link" in b.lower() for b in report.blockers)


def test_pitch_in_a_connection_request_is_blocked():
    report = check_copy(
        "Hi Dana, I help teams like Northwind grow. Can we schedule a call this week?",
        "connect",
        person(),
    )
    assert not report.passed
    assert any("pitch" in b.lower() for b in report.blockers)


def test_over_length_connection_note_is_blocked():
    text = "Hi Dana, your growth work at Northwind stood out. " + ("x" * CONNECT_NOTE_MAX)
    report = check_copy(text, "connect", person())
    assert not report.passed
    assert any("too long" in b.lower() for b in report.blockers)


# ----------------------------------------------------------------------
# Warnings: heavily penalized, surfaced to the reviewer
# ----------------------------------------------------------------------


def test_tired_phrasing_is_penalized():
    report = check_copy(
        "Hi Dana, I hope this message finds you well. I came across your profile "
        "at Northwind and thought I'd reach out about growth.",
        "message",
        person(),
    )
    assert report.score < 70
    assert any("worn-out" in w.lower() for w in report.warnings)


def test_generic_message_with_no_personal_detail_is_penalized():
    report = check_copy(
        "Hi there, I work with growth teams and would value connecting with you "
        "to swap notes on what is working.",
        "message",
        person(),
    )
    assert not report.passed
    assert any("personal detail" in w.lower() for w in report.warnings)


def test_all_about_the_sender_is_penalized():
    report = check_copy(
        "I run a growth agency. I have helped many teams. I would like to talk. "
        "I think we could work together on something interesting.",
        "message",
        person(),
    )
    assert report.score < 70


def test_hype_punctuation_and_shouting_penalized():
    report = check_copy(
        "Dana!! This is HUGE for Northwind!! You need to see this AMAZING result!",
        "message",
        person(),
    )
    assert report.score < 70


# ----------------------------------------------------------------------
# Good copy passes
# ----------------------------------------------------------------------


def test_specific_grounded_connection_note_passes():
    report = check_copy(
        "Hi Dana — your work leading growth at Northwind keeps coming up when "
        "people talk about B2B activation. Would be glad to connect.",
        "connect",
        person(),
    )
    assert report.passed, report.all_issues
    assert report.score >= 70
    assert "first_name" in report.stats["personalization_signals"]
    assert "company" in report.stats["personalization_signals"]


def test_referencing_their_post_counts_as_personalization():
    target = person(
        first_name=None,
        full_name=None,
        company=None,
        title=None,
        headline=None,
        context={"post_text": "We rebuilt our onboarding around activation metrics"},
    )
    report = check_copy(
        "The point about activation is the part most teams skip. What did you "
        "measure before you rebuilt it, and did that change what you shipped?",
        "comment",
        target,
    )
    assert "their_post" in report.stats["personalization_signals"]


def test_sharing_only_generic_topic_words_does_not_count_as_personalization():
    """Regression test for the Aug 21 2026 audit finding: the post-text check
    used to credit ANY shared 6+ letter word, so a templated comment on a
    generic-topic post scored a false 'their_post' signal. This is the actual
    worst-scoring comment from that audit (score 5/100) against its real
    source post -- the only words it shared with the post were "activation",
    "product", and "marketing", all now stoplisted the same way a generic
    headline word already was.
    """
    target = person(
        first_name="Amaya",
        full_name="Amaya Reyes",
        company=None,
        title=None,
        headline=None,
        context={
            "post_text": "Activation is a team sport — product, marketing "
            "and sales all own a piece.",
        },
    )
    report = check_copy(
        "You nailed it with the team aspect of activation. I've seen how "
        "alignment between product and marketing can significantly boost "
        "retention. What strategies have you found effective in fostering "
        "that collaboration at Trackr?",
        "comment",
        target,
    )
    assert "their_post" not in report.stats["personalization_signals"]


def test_allowed_acronyms_are_not_treated_as_shouting():
    report = check_copy(
        "Hi Dana — your SaaS growth work at Northwind, especially the B2B "
        "activation side, is the kind of thing I follow closely.",
        "connect",
        person(),
    )
    assert report.passed, report.all_issues


def test_gate_works_without_a_target():
    """Copy can be checked before a target is attached (e.g. template review)."""
    report = check_copy(
        "This is a reasonable length message that says something specific and "
        "asks you a real question about your work.",
        "message",
    )
    assert isinstance(report.score, int)
