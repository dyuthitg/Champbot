"""
Guardrail flag tests.

The gate has always known *why* it docked a draft; until now it only said so
in a free-text sentence, which meant the review queue could show a warning but
could never group two drafts that broke the same rule. These tests cover the
named-flag layer that fixes that, and the one property that matters most about
it: naming a rule must not change what the gate lets through.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.outreach.quality import (
    COMMENT_MAX,
    COMMENT_SENTENCE_MAX,
    COMMENT_TARGET_CHARS,
    CONNECT_NOTE_MAX,
    MESSAGE_IDEAL_MAX,
    MESSAGE_MAX,
    RULES,
    SEVERITIES,
    check_copy,
    count_sentences,
    has_formulaic_question,
)

REPO = Path(__file__).resolve().parents[1]


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


def codes(report) -> set:
    return set(report.flag_codes)


# ----------------------------------------------------------------------
# The vocabulary itself
# ----------------------------------------------------------------------


def test_every_rule_has_a_short_label():
    """The label is what an operator reads on a chip. A rule without one, or
    with a sentence for one, breaks the queue's layout and its scannability."""
    for code, rule in RULES.items():
        assert rule.code == code
        assert rule.label
        assert len(rule.label) <= 30, f"{code} label is too long for a chip"
        assert not rule.label.endswith("."), f"{code} label reads as a sentence"


def test_the_comment_spec_rules_are_all_present_and_cite_the_spec():
    """R1-R7 come from COMMENT_QUALITY_SPEC_V1.md and must say so, or the
    'same vocabulary everywhere' claim is decoration."""
    for n in range(1, 8):
        rule = RULES[f"R{n}"]
        assert rule.spec_ref and rule.spec_ref.startswith(f"R{n} ")


def test_checks_that_are_not_in_the_spec_admit_it():
    """An honest gap beats a rule that implies spec coverage it never had."""
    assert RULES["CTA"].spec_ref is None
    assert RULES["OPENER"].spec_ref is None
    assert RULES["DUP"].spec_ref is None


# ----------------------------------------------------------------------
# The three chips the brief actually named
# ----------------------------------------------------------------------


def test_too_long_is_flagged_as_r2():
    report = check_copy("word " * 100, "comment", person())
    assert "R2" in codes(report)
    assert RULES["R2"].label == "Too long"
    assert not report.passed


def test_generic_phrase_is_flagged_as_r4():
    report = check_copy(
        "Hi Dana, I hope this message finds you well and that Northwind's "
        "activation work is going smoothly this quarter.",
        "message",
        person(),
    )
    assert "R4" in codes(report)
    assert RULES["R4"].label == "Generic phrase"


def test_no_specific_reference_is_flagged_as_r3():
    report = check_copy(
        "Really useful perspective on how teams should think about the "
        "problem, and it lines up with what plenty of people are seeing.",
        "comment",
        person(),
    )
    assert "R3" in codes(report)
    assert RULES["R3"].label == "No specific reference"


# ----------------------------------------------------------------------
# Naming a rule must not change the verdict
# ----------------------------------------------------------------------


def test_every_blocker_and_warning_has_a_matching_flag():
    """The two views of a finding must never disagree: anything the gate says
    in prose has to be a named rule too, or the filter silently loses items."""
    report = check_copy(
        "HELLO {{first_name}}!!! I hope this message finds you well. "
        "Book a call at calendly.com/me/30min. We are the best-in-class "
        "platform and we do great work and we are excited!",
        "connect",
        person(),
    )
    flagged_details = {f.detail for f in report.flags}
    for issue in report.all_issues:
        assert issue in flagged_details, f"unnamed finding: {issue}"


