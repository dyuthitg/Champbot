"""
Production OpenRouter chat client.

Thin wrapper over the OpenAI async SDK pointed at the OpenRouter endpoint.
OpenRouter is wire-compatible with the OpenAI Chat Completions API, so the
same client speaks to any model on OpenRouter (Anthropic, Llama, Mistral, ...)
selected purely by the ``model`` string.
"""

from __future__ import annotations

from typing import Sequence

from src.infrastructure.llm.provider import ChatClient, OpenRouterConfig


class OpenRouterClient(ChatClient):
    """OpenRouter-backed chat client using the OpenAI async SDK."""

    def __init__(self, config: OpenRouterConfig):
        if not config.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is not set; cannot create OpenRouterClient. "
                "Set it in the environment or inject a client for tests."
            )
        # Imported here so the module only requires `openai` when actually used.
        from openai import AsyncOpenAI

        default_headers = {}
        if config.referer:
            default_headers["HTTP-Referer"] = config.referer
        if config.app_title:
            default_headers["X-Title"] = config.app_title

        self._client = AsyncOpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
            default_headers=default_headers or None,
        )

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        resp = await self._client.chat.completions.create(
            model=model,
            messages=list(messages),
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
