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

_MAX_FLAGGED_PER_ITEM = 3  # Named individually; beyond this, just a count.


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


def find_similar(suggestions: List[Any]) -> Dict[str, List[str]]:
    """
    Compare every draft against every other draft for the *same action*
    (a formulaic comment and a formulaic connection note aren't the same
    failure just because both are short) and return, per suggestion id, the
    names of the other queued people it reads like.
    """
    by_action: Dict[str, List[Any]] = {}
    for s in suggestions:
        if _text_of(s):
            by_action.setdefault(getattr(s, "action", None), []).append(s)

    result: Dict[str, List[str]] = {}
    for group in by_action.values():
        if len(group) < 2:
            continue
        normalized = [
            _normalize(_text_of(s), getattr(getattr(s, "target", None), "first_name", None))
            for s in group
        ]
        for i, s_a in enumerate(group):
            matches = [
                group[j]
                for j in range(len(group))
                if j != i
                and SequenceMatcher(None, normalized[i], normalized[j]).ratio() >= SIMILARITY_THRESHOLD
            ]
            if matches:
                result[str(s_a.id)] = [_name_of(m) for m in matches[:_MAX_FLAGGED_PER_ITEM]]
    return result
