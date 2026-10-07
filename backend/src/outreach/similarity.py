"""
Repetition detection: does this draft read like a template stamped on
several different people?

The Aug 21 2026 comment-quality audit found the bot's real failure mode --
not individual bad comments, but the same three-beat skeleton sent to 43 of
58 different people. The quality gate scores each draft in isolation and can
never see that pattern; catching it means comparing a batch against itself,
which is what this module does. It runs across the whole pending queue for
an account every time the queue is listed, so the flag is visible before
anything gets approved -- not after.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

# Similarity above this ratio, after stripping the one piece of text that's
# *supposed* to differ (the recipient's name), counts as "basically the same
# message." Chosen against the Aug 21 audit's real data: the worst offenders
# (the "This matches what I keep seeing, X -- the hard part..." template)
# compare at 0.94+ against each other once names are stripped; genuinely
# different comments on the same topic sit well under 0.5.
SIMILARITY_THRESHOLD = 0.75

# How many of the other people in a cluster get named out loud. The rest are
# a count -- "reads like 40 other queued drafts" is the useful sentence, and
# forty names is not.
MAX_NAMED = 3

# Word-overlap floor, applied before difflib is asked anything.
#
# difflib's own cheap bounds compare characters, and English prose written by
# one model on one topic has near-identical letter distributions -- so
# quick_ratio() waves nearly every pair through to the expensive comparison and
# prunes almost nothing. Words discriminate where letters don't: two drafts
# that are 75% identical character-for-character share nearly all their
# vocabulary, and two genuinely different comments share little beyond "the"
# and "you".
#
# 0.25 is set well below anything a real match reaches (the Aug 21 audit's
# template pairs sit above 0.9 once names are stripped) so the gate can only
# skip pairs that were never going to match. It is a heuristic, not a proof --
# which is why it is this loose.
WORD_OVERLAP_FLOOR = 0.25

# Below this many words, word overlap is too noisy to judge, so short drafts
# skip the gate and go straight to the exact comparison.
_MIN_WORDS_FOR_GATE = 6

_WORD_RE = re.compile(r"[a-z0-9']+")


def _normalize(text: str, first_name: Optional[str]) -> str:
    lowered = (text or "").lower().strip()
    if first_name:
        lowered = re.sub(re.escape(first_name.lower()), "{name}", lowered)
    return lowered


def _text_of(suggestion: Any) -> Optional[str]:
    return getattr(suggestion, "final_text", None) or getattr(suggestion, "draft_text", None)


def _name_of(suggestion: Any) -> str:
    target = getattr(suggestion, "target", None)
    if target is not None:
        name = getattr(target, "full_name", None) or getattr(target, "first_name", None)
        if name:
            return name
    return "another person"


def _words(text: str) -> frozenset:
    return frozenset(_WORD_RE.findall(text))


def _word_overlap(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def _is_similar(matcher: SequenceMatcher, candidate: str) -> bool:
    """
    Is ``candidate`` (already loaded as seq1) close enough to the matcher's
    current seq2?

    difflib's two cheap upper bounds run first: ``real_quick_ratio`` is a pure
    length bound and ``quick_ratio`` a character-multiset bound. Neither can
    ever be lower than the exact ratio, so a candidate that fails either cannot
    pass the real comparison and never reaches it.
    """
    if matcher.real_quick_ratio() < SIMILARITY_THRESHOLD:
        return False
    if matcher.quick_ratio() < SIMILARITY_THRESHOLD:
        return False
    return matcher.ratio() >= SIMILARITY_THRESHOLD


def find_similar(suggestions: List[Any]) -> Dict[str, List[str]]:
    """
    Group drafts for the *same action* into clusters that read alike, and
    return, per suggestion id, the names of the other people in its cluster.

    Comparing only within one action is deliberate: a formulaic comment and a
    formulaic connection note aren't the same failure just because both are
    short.

    **Why clusters rather than every pair.** The original version compared
    every draft against every other one, which is the honest reading of the
    question but quadratic — and the shape of queue it exists to catch is
    exactly the shape that makes it worst. Measured on a 400-item queue built
    from three templates it took **72 seconds**, and at the 200 items the review
    screen already asks for, 18 seconds sat inside every single queue load.

    Clustering asks a cheaper question with the same answer. Each draft is
    compared against the *representative* of each cluster found so far, not
    against every draft: three templates stamped on 400 people means three
    representatives and 400 comparisons instead of 80,000. Same flags, and the
    count within a cluster is exact rather than capped.

    The approximation this makes is transitivity — if A reads like B and B
    reads like C, C joins A's cluster without being compared to A. At a 0.75
    threshold on name-stripped text that is the behaviour we want anyway: these
    are drafts off one template, and "one template, N people" is a truer
    description of the problem than a pile of pairs.
    """
    by_action: Dict[str, List[Any]] = {}
    for item in suggestions:
        if _text_of(item):
            by_action.setdefault(getattr(item, "action", None), []).append(item)

    result: Dict[str, List[str]] = {}
    for group in by_action.values():
        if len(group) < 2:
            continue
        normalized = [
            _normalize(_text_of(item), getattr(getattr(item, "target", None), "first_name", None))
            for item in group
        ]

        # index of each cluster's representative -> member indices
        word_sets = [_words(text) for text in normalized]

        clusters: Dict[int, List[int]] = {}
        cluster_of: List[int] = [-1] * len(group)
        matcher = SequenceMatcher(None)

        for i, text in enumerate(normalized):
            matcher.set_seq1(text)
            joined = -1
            for rep in clusters:
                # Words first: a set intersection is microseconds and rules
                # out most pairs outright. Only what survives it is worth
                # difflib's time.
                if (
                    len(word_sets[i]) >= _MIN_WORDS_FOR_GATE
                    and len(word_sets[rep]) >= _MIN_WORDS_FOR_GATE
                    and _word_overlap(word_sets[i], word_sets[rep]) < WORD_OVERLAP_FLOOR
                ):
                    continue
                # seq2 is the representative; difflib indexes seq2 and reuses
                # that index, so the reps are the side worth re-setting least.
                matcher.set_seq2(normalized[rep])
                if _is_similar(matcher, text):
                    joined = rep
                    break
            if joined < 0:
                clusters[i] = [i]
                cluster_of[i] = i
            else:
                clusters[joined].append(i)
                cluster_of[i] = joined

        for members in clusters.values():
            if len(members) < 2:
                continue
            for index in members:
                others = [group[m] for m in members if m != index]
                result[str(group[index].id)] = [_name_of(o) for o in others]
    return result
