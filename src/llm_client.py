"""Thin async wrapper around the Anthropic SDK shared by all agents.

Why a wrapper: every agent does basically the same thing — send a system prompt
plus a JSON-blob user message and expect strict JSON back. Centralising that
keeps each agent file focused on its domain logic + its own prompt rather than
on boilerplate JSON-parsing and fence-stripping.
"""
import json
import os
from anthropic import AsyncAnthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
REPORT_MODEL = "claude-sonnet-4-6"           # used by the orchestrator for the final HTML composition


_client: AsyncAnthropic | None = None


def get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


async def ask_json(system_prompt: str, user_payload: str | dict,
                    model: str = DEFAULT_MODEL, max_tokens: int = 1024) -> dict:
    """Send a prompt expecting strict JSON back. Strips code fences if the model added them."""
    client = get_client()
    payload_str = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": payload_str}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


async def ask_text(system_prompt: str, user_payload: str | dict,
                   model: str = REPORT_MODEL, max_tokens: int = 3072) -> str:
    """Send a prompt expecting free-form text (HTML) back."""
    client = get_client()
    payload_str = user_payload if isinstance(user_payload, str) else json.dumps(user_payload, ensure_ascii=False)

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": payload_str}],
    )
    return response.content[0].text.strip()