def test_advisory_flags_never_touch_the_score_or_the_verdict():
    """
    The audit's own headline failure, run through the gate.

    43 of 58 comments ended in this shape and the gate scored every one of
    them 100/100 -- it has no rule for it. R1/R5 are shown here and *not*
    enforced, because tightening the shared gate is not a solo call
    (COMMENT_RULES_ENFORCEMENT_GAP.md). Visible, not blocking, is the whole
    point of today's change.
    """
    # No banned phrase in here on purpose -- the point of this test is that the
    # *advisory* rules leave the verdict alone, so anything that would legitimately
    # dock the score would hide the thing being tested. ("You're spot on" used to
    # open this fixture; it became an R4 warning on 2026-09-04, which is a
    # different rule and has its own test below.)
    text = (
        "Deleting the second onboarding screen is the part I keep coming back to, "
        "Dana. The handoff is always where it goes. Have you found any specific "
        "strategies that work well for that?"
    )
    report = check_copy(text, "comment", person())

    assert report.passed
    assert report.score == 100
    assert report.blockers == []
    assert report.warnings == []

    advisories = {f.code for f in report.flags if f.severity == "advisory"}
    assert "R5" in advisories


def test_the_specs_banned_phrases_are_actually_enforced():
    """
    Regression test for the gap the first staging run found.

    COMMENT_QUALITY_SPEC_V1.md's R4 list was written on 2026-08-25 with "wire
    this into _TIRED_PHRASES" filed under "this week, no new logic". It never
    got wired, so for ten days the enforced list and the written list were
    different documents -- and three of the five comments the model wrote in
    the first end-to-end run opened with one of the missing phrases.
    """
    spec_r4 = [
        "thanks for sharing",
        "great insights",
        "spot on",
        "you make a solid point",
        "you make a great point",
        "you raise a good point",
        "you raise a crucial point",
        "you nailed it",
        "you've nailed it",
        "absolutely agree",
        "that's a solid approach",
        "i hope this message finds you well",
        "quick question",
        "circle back",
        "touch base",
        "pick your brain",
        "synergy",
        "game changer",
    ]
    for phrase in spec_r4:
        report = check_copy(
            f"{phrase.capitalize()}, Dana. The Northwind activation work you "
            "described is the interesting part here.",
            "comment",
            person(),
        )
        assert "R4" in codes(report), f"spec phrase not enforced: {phrase}"


def test_phrases_the_spec_deliberately_allows_stay_allowed():
    """R4 bans named failures, not merely frequent wordings. These two recur
    often in the audit data and were left off the list on purpose."""
    for phrase in ("It's interesting how", "I've seen teams"):
        report = check_copy(
            f"{phrase} the second onboarding screen mattered more than the "
            "checklist did, Dana.",
            "comment",
            person(),
        )
        assert "R4" not in codes(report), f"wrongly banned: {phrase}"


def test_r5_covers_the_tense_the_spec_only_implied():
    """"Did you notice" is the same rule being broken as "have you noticed".
    The first staging run produced the first form and it sailed through."""
    assert has_formulaic_question("Did you notice any specific trends after the change?")
    assert has_formulaic_question("Have you noticed any specific trends after the change?")


def test_r1_is_advisory_and_only_for_comments():
    four_sentences = (
        "Dana, the Northwind write-up landed well. One thing stood out. "
        "The handoff point is where it usually breaks. Worth a longer read."
    )
    assert count_sentences(four_sentences) == 4

    comment = check_copy(four_sentences, "comment", person())
    assert "R1" in codes(comment)
    assert all(f.severity == "advisory" for f in comment.flags if f.code == "R1")
    assert comment.warnings == []

    # A direct message is allowed to be four sentences -- R1 is a comment rule.
    message = check_copy(four_sentences, "message", person())
    assert "R1" not in codes(message)


def test_an_acronym_is_not_shouting_because_of_a_question_mark():
    """
    Found in the first end-to-end staging run: the model wrote "...for boosting
    NRR?" and the gate called it shouting, while the same acronym mid-sentence
    was fine. The length test ran on the unstripped token, so punctuation
    decided the verdict.
    """
    with_mark = check_copy(
        "Net revenue retention cuts through the noise. What actually lifts NRR?",
        "comment",
        person(),
    )
    without = check_copy(
        "Net revenue retention cuts through the noise and NRR is the number.",
        "comment",
        person(),
    )
    assert "CAPS" not in codes(with_mark)
    assert "CAPS" not in codes(without)


