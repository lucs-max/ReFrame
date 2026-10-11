"""Prompts and output formats shared by the Claude and local-AI integrations."""

from __future__ import annotations

import json

from .analyzer import Analysis
from .models import CATEGORIES, Idea, MarketInputs

MARKET_SCHEMA = {
    "type": "object",
    "properties": {name: {"type": "integer" if f.type == "int" else "number"}
                   for name, f in MarketInputs.__dataclass_fields__.items()},
    "required": list(MarketInputs.__dataclass_fields__),
    "additionalProperties": False,
}

IDEAS_SCHEMA = {
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
                    "market": MARKET_SCHEMA,
                },
                "required": ["title", "description", "category", "recurring_revenue", "market"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["ideas"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
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


def brainstorm_prompt(topic: str, count: int, constraints: str = "") -> tuple[str, str]:
    system = ("You are a pragmatic startup analyst. Propose business ideas with realistic, "
              "conservative market estimates. Prefer underserved niches with clear demand "
              "over crowded markets.")
    prompt = (f"Generate {count} distinct business ideas about: {topic}\n"
              f"Constraints from the founder: {constraints or 'none'}\n\n{FIELD_GUIDE}")
    return system, prompt


def review_prompt(idea: Idea, analysis: Analysis) -> tuple[str, str]:
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
    return system, json.dumps(payload, indent=2) + "\n\n" + FIELD_GUIDE
