"""
Brand voice profiles: how a comment should sound, defined as data.

A marketer edits a YAML file under ``config/brand_voices/`` -- no code, no
deploy beyond dropping the file in -- and it becomes selectable wherever an
ICP is configured. See ``config/brand_voices/README.md`` for the marketer's
side of this; this module is the only code that reads those files.

The copywriter (``src/outreach/copy.py``) turns a loaded profile into the
same kind of plain-English instructions it already follows, and layers it
*on top of* the shared defaults rather than replacing them: brand voice
governs tone, never the safety rules (no invented facts, no links, no
pitching) -- those apply to every brand, no exceptions.

A missing or invalid profile file degrades to the default voice; it never
raises out of ``load_profile`` and never blocks a draft.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import yaml

logger = logging.getLogger(__name__)

PROFILES_DIR = Path(__file__).resolve().parents[2] / "config" / "brand_voices"

_FORMALITY = {"casual", "conversational", "formal"}
_EMOJI = {"never", "rare", "occasional"}
_CTA = {"none", "soft_question", "direct_ask"}
_SIGNOFF = {"none", "first_name_only"}

# Files that are documentation, not profiles -- never offered in a picker.
_RESERVED_STEMS = {"_template", "schema"}


class BrandVoiceError(ValueError):
    """A profile file exists but doesn't match the schema."""


@dataclass
class ExampleComment:
    post_context: str
    comment: str


@dataclass
class BrandVoiceProfile:
    id: str
    brand_name: str
    formality: str
    max_sentences: int
    emoji_frequency: str
    banned_phrases: List[str]
    example_comments: List[ExampleComment]
    preferred_phrases: List[str] = field(default_factory=list)
    tone_words: List[str] = field(default_factory=list)
    cta_style: str = "soft_question"
    signoff: str = "none"
    notes: str = ""


def _require(data: dict, key: str, path: Path):
    value = data.get(key)
    if value in (None, "", []):
        raise BrandVoiceError(f"{path.name}: missing required field '{key}'")
    return value


def _enum(value, allowed: set, field_name: str, path: Path) -> str:
    value = str(value)
    if value not in allowed:
        raise BrandVoiceError(
            f"{path.name}: '{field_name}' must be one of {sorted(allowed)}, got {value!r}"
        )
    return value


def _parse(data: dict, path: Path) -> BrandVoiceProfile:
    if not isinstance(data, dict):
        raise BrandVoiceError(f"{path.name}: file must contain a YAML mapping")

    profile_id = str(_require(data, "id", path))
    if profile_id != path.stem:
        raise BrandVoiceError(
            f"{path.name}: 'id' ({profile_id!r}) must match the filename ({path.stem!r})"
        )

    max_sentences = _require(data, "max_sentences", path)
    try:
        max_sentences = int(max_sentences)
    except (TypeError, ValueError):
        raise BrandVoiceError(f"{path.name}: 'max_sentences' must be a whole number")
    if not (1 <= max_sentences <= 5):
        raise BrandVoiceError(f"{path.name}: 'max_sentences' must be between 1 and 5")

    banned = _require(data, "banned_phrases", path)
    if not isinstance(banned, list) or not all(isinstance(p, str) for p in banned):
        raise BrandVoiceError(f"{path.name}: 'banned_phrases' must be a list of words/phrases")

    raw_examples = _require(data, "example_comments", path)
    if not isinstance(raw_examples, list) or len(raw_examples) < 2:
        raise BrandVoiceError(f"{path.name}: 'example_comments' needs at least 2 entries")
    examples = []
    for i, ex in enumerate(raw_examples):
        if not isinstance(ex, dict) or not ex.get("post_context") or not ex.get("comment"):
            raise BrandVoiceError(
                f"{path.name}: example_comments[{i}] needs both 'post_context' and 'comment'"
            )
        examples.append(
            ExampleComment(post_context=str(ex["post_context"]), comment=str(ex["comment"]))
        )

    return BrandVoiceProfile(
        id=profile_id,
        brand_name=str(_require(data, "brand_name", path)),
        formality=_enum(_require(data, "formality", path), _FORMALITY, "formality", path),
        max_sentences=max_sentences,
        emoji_frequency=_enum(
            _require(data, "emoji_frequency", path), _EMOJI, "emoji_frequency", path
        ),
        banned_phrases=[str(p) for p in banned],
        example_comments=examples,
        preferred_phrases=[str(p) for p in (data.get("preferred_phrases") or [])],
        tone_words=[str(p) for p in (data.get("tone_words") or [])],
        cta_style=_enum(data.get("cta_style", "soft_question"), _CTA, "cta_style", path),
        signoff=_enum(data.get("signoff", "none"), _SIGNOFF, "signoff", path),
        notes=str(data.get("notes") or "").strip(),
    )