def test_real_shouting_still_gets_flagged():
    report = check_copy(
        "This is GENUINELY SHOUTING at Dana about Northwind activation work.",
        "comment",
        person(),
    )
    assert "CAPS" in codes(report)


def test_severities_are_only_ever_the_three_we_defined():
    report = check_copy(
        "hi there {{name}}!! check www.example.com/thing and book a call soon",
        "connect",
        person(),
    )
    assert report.flags
    for flag in report.flags:
        assert flag.severity in SEVERITIES


def test_an_empty_draft_is_named_too():
    report = check_copy("", "comment", person())
    assert codes(report) == {"EMPTY"}


# ----------------------------------------------------------------------
# The two rule tests transcribed straight from the spec
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("One sentence only", 1),
        ("One. Two.", 2),
        ("One! Two? Three.", 3),
        ("Trailing whitespace.   ", 1),
    ],
)
def test_r1_sentence_counting_matches_the_spec_test(text, expected):
    assert count_sentences(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Have you found any specific strategies that work for this?",
        "What strategies have you found most effective here?",
        "Curious what approach you've tried for that metric?",
    ],
)
def test_r5_catches_the_shape_not_the_wording(text):
    """The audit had upwards of fifteen literal wordings of one template.
    Banning strings is whack-a-mole; the rule bans the shape."""
    assert has_formulaic_question(text)


@pytest.mark.parametrize(
    "text",
    [
        "What made you confident the extra fields weren't buying you anything?",
        "Did conversion move more than you expected?",
        "This is not a question at all.",
    ],
)
def test_r5_leaves_real_questions_alone(text):
    assert not has_formulaic_question(text)


# ----------------------------------------------------------------------
# The queue: named flags, including the cross-queue repetition one
# ----------------------------------------------------------------------


async def test_the_queue_returns_named_flags_including_repetition(
    db, org, warm_account, icp
):
    """
    End to end through the real list endpoint: the operator's queue must
    carry the rule names, and repetition -- which no single draft can see
    about itself -- has to arrive in the same vocabulary as everything else,
    or it cannot be filtered alongside the rest.
    """
    from src.api.middleware.clerk import RequestContext
    from src.api.routes.outreach import list_suggestions
    from src.outreach.models import OutreachSuggestion, SuggestionStatus
    from src.targeting.models import OutreachTarget
    import uuid as _uuid

    organization, user = org

    # Two people, and one template stamped on both -- the Aug 21 pattern.
    template = (
        "This matches what I keep seeing, {name} — the hard part is usually "
        "getting everyone to agree on it first. Have you found any specific "
        "strategies that worked?"
    )
    for first, last in (("Amaya", "Reyes"), ("Tom", "Okafor")):
        target = OutreachTarget(
            id=_uuid.uuid4(),
            org_id=organization.id,
            account_id=warm_account.id,
            profile_url=f"https://www.linkedin.com/in/{first.lower()}-{last.lower()}",
            member_urn=f"urn:li:fs_profile:{first.upper()}",
            full_name=f"{first} {last}",
            first_name=first,
            title="Head of Growth",
            company="Northwind",
            headline="Head of Growth at Northwind",
            relevance_score=80,
        )
        db.add(target)
        db.add(
            OutreachSuggestion(
                id=_uuid.uuid4(),
                org_id=organization.id,
                account_id=warm_account.id,
                target_id=target.id,
                action="comment",
                status=SuggestionStatus.PENDING,
                draft_text=template.format(name=first),
                relevance_score=80,
                quality_score=100,
                quality_warnings=[],
            )
        )
    await db.commit()

    ctx = RequestContext(
        user_id=str(user.id),
        org_id=str(organization.id),
        clerk_user_id="clerk_test",
        clerk_org_id=None,
        email="test@example.com",
        role="owner",
    )
    result = await list_suggestions(
        account_id=str(warm_account.id),
        suggestion_status=SuggestionStatus.PENDING,
        limit=50,
        # Passed explicitly: called directly like this, FastAPI's Query
        # defaults arrive as Query objects rather than their values.
        offset=0,
        ctx=ctx,
        db=db,
    )

    assert len(result.suggestions) == 2
    for item in result.suggestions:
        found = {f.code for f in item.quality_flags}
        assert "DUP" in found, "repetition must arrive as a named flag"
        assert "R5" in found, "the formulaic question must be visible in the queue"
        for flag in item.quality_flags:
            assert flag.label and flag.detail
            assert flag.severity in SEVERITIES

    dup = next(f for f in result.suggestions[0].quality_flags if f.code == "DUP")
    assert "Okafor" in dup.detail or "Reyes" in dup.detail


