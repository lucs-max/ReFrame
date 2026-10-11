"""Supply & demand and profit model.

The model is deliberately simple and transparent so every number can be
traced back to an input:

* Demand: ``willingness_to_pay`` is treated as the *median* price buyers
  accept. The share of the market that buys at price ``p`` is
  ``1 / (1 + (p / wtp) ** (2 * elasticity))`` — half the market at the
  median, falling faster the more price-sensitive the market is.
* Supply: your "fair share" of the market is ``pull / (competitors + 1)``
  where pull grows with differentiation. A new entrant realistically
  obtains only ``OBTAINABLE`` (10%) of that fair share within three years.
* Adoption ramps over three years (30% → 65% → 100% of the steady share)
  while the market itself grows by ``demand_growth`` each year.
* The price is chosen by searching for the one that maximizes 3-year profit.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

from .models import Idea, MarketInputs

YEARS = 3
ADOPTION_RAMP = (0.30, 0.65, 1.00)
MAX_SHARE = 0.5
OBTAINABLE = 0.10


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def buy_fraction(price: float, wtp: float, elasticity: float) -> float:
    if price <= 0:
        return 1.0
    if wtp <= 0:
        return 0.0
    return 1.0 / (1.0 + (price / wtp) ** (2.0 * max(elasticity, 0.05)))


def steady_share(m: MarketInputs) -> float:
    """Share of the market you can win once fully ramped (before price effects)."""
    pull = 0.2 + 0.8 * clamp(m.differentiation)
    return OBTAINABLE * min(MAX_SHARE, pull / (max(m.competitors, 0) + 1))


@dataclass
class YearResult:
    year: int
    customers: float
    new_customers: float
    revenue: float
    variable_costs: float
    acquisition_costs: float
    fixed_costs: float
    profit: float


@dataclass
class MarketAnalysis:
    optimal_price: float
    price_vs_wtp: float
    years: list[YearResult]
    total_revenue: float
    total_profit: float
    roi: float
    gross_margin: float
    ltv: float
    ltv_to_cac: float
    break_even_month: int | None
    market_gap: float  # 0..1 how under-supplied the market is
    demand_per_competitor: float
    funding_gap: float  # money still needed beyond your budget (0 if covered)

    def to_dict(self) -> dict:
        return asdict(self)


def simulate(idea: Idea, price: float) -> list[YearResult]:
    m = idea.market
    share = steady_share(m) * buy_fraction(price, m.willingness_to_pay, m.price_elasticity)
    churn = clamp(m.yearly_churn) if idea.recurring_revenue else 1.0
    results: list[YearResult] = []
    prev_customers = 0.0
    for year in range(1, YEARS + 1):
        population = m.potential_customers * (1 + m.demand_growth) ** (year - 1)
        customers = population * share * ADOPTION_RAMP[year - 1]
        new_customers = max(0.0, customers - prev_customers * (1 - churn))
        revenue = customers * price * m.purchases_per_year
        variable = customers * m.unit_cost * m.purchases_per_year
        acquisition = new_customers * m.customer_acquisition_cost
        profit = revenue - variable - acquisition - m.fixed_costs_per_year
        results.append(
            YearResult(year, customers, new_customers, revenue, variable,
                       acquisition, m.fixed_costs_per_year, profit)
        )
        prev_customers = customers
    return results


def _cumulative_profit(idea: Idea, price: float) -> float:
    return sum(y.profit for y in simulate(idea, price)) - idea.market.upfront_investment


def find_optimal_price(idea: Idea) -> float:
    """Grid search, then refine around the best point."""
    wtp = max(idea.market.willingness_to_pay, 0.01)
    floor = max(idea.market.unit_cost, wtp * 0.1)
    candidates = [floor + (wtp * 3 - floor) * i / 200 for i in range(201)]
    best = max(candidates, key=lambda p: _cumulative_profit(idea, p))
    step = (wtp * 3 - floor) / 200
    fine = [best + step * (i - 50) / 50 for i in range(101)]
    best = max((p for p in fine if p > 0), key=lambda p: _cumulative_profit(idea, p))
    return round(best, 2)


def _break_even_month(idea: Idea, years: list[YearResult]) -> int | None:
    cash = -idea.market.upfront_investment
    for y in years:
        monthly = y.profit / 12
        for month in range(12):
            cash += monthly
            if cash >= 0:
                return (y.year - 1) * 12 + month + 1
    return None


def analyze_market(idea: Idea) -> MarketAnalysis:
    m = idea.market
    price = find_optimal_price(idea)
    years = simulate(idea, price)
    total_revenue = sum(y.revenue for y in years)
    total_profit = sum(y.profit for y in years) - m.upfront_investment

    gross_margin = (price - m.unit_cost) / price if price > 0 else 0.0
    lifetime_years = 1 / max(m.yearly_churn, 0.05) if idea.recurring_revenue else 1.0
    ltv = (price - m.unit_cost) * m.purchases_per_year * lifetime_years
    ltv_to_cac = ltv / m.customer_acquisition_cost if m.customer_acquisition_cost > 0 else 10.0

    demand_per_competitor = m.potential_customers / (m.competitors + 1)
    # 100 buyers per supplier -> 0, 100k+ per supplier -> 1 (log scale), boosted by growth
    gap = (math.log10(max(demand_per_competitor, 1)) - 2) / 3 + m.demand_growth
    market_gap = clamp(gap)

    # Money at risk before break-even: upfront plus the deepest cash dip
    cash, low = -m.upfront_investment, -m.upfront_investment
    for y in years:
        cash += y.profit
        low = min(low, cash)
    funding_gap = max(0.0, -low - m.budget)

    invested = m.upfront_investment + m.fixed_costs_per_year
    return MarketAnalysis(
        optimal_price=price,
        price_vs_wtp=price / m.willingness_to_pay if m.willingness_to_pay else 0.0,
        years=years,
        total_revenue=total_revenue,
        total_profit=total_profit,
        roi=total_profit / invested if invested else 0.0,
        gross_margin=gross_margin,
        ltv=ltv,
        ltv_to_cac=ltv_to_cac,
        break_even_month=_break_even_month(idea, years),
        market_gap=market_gap,
        demand_per_competitor=demand_per_competitor,
        funding_gap=funding_gap,
    )
