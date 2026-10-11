"""Core data types shared across ReFrame."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CATEGORIES = (
    "saas",
    "mobile_app",
    "ecommerce",
    "marketplace",
    "content",
    "physical_product",
    "service",
    "api",
)


@dataclass
class MarketInputs:
    """What you know (or estimate) about the market for an idea.

    Every field has a neutral default so an idea can be analyzed with
    partial information; the analysis reports which inputs were defaulted.
    """

    # Demand side
    potential_customers: int = 10_000  # people/businesses who have the problem
    demand_growth: float = 0.05  # yearly growth of that group (0.05 = 5%)
    willingness_to_pay: float = 20.0  # typical price buyers accept today
    price_elasticity: float = 1.5  # >1: demand drops fast when price rises
    purchases_per_year: float = 12.0  # 12 for a monthly subscription, 1 for one-off
    yearly_churn: float = 0.3  # share of paying customers lost each year (recurring only)

    # Supply side
    competitors: int = 5  # direct alternatives buyers can choose today
    differentiation: float = 0.5  # 0..1, how clearly better/different you are

    # Unit economics
    unit_cost: float = 4.0  # variable cost per purchase
    customer_acquisition_cost: float = 30.0
    fixed_costs_per_year: float = 12_000.0
    upfront_investment: float = 5_000.0

    # Execution
    build_complexity: float = 0.5  # 0 trivial .. 1 very hard
    skill_fit: float = 0.5  # 0 none .. 1 you have every skill needed
    budget: float = 10_000.0  # money you can put in

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MarketInputs":
        data = data or {}
        known = {f: data[f] for f in cls.__dataclass_fields__ if f in data}
        inputs = cls(**known)
        for name, f in cls.__dataclass_fields__.items():
            cast = int if f.type == "int" else float
            setattr(inputs, name, cast(getattr(inputs, name)))
        return inputs

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Idea:
    title: str
    description: str = ""
    category: str = "saas"
    recurring_revenue: bool = True
    market: MarketInputs = field(default_factory=MarketInputs)
    id: int | None = None
    created_at: str | None = None

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"Unknown category {self.category!r}; choose one of {', '.join(CATEGORIES)}"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Idea":
        return cls(
            title=data["title"],
            description=data.get("description", ""),
            category=data.get("category", "saas"),
            recurring_revenue=bool(data.get("recurring_revenue", True)),
            market=MarketInputs.from_dict(data.get("market")),
            id=data.get("id"),
            created_at=data.get("created_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["market"] = self.market.to_dict()
        return d