async def test_flags_follow_a_hand_edit(db, org, warm_account, icp):
    """
    quality_warnings is written once, when the draft is generated. If the
    chips read from it they would keep describing copy the operator has
    already rewritten -- so they are re-checked against the current text.
    """
    from src.api.routes.outreach import _serialize
    from src.outreach import suggest as engine
    from src.targeting.service import import_targets
    from src.targeting.schemas import TargetImportItem

    organization, _ = org
    await import_targets(
        db,
        org_id=str(organization.id),
        account_id=str(warm_account.id),
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
    result = await engine.generate_suggestions(db, warm_account, icp)
    suggestion = result["created"][0]

    clean = await _serialize(db, suggestion)
    assert "R4" not in {f.code for f in clean.quality_flags}

    # Stale by construction: the stored warnings still describe the old text.
    suggestion.final_text = "Hi Dana, I hope this message finds you well at Northwind."
    await db.commit()

    edited = await _serialize(db, suggestion)
    assert "R4" in {f.code for f in edited.quality_flags}


# ----------------------------------------------------------------------
# The frontend must not invent its own numbers
# ----------------------------------------------------------------------


def test_the_editor_counter_uses_the_gates_own_limits():
    """
    The live counter has to know the limits before the server has seen a
    keystroke, so the numbers are mirrored in frontend/src/lib/guardrails.ts.
    Mirrored numbers drift. This reads the file and fails when they do.
    """
    source = io.open(REPO / "frontend/src/lib/guardrails.ts", encoding="utf-8").read()

    def number(name: str) -> int:
        match = re.search(rf"^\s*{name}:\s*(\d+),", source, re.M)
        assert match, f"{name} is missing from guardrails.ts"
        return int(match.group(1))

    hard = source.split("export const SOFT_TARGET")[0]
    soft = source.split("export const SOFT_TARGET")[1]

    def number_in(block: str, name: str) -> int:
        match = re.search(rf"^\s*{name}:\s*(\d+),", block, re.M)
        assert match, f"{name} is missing"
        return int(match.group(1))

    assert number_in(hard, "connect") == CONNECT_NOTE_MAX
    assert number_in(hard, "comment") == COMMENT_MAX
    assert number_in(hard, "message") == MESSAGE_MAX
    assert number_in(soft, "comment") == COMMENT_TARGET_CHARS
    assert number_in(soft, "message") == MESSAGE_IDEAL_MAX

    sentence_max = re.search(r"SENTENCE_MAX = (\d+)", source)
    assert sentence_max and int(sentence_max.group(1)) == COMMENT_SENTENCE_MAX

    # And the labels must not be hard-coded there: they come from the API.
    # Comments are stripped first -- the file is allowed to *mention* a rule
    # name while explaining why it doesn't define one.
    code_only = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code_only = re.sub(r"^\s*//.*$", "", code_only, flags=re.M)
    for rule in RULES.values():
        assert rule.label not in code_only, (
            f"'{rule.label}' is hard-coded in guardrails.ts — rule names belong "
            "in src/outreach/quality.py only"
        )
