"""Optional Claude integration for brainstorming and expert review.

ReFrame's own model does the scoring and learning offline. If the
``anthropic`` package is installed and credentials are configured
(``reframe set-key``, ``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile),
Claude can also:

* brainstorm new ideas with estimated market inputs (``brainstorm``), and
* write a qualitative review of an analyzed idea (``review``).

Market numbers produced by Claude are estimates — validate them with
customer interviews before trusting them.
"""

from __future__ import annotations

import json
import os

from .analyzer import Analysis
from .models import Idea
from .prompts import IDEAS_SCHEMA, REVIEW_SCHEMA, brainstorm_prompt, review_prompt

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    pass


class MissingAPIKey(LLMUnavailable):
    """No usable Anthropic API key: ask the user for one."""


class NoCredits(LLMUnavailable):
    """The key works but the Anthropic account has no credit left."""


NO_CREDITS_HELP = (
    "Your API key works, but your Anthropic account has no API credit.\n"
    "The Claude API is paid per use and billed separately from a Claude.ai subscription.\n"
    "Add credit at https://console.anthropic.com/settings/billing, then try again.\n"
    "Or brainstorm for free without Claude:  reframe brainstorm \"<topic>\" --offline"
)


NO_KEY_HELP = (
    "This feature uses Claude and needs an Anthropic API key.\n"
    "1. Create a key at https://console.anthropic.com/settings/keys\n"
    "2. Save it with:  reframe set-key   (or paste it in the web app)\n"
    "Everything else in ReFrame works without a key."
)


def _client(api_key: str | None = None):
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - depends on environment
        raise LLMUnavailable("Install the optional dependency: pip install \"reframe[ai]\"") from e
    key = os.environ.get("ANTHROPIC_API_KEY") or api_key
    # Without a key, the SDK can still use ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile.
    return anthropic, (anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic())


def _ask(system: str, prompt: str, schema: dict, api_key: str | None = None) -> dict:
    anthropic, client = _client(api_key)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "high", "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
    except TypeError as e:
        # The SDK raises a plain TypeError when it finds no credentials at all.
        if "authentication" in str(e).lower():
            raise MissingAPIKey(NO_KEY_HELP) from e
        raise
    except anthropic.AuthenticationError as e:
        raise MissingAPIKey("Your Anthropic API key was rejected (invalid or revoked).\n"
                            + NO_KEY_HELP) from e
    except anthropic.RateLimitError as e:
        raise LLMUnavailable("Rate limited by the Claude API; try again shortly.") from e
    except anthropic.APIStatusError as e:
        if "credit balance" in str(e.message).lower():
            raise NoCredits(NO_CREDITS_HELP) from e
        raise LLMUnavailable(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable("Could not reach the Claude API.") from e

    if response.stop_reason == "refusal":
        raise LLMUnavailable("Claude declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("Claude's answer was cut off; try a narrower request.")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def brainstorm(topic: str, count: int = 5, constraints: str = "",
               api_key: str | None = None) -> list[Idea]:
    system, prompt = brainstorm_prompt(topic, count, constraints)
    data = _ask(system, prompt, IDEAS_SCHEMA, api_key)
    return [Idea.from_dict(d) for d in data["ideas"]]


def review(idea: Idea, analysis: Analysis, api_key: str | None = None) -> dict:
    system, prompt = review_prompt(idea, analysis)
    return _ask(system, prompt, REVIEW_SCHEMA, api_key)
