"""Optional Claude integration for brainstorming and expert review.

ReFrame's own model does the scoring and learning offline. If the
``anthropic`` package is installed and credentials are configured
(``ANTHROPIC_API_KEY`` or an ``ant auth login`` profile), Claude can also:

* brainstorm new ideas with estimated market inputs (``brainstorm``), and
* write a qualitative review of an analyzed idea (``review``).

Market numbers produced by Claude are estimates — validate them with
customer interviews before trusting them.
"""

from __future__ import annotations

import json

from .analyzer import Analysis
from .models import CATEGORIES, Idea, MarketInputs

MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMUnavailable(RuntimeError):
    pass


def _client():
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - depends on environment
        raise LLMUnavailable("Install the optional dependency: pip install 'reframe[ai]'") from e
    return anthropic, anthropic.Anthropic()


_MARKET_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "integer" if f.type == "int" else "number"}
                   for name, f in MarketInputs.__dataclass_fields__.items()},
    "required": list(MarketInputs.__dataclass_fields__),
    "additionalProperties": False,
}

_IDEAS_SCHEMA = {
    "type": "object",
    "properties": {
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "recurring_revenue": {"type": "boolean"},
                    "market": _MARKET_SCHEMA,
                },
                "required": ["title", "description", "category", "recurring_revenue", "market"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "hidden_risks": {"type": "array", "items": {"type": "string"}},
        "opportunities": {"type": "array", "items": {"type": "string"}},
        "questions_to_validate": {"type": "array", "items": {"type": "string"}},
        "suspicious_inputs": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "hidden_risks", "opportunities", "questions_to_validate",
                 "suspicious_inputs"],
    "additionalProperties": False,
}

FIELD_GUIDE = """Market input meanings:
potential_customers: people/businesses with the problem in the target market
demand_growth: yearly growth as a fraction (0.1 = 10%)
willingness_to_pay: median price per purchase buyers accept (USD)
price_elasticity: 0.5 inelastic .. 3 very price-sensitive
purchases_per_year: 12 for monthly subscription, 1 for one-off
yearly_churn: fraction of paying customers lost per year
competitors: direct alternatives buyers use today
differentiation: 0..1 how clearly better/different
unit_cost: variable cost per purchase (USD)
customer_acquisition_cost: cost to win one customer (USD)
fixed_costs_per_year, upfront_investment, budget: USD
build_complexity, skill_fit: 0..1"""


def _ask(system: str, prompt: str, schema: dict) -> dict:
    anthropic, client = _client()
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
    except anthropic.AuthenticationError as e:
        raise LLMUnavailable("Claude credentials missing or invalid (set ANTHROPIC_API_KEY).") from e
    except anthropic.RateLimitError as e:
        raise LLMUnavailable("Rate limited by the Claude API; try again shortly.") from e
    except anthropic.APIStatusError as e:
        raise LLMUnavailable(f"Claude API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMUnavailable("Could not reach the Claude API.") from e

    if response.stop_reason == "refusal":
        raise LLMUnavailable("Claude declined this request.")
    if response.stop_reason == "max_tokens":
        raise LLMUnavailable("Claude's answer was cut off; try a narrower request.")
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def brainstorm(topic: str, count: int = 5, constraints: str = "") -> list[Idea]:
    system = ("You are a pragmatic startup analyst. Propose business ideas with realistic, "
              "conservative market estimates. Prefer underserved niches with clear demand "
              "over crowded markets.")
    prompt = (f"Generate {count} distinct business ideas about: {topic}\n"
              f"Constraints from the founder: {constraints or 'none'}\n\n{FIELD_GUIDE}")
    data = _ask(system, prompt, _IDEAS_SCHEMA)
    return [Idea.from_dict(d) for d in data["ideas"]]


def review(idea: Idea, analysis: Analysis) -> dict:
    system = ("You are a skeptical investor and operator. Review the idea and the quantitative "
              "analysis. Point out what the numbers may be missing and which inputs look unrealistic.")
    payload = {
        "idea": idea.to_dict(),
        "analysis": {
            "success_score": analysis.score,
            "verdict": analysis.verdict,
            "optimal_price": analysis.market.optimal_price,
            "three_year_profit": analysis.market.total_profit,
            "ltv_to_cac": analysis.market.ltv_to_cac,
            "break_even_month": analysis.market.break_even_month,
            "strengths": [s["label"] for s in analysis.strengths],
            "risks": [r["label"] for r in analysis.risks],
        },
    }
    return _ask(system, json.dumps(payload, indent=2) + "\n\n" + FIELD_GUIDE, _REVIEW_SCHEMA)