@lru_cache(maxsize=None)
def _load_cached(path_str: str, mtime_ns: int) -> BrandVoiceProfile:
    # ``mtime_ns`` is part of the cache key purely so an edited file (or a
    # freshly written one in a test) is re-read instead of serving a stale
    # parse from an earlier call at the same path.
    path = Path(path_str)
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return _parse(data, path)


def load_profile(profile_id: Optional[str]) -> Optional[BrandVoiceProfile]:
    """Load one profile by id. Returns None if it doesn't exist or doesn't parse."""
    if not profile_id:
        return None
    path = PROFILES_DIR / f"{profile_id}.yaml"
    if not path.exists():
        logger.warning("Brand voice profile not found: %s", profile_id)
        return None
    try:
        return _load_cached(str(path), path.stat().st_mtime_ns)
    except BrandVoiceError as exc:
        logger.error("Brand voice profile %r is invalid, falling back to default: %s", profile_id, exc)
        return None
    except yaml.YAMLError as exc:
        logger.error("Brand voice profile %r is not valid YAML, falling back to default: %s", profile_id, exc)
        return None


def list_profiles() -> List[BrandVoiceProfile]:
    """Every valid profile a marketer has dropped into config/brand_voices/."""
    if not PROFILES_DIR.exists():
        return []
    profiles = []
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        if path.stem in _RESERVED_STEMS:
            continue
        loaded = load_profile(path.stem)
        if loaded:
            profiles.append(loaded)
    return profiles


_EMOJI_RULE = {
    "never": "Never use emoji.",
    "rare": "Emoji only if one would feel completely natural here -- most comments should have none.",
    "occasional": "One emoji is fine when it genuinely fits; don't force it.",
}
_FORMALITY_RULE = {
    "casual": "Write like a friendly peer, not a brand account. Contractions and casual phrasing are good; no corporate polish.",
    "conversational": "Write like a knowledgeable professional talking to another one -- relaxed but credible.",
    "formal": "Write with restraint and precision, like a considered professional comment. No slang, no forced casualness.",
}
_CTA_RULE = {
    "none": "Do not end with a question. State the thought and stop.",
    "soft_question": "A light, genuine question is fine to close with, but never a generic one.",
    "direct_ask": "Ending with a direct, specific question is encouraged.",
}
_SIGNOFF_RULE = {
    "none": "Do not address them by name.",
    "first_name_only": "You may address them by first name, once.",
}


def render_style_rules(profile: BrandVoiceProfile) -> str:
    """Turn a profile into the plain-English instructions the model follows."""
    lines = [
        f"Brand voice: {profile.brand_name}.",
        _FORMALITY_RULE[profile.formality],
        f"At most {profile.max_sentences} sentence{'s' if profile.max_sentences != 1 else ''}.",
        _EMOJI_RULE[profile.emoji_frequency],
        _CTA_RULE[profile.cta_style],
        _SIGNOFF_RULE[profile.signoff],
    ]
    if profile.tone_words:
        lines.append(f"Tone: {', '.join(profile.tone_words)}.")
    if profile.banned_phrases:
        lines.append("Never use these words or phrases: " + ", ".join(profile.banned_phrases) + ".")
    if profile.preferred_phrases:
        lines.append(
            "Where it fits naturally, language like this is on-brand: "
            + ", ".join(profile.preferred_phrases) + "."
        )
    if profile.notes:
        lines.append(profile.notes)
    if profile.example_comments:
        lines.append(
            "Examples of this brand's voice -- match the style and register, "
            "never the specific content:"
        )
        for ex in profile.example_comments:
            lines.append(f'- On a post about "{ex.post_context}": "{ex.comment}"')
    return "\n".join(lines)
