"""Full analysis of an idea: market model + AI score + what-if experiments."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

from .brain import ViabilityModel, featurize
from .market import MarketAnalysis, analyze_market
from .models import Idea, MarketInputs

# Levers you control, and how each experiment changes the inputs.
EXPERIMENTS = {
    "Sharpen differentiation (+0.2)":
        lambda m: setattr(m, "differentiation", min(1.0, m.differentiation + 0.2)),
    "Cut acquisition cost 30%":
        lambda m: setattr(m, "customer_acquisition_cost", m.customer_acquisition_cost * 0.7),
    "Cut unit cost 25%":
        lambda m: setattr(m, "unit_cost", m.unit_cost * 0.75),
    "Halve fixed costs":
        lambda m: setattr(m, "fixed_costs_per_year", m.fixed_costs_per_year * 0.5),
    "Reduce scope (complexity -0.2)":
        lambda m: setattr(m, "build_complexity", max(0.0, m.build_complexity - 0.2)),
    "Improve retention (churn -30%)":
        lambda m: setattr(m, "yearly_churn", m.yearly_churn * 0.7),
    "Target a niche (1/2 the market, 1/3 the competitors)":
        lambda m: (setattr(m, "potential_customers", m.potential_customers // 2),
                   setattr(m, "competitors", m.competitors // 3)),
}


def verdict(score: float) -> str:
    if score >= 0.7:
        return "Strong: build it"
    if score >= 0.5:
        return "Promising: fix the top risks first"
    if score >= 0.35:
        return "Weak: rework the idea before building"
    return "Unlikely to work as-is: pivot or drop"


@dataclass
class Experiment:
    name: str
    score: float
    score_change: float
    profit: float
    profit_change: float


@dataclass
class Analysis:
    idea_title: str
    score: float
    verdict: str
    market: MarketAnalysis
    features: dict[str, float]
    strengths: list[dict]
    risks: list[dict]
    experiments: list[Experiment]
    defaulted_inputs: list[str]
    model_trained_on: int

    def to_dict(self) -> dict:
        return asdict(self)


def _score(idea: Idea, model: ViabilityModel) -> tuple[float, MarketAnalysis, dict[str, float]]:
    market = analyze_market(idea)
    x = featurize(idea, market)
    return model.predict(x), market, x


def analyze(idea: Idea, model: ViabilityModel | None = None,
            provided_inputs: set[str] | None = None) -> Analysis:
    model = model or ViabilityModel()
    score, market, x = _score(idea, model)

    contributions = model.explain(x)
    strengths = [asdict(c) for c in contributions if c.impact > 0.05][:4]
    risks = [asdict(c) for c in reversed(contributions) if c.impact < -0.05][:4]

    experiments = []
    for name, apply in EXPERIMENTS.items():
        variant = copy.deepcopy(idea)
        apply(variant.market)
        s, mk, _ = _score(variant, model)
        experiments.append(Experiment(name, s, s - score, mk.total_profit,
                                      mk.total_profit - market.total_profit))
    experiments.sort(key=lambda e: (round(e.score_change, 2), e.profit_change), reverse=True)

    defaulted = []
    if provided_inputs is not None:
        defaulted = [f for f in MarketInputs.__dataclass_fields__ if f not in provided_inputs]

    return Analysis(
        idea_title=idea.title,
        score=score,
        verdict=verdict(score),
        market=market,
        features=x,
        strengths=strengths,
        risks=risks,
        experiments=experiments,
        defaulted_inputs=defaulted,
        model_trained_on=model.trained_on,
    )


def rank(ideas: list[Idea], model: ViabilityModel | None = None) -> list[Analysis]:
    """Analyze several ideas and order them by success score, then profit."""
    results = [analyze(i, model) for i in ideas]
    return sorted(results, key=lambda a: (a.score, a.market.total_profit), reverse=True)
