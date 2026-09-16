"""
Tests for the OpenRouter two-slot LLM provider.

No network: a fake ChatClient records the model it was asked to use so we can
assert slot resolution, per-org overrides, and per-call overrides.
"""

import pytest

from src.infrastructure.llm.provider import (
    LLMProvider,
    ModelSlot,
    OpenRouterConfig,
    Slot,
)

pytestmark = pytest.mark.asyncio


class FakeClient:
    def __init__(self):
        self.calls = []

    async def chat(self, *, model, messages, temperature, max_tokens):
        self.calls.append(
            {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        return f"reply from {model}"


def make_config():
    return OpenRouterConfig(
        api_key="test",
        content=ModelSlot(model="anthropic/claude-3.5-sonnet", temperature=0.7, max_tokens=512),
        classification=ModelSlot(model="meta-llama/llama-3.1-8b-instruct", temperature=0.0, max_tokens=64),
    )


async def test_content_slot_uses_content_model():
    client = FakeClient()
    provider = LLMProvider(make_config(), client=client)

    result = await provider.write([{"role": "user", "content": "hi"}])

    assert result.slot == Slot.CONTENT
    assert result.model == "anthropic/claude-3.5-sonnet"
    assert client.calls[0]["temperature"] == 0.7
    assert client.calls[0]["max_tokens"] == 512


async def test_classification_slot_uses_classification_model():
    client = FakeClient()
    provider = LLMProvider(make_config(), client=client)

    result = await provider.classify([{"role": "user", "content": "label this"}])

    assert result.slot == Slot.CLASSIFICATION
    assert result.model == "meta-llama/llama-3.1-8b-instruct"
    assert client.calls[0]["temperature"] == 0.0
    assert client.calls[0]["max_tokens"] == 64


async def test_per_org_override_takes_precedence_over_config():
    client = FakeClient()

    async def resolver(org_id, slot):
        if org_id == "org-42" and slot == Slot.CONTENT:
            return ModelSlot(model="openai/gpt-4o", temperature=0.5, max_tokens=256)
        return None

    provider = LLMProvider(make_config(), client=client, settings_resolver=resolver)

    # org with an override
    r1 = await provider.write([{"role": "user", "content": "x"}], org_id="org-42")
    assert r1.model == "openai/gpt-4o"

    # different org falls back to config default
    r2 = await provider.write([{"role": "user", "content": "x"}], org_id="org-99")
    assert r2.model == "anthropic/claude-3.5-sonnet"


async def test_per_call_model_override_wins():
    client = FakeClient()
    provider = LLMProvider(make_config(), client=client)

    r = await provider.complete(
        Slot.CONTENT, [{"role": "user", "content": "x"}], model="mistralai/mistral-large"
    )
    assert r.model == "mistralai/mistral-large"


async def test_from_env_reads_models(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENROUTER_CONTENT_MODEL", "anthropic/claude-3-opus")
    monkeypatch.setenv("OPENROUTER_CLASSIFICATION_MODEL", "google/gemini-flash-1.5")

    cfg = OpenRouterConfig.from_env()
    assert cfg.content.model == "anthropic/claude-3-opus"
    assert cfg.classification.model == "google/gemini-flash-1.5"
    assert cfg.classification.temperature == 0.0
