"""
Brand voice profile tests.

The point of the schema is that a marketer can drop a YAML file in
config/brand_voices/ with no engineer involved. These tests hold two
promises that make that safe: the two real profiles the product ships with
actually load and validate, and a broken or missing profile degrades to the
default voice instead of blocking a draft.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from src.outreach import brand_voice
from src.outreach.brand_voice import BrandVoiceError, _parse, load_profile, render_style_rules
from src.outreach.copy import build_messages

REAL_PROFILES = ["lake-b2b", "loopwork"]


# ----------------------------------------------------------------------
# The two shipped profiles: real files, not fixtures
# ----------------------------------------------------------------------


@pytest.mark.parametrize("profile_id", REAL_PROFILES)
def test_shipped_profile_loads_and_validates(profile_id):
    profile = load_profile(profile_id)
    assert profile is not None, f"{profile_id}.yaml should load and pass the schema"
    assert profile.id == profile_id
    assert profile.brand_name
    assert len(profile.example_comments) >= 2


def test_shipped_profiles_are_meaningfully_different():
    """The whole point of two profiles is proving the schema generalises --
    they should not just be the same voice with a different name."""
    lake = load_profile("lake-b2b")
    loopwork = load_profile("loopwork")
    assert lake.formality != loopwork.formality
    assert lake.emoji_frequency != loopwork.emoji_frequency
    assert lake.max_sentences != loopwork.max_sentences


def test_list_profiles_returns_both_and_skips_template():
    ids = {p.id for p in brand_voice.list_profiles()}
    assert set(REAL_PROFILES) <= ids
    assert "_template" not in ids
    assert "schema" not in ids


# ----------------------------------------------------------------------
# Schema enforcement
# ----------------------------------------------------------------------


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _valid_data(profile_id="acme"):
    return {
        "id": profile_id,
        "brand_name": "Acme",
        "formality": "casual",
        "max_sentences": 2,
        "emoji_frequency": "never",
        "banned_phrases": ["synergy"],
        "example_comments": [
            {"post_context": "a", "comment": "one"},
            {"post_context": "b", "comment": "two"},
        ],
    }


def test_valid_minimal_profile_parses():
    path_stub = Path("acme.yaml")
    profile = _parse(_valid_data(), path_stub)
    assert profile.brand_name == "Acme"
    assert profile.cta_style == "soft_question"  # default applied
    assert profile.signoff == "none"


@pytest.mark.parametrize(
    "missing_key",
    ["id", "brand_name", "formality", "max_sentences", "emoji_frequency", "banned_phrases", "example_comments"],
)
def test_missing_required_field_is_rejected(missing_key):
    data = _valid_data()
    del data[missing_key]
    with pytest.raises(BrandVoiceError):
        _parse(data, Path("acme.yaml"))


def test_id_must_match_filename():
    data = _valid_data(profile_id="wrong-name")
    with pytest.raises(BrandVoiceError, match="must match the filename"):
        _parse(data, Path("acme.yaml"))


def test_bad_enum_value_is_rejected():
    data = _valid_data()
    data["formality"] = "shouty"
    with pytest.raises(BrandVoiceError, match="formality"):
        _parse(data, Path("acme.yaml"))


def test_max_sentences_out_of_range_is_rejected():
    data = _valid_data()
    data["max_sentences"] = 9
    with pytest.raises(BrandVoiceError):
        _parse(data, Path("acme.yaml"))


def test_fewer_than_two_examples_is_rejected():
    data = _valid_data()
    data["example_comments"] = [{"post_context": "a", "comment": "one"}]
    with pytest.raises(BrandVoiceError, match="example_comments"):
        _parse(data, Path("acme.yaml"))


def test_load_profile_missing_file_returns_none_not_raise():
    assert load_profile("does-not-exist") is None


def test_load_profile_none_id_returns_none():
    assert load_profile(None) is None


def test_broken_profile_on_disk_falls_back_to_none(tmp_path, monkeypatch):
    """An invalid file must never blow up a draft -- it degrades silently."""
    monkeypatch.setattr(brand_voice, "PROFILES_DIR", tmp_path)
    data = _valid_data(profile_id="broken")
    del data["banned_phrases"]
    _write(tmp_path, "broken", data)

    assert load_profile("broken") is None


# ----------------------------------------------------------------------
# What actually reaches the model
# ----------------------------------------------------------------------


def test_render_style_rules_carries_every_setting():
    profile = _parse(_valid_data(), Path("acme.yaml"))
    rendered = render_style_rules(profile)
    assert "At most 2 sentence" in rendered
    assert "Never use emoji" in rendered
    assert "synergy" in rendered


def test_build_messages_includes_brand_voice_when_icp_has_one():
    icp = SimpleNamespace(instructions=None, value_proposition=None, name="Test ICP", brand_voice_id="lake-b2b")
    target = SimpleNamespace(full_name="Dana Whitfield", first_name="Dana")
    account = SimpleNamespace(display_name="Test Account", headline=None)

    messages = build_messages("comment", target, account, icp)
    system = messages[0]["content"]

    assert "Lake B2B" in system
    assert "Never use these words or phrases" in system


def test_build_messages_omits_brand_voice_when_icp_has_none():
    icp = SimpleNamespace(instructions=None, value_proposition=None, name="Test ICP", brand_voice_id=None)
    target = SimpleNamespace(full_name="Dana Whitfield", first_name="Dana")
    account = SimpleNamespace(display_name="Test Account", headline=None)

    messages = build_messages("comment", target, account, icp)
    assert "Brand voice for this account" not in messages[0]["content"]


def test_build_messages_unknown_brand_voice_id_degrades_quietly():
    icp = SimpleNamespace(instructions=None, value_proposition=None, name="Test ICP", brand_voice_id="nonexistent")
    target = SimpleNamespace(full_name="Dana Whitfield", first_name="Dana")
    account = SimpleNamespace(display_name="Test Account", headline=None)

    # Must not raise -- a typo'd or deleted profile id should never block a draft.
    messages = build_messages("comment", target, account, icp)
    assert "Brand voice for this account" not in messages[0]["content"]
