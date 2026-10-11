"""ReFrame's own AI: a viability model that learns what works.

It is a logistic-regression model over a dozen interpretable features. It
starts from *prior* weights that encode common startup knowledge (strong
demand, low competition and healthy unit economics help; high complexity
and funding gaps hurt). Every time you record the real outcome of a project
— did it succeed or not — the model retrains, pulled toward the evidence
but regularized toward the priors so a handful of outcomes cannot make it
overconfident.

Because the model is linear, each prediction can be explained exactly:
every feature's contribution to the score is ``weight * (value - 0.5)``.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .market import MarketAnalysis, clamp
from .models import Idea

# name -> (prior weight, label, advice when this feature drags the score down)
FEATURES: dict[str, tuple[float, str, str]] = {
    "market_gap": (1.6, "Demand vs. supply gap",
                   "Few buyers per competitor. Narrow to an underserved niche or region."),
    "demand_growth": (0.9, "Market growth",
                      "The market is flat. Look for a trend that is growing your buyers."),
    "competition": (-1.5, "Competition intensity",
                    "Crowded market. Compete on a specific segment, not head-on."),
    "differentiation": (1.5, "Differentiation",
                        "Buyers can't tell you apart. Define one thing you do 10x better."),
    "gross_margin": (1.0, "Gross margin",
                     "Thin margins. Cut unit cost or move upmarket."),
    "unit_economics": (1.8, "LTV / CAC",
                       "Customers cost more to win than they're worth. Find cheaper channels or raise retention."),
    "profitability": (1.4, "3-year profit / ROI",
                      "Projected profit is low. Revisit pricing, costs, or market size."),
    "speed_to_profit": (0.8, "Time to break even",
                        "Slow to break even. Ship a smaller paid MVP first."),
    "build_complexity": (-0.9, "Build complexity",
                         "Hard to build. Cut scope to the smallest version that solves the core problem."),
    "skill_fit": (0.8, "Skill fit",
                  "Skills gap. Partner, hire, or use no-code tools for the parts you can't do."),
    "funding": (0.9, "Funding coverage",
                "Your budget doesn't cover the cash dip. Pre-sell, reduce costs, or raise money."),
    "recurring": (0.6, "Recurring revenue",
                  "One-off sales. Add a subscription, consumables, or a service plan."),
}
# Most new projects fail, so a perfectly average idea starts below 50%.
PRIOR_BIAS = -0.5
# How strongly learned weights are pulled back toward the priors.
PRIOR_STRENGTH = 2.0


def featurize(idea: Idea, analysis: MarketAnalysis) -> dict[str, float]:
    m = idea.market
    if analysis.break_even_month is None:
        speed = 0.0
    else:
        speed = clamp(1 - (analysis.break_even_month - 1) / 36)
    at_risk = max(m.upfront_investment + m.fixed_costs_per_year, 1.0)
    return {
        "market_gap": analysis.market_gap,
        "demand_growth": clamp(m.demand_growth / 0.3),
        # log scale: 0 competitors -> 0, 9 -> 0.5, 99+ -> 1
        "competition": clamp(math.log10(max(m.competitors, 0) + 1) / 2),
        "differentiation": clamp(m.differentiation),
        "gross_margin": clamp(analysis.gross_margin),
        "unit_economics": clamp((analysis.ltv_to_cac - 1) / 4),
        "profitability": clamp((analysis.roi + 1) / 4),
        "speed_to_profit": speed,
        "build_complexity": clamp(m.build_complexity),
        "skill_fit": clamp(m.skill_fit),
        "funding": clamp(1 - analysis.funding_gap / at_risk),
        "recurring": 1.0 if idea.recurring_revenue else 0.0,
    }


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + math.exp(-z))
    e = math.exp(z)
    return e / (1 + e)


@dataclass
class Contribution:
    feature: str
    label: str
    value: float
    impact: float
    advice: str


class ViabilityModel:
    def __init__(self, weights: dict[str, float] | None = None, bias: float = PRIOR_BIAS,
                 trained_on: int = 0):
        self.weights = {k: v[0] for k, v in FEATURES.items()}
        if weights:
            self.weights.update({k: v for k, v in weights.items() if k in FEATURES})
        self.bias = bias
        self.trained_on = trained_on

    # -- prediction ---------------------------------------------------------
    def _z(self, x: dict[str, float]) -> float:
        return self.bias + sum(self.weights[k] * (x[k] - 0.5) for k in FEATURES)

    def predict(self, x: dict[str, float]) -> float:
        """Probability of success, 0..1."""
        return _sigmoid(self._z(x))

    def explain(self, x: dict[str, float]) -> list[Contribution]:
        out = [
            Contribution(k, FEATURES[k][1], x[k], self.weights[k] * (x[k] - 0.5), FEATURES[k][2])
            for k in FEATURES
        ]
        return sorted(out, key=lambda c: c.impact, reverse=True)

    # -- learning -----------------------------------------------------------
    def train(self, samples: list[tuple[dict[str, float], float]], epochs: int = 2000,
              lr: float = 0.1) -> None:
        """Fit to (features, outcome) pairs; outcome is 1 for success, 0 for failure.

        Minimizes log-loss plus an L2 penalty toward the prior weights.
        """
        if not samples:
            return
        n = len(samples)
        priors = {k: v[0] for k, v in FEATURES.items()}
        w, b = dict(self.weights), self.bias
        for _ in range(epochs):
            grad_w = {k: 0.0 for k in FEATURES}
            grad_b = 0.0
            for x, y in samples:
                p = _sigmoid(b + sum(w[k] * (x[k] - 0.5) for k in FEATURES))
                err = p - y
                for k in FEATURES:
                    grad_w[k] += err * (x[k] - 0.5)
                grad_b += err
            for k in FEATURES:
                reg = PRIOR_STRENGTH * (w[k] - priors[k])
                w[k] -= lr * (grad_w[k] / n + reg / n)
            b -= lr * (grad_b / n + PRIOR_STRENGTH * (b - PRIOR_BIAS) / n)
        self.weights, self.bias, self.trained_on = w, b, n

    def lessons(self) -> list[dict]:
        """How the model's beliefs moved away from the priors after learning."""
        rows = []
        for k, (prior, label, _) in FEATURES.items():
            delta = self.weights[k] - prior
            rows.append({"feature": k, "label": label, "prior": prior,
                         "learned": self.weights[k], "shift": delta})
        return sorted(rows, key=lambda r: abs(r["shift"]), reverse=True)

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"weights": self.weights, "bias": self.bias, "trained_on": self.trained_on}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "ViabilityModel":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text())
        return cls(data.get("weights"), data.get("bias", PRIOR_BIAS), data.get("trained_on", 0))
