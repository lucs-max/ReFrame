"""Offline expert review: rule-based checks plus a sensitivity analysis.

Gives the same kind of review as the Claude reviewer (summary, hidden risks,
opportunities, questions to validate, inputs to double-check) without any
API. The sensitivity analysis re-runs the market model with each input 20%
worse, so you learn which of your guesses the profit depends on most.
"""

from __future__ import annotations

import copy

from .analyzer import Analysis
from .market import analyze_market
from .models import Idea

# input -> (label, direction that is "worse": -1 lower is worse, +1 higher is worse)
SENSITIVE_INPUTS = {
    "potential_customers": ("Market size", -1),
    "willingness_to_pay": ("Willingness to pay", -1),
    "differentiation": ("Differentiation", -1),
    "competitors": ("Number of competitors", +1),
    "customer_acquisition_cost": ("Customer acquisition cost", +1),
    "unit_cost": ("Unit cost", +1),
    "yearly_churn": ("Churn", +1),
    "fixed_costs_per_year": ("Fixed costs", +1),
    "demand_growth": ("Market growth", -1),
}

QUESTIONS = {
    "potential_customers": "How many buyers really have this problem? Count them in a directory, "
                           "LinkedIn search or industry report.",
    "willingness_to_pay": "What do buyers pay today for their current solution? Ask in interviews "
                          "and test the price on a landing page.",
    "differentiation": "Can 5 interviewees explain in one sentence why you're better than "
                       "what they use now?",
    "competitors": "List every alternative, including spreadsheets and doing nothing. Is the "
                   "competitor count right?",
    "customer_acquisition_cost": "Run a $100–200 ad or outreach test. What does one paying "
                                 "customer really cost?",
    "unit_cost": "Get real quotes from suppliers or hosting providers for your unit cost.",
    "yearly_churn": "How long do customers keep paying for similar products? Check competitor "
                    "reviews and forums.",
    "fixed_costs_per_year": "List every monthly tool, salary and rent cost. Are fixed costs complete?",
    "demand_growth": "Is the market growing? Check search trends and industry reports.",
}


def sensitivity(idea: Idea, base_profit: float) -> list[dict]:
    rows = []
    for field, (label, worse) in SENSITIVE_INPUTS.items():
        variant = copy.deepcopy(idea)
        value = getattr(variant.market, field)
        if field == "competitors":
            new = max(value + 1, round(value * 1.2))
        else:
            new = value * (1 + 0.2 * worse)
        if field == "differentiation":
            new = max(0.0, min(1.0, new))
        setattr(variant.market, field, type(value)(new))
        loss = base_profit - analyze_market(variant).total_profit
        rows.append({"field": field, "label": label, "profit_loss": loss})
    return sorted(rows, key=lambda r: r["profit_loss"], reverse=True)


def offline_review(idea: Idea, analysis: Analysis) -> dict:
    m, mk = idea.market, analysis.market
    risks, opportunities, suspicious = [], [], []

    if mk.ltv_to_cac < 1:
        risks.append(f"Each customer is worth ${mk.ltv:,.0f} but costs ${m.customer_acquisition_cost:,.0f} "
                     "to win: you lose money on every sale until this flips.")
    elif mk.ltv_to_cac < 3:
        risks.append(f"LTV/CAC is {mk.ltv_to_cac:.1f}x (healthy is 3x+): little room if ads get pricier.")
    if mk.break_even_month is None:
        risks.append("The model doesn't break even within 3 years.")
    elif mk.break_even_month > 18:
        risks.append(f"Break-even takes {mk.break_even_month} months; you need enough cash to last that long.")
    if mk.funding_gap > 0:
        risks.append(f"You'd need about ${mk.funding_gap:,.0f} more than your budget before the cash dip ends.")
    if idea.recurring_revenue and m.yearly_churn >= 0.5:
        risks.append(f"High churn ({m.yearly_churn:.0%}/year): you must keep replacing half your customers.")
    if mk.gross_margin < 0.4:
        risks.append(f"Gross margin is only {mk.gross_margin:.0%}, so growth needs a lot of cash.")
    if m.competitors >= 30:
        risks.append(f"{m.competitors} competitors: expect price pressure and expensive ads.")
    if m.build_complexity >= 0.7 and m.skill_fit <= 0.4:
        risks.append("A hard build plus a skills gap often means delays; budget for help.")
    for r in analysis.risks:
        if not any(r["label"].lower() in x.lower() for x in risks):
            risks.append(f"{r['label']}: {r['advice']}")

    for e in analysis.experiments:
        if e.profit_change > 0 and len(opportunities) < 3:
            opportunities.append(f"{e.name}: about ${e.profit_change:,.0f} more 3-year profit.")
    if not idea.recurring_revenue:
        opportunities.append("Add recurring revenue (subscription, refills, service plan) to raise customer value.")
    if mk.price_vs_wtp < 0.8:
        opportunities.append("The best price is well below willingness to pay. A premium tier could "
                             "capture buyers who'd pay more.")
    if mk.market_gap >= 0.7:
        opportunities.append("Lots of buyers per competitor: the market looks under-supplied.")

    if m.competitors == 0:
        suspicious.append("Zero competitors is rare. It can mean no one will pay. Include indirect "
                          "alternatives (spreadsheets, doing nothing).")
    if m.differentiation >= 0.8:
        suspicious.append(f"Differentiation {m.differentiation:.1f} is very high. Have customers confirmed it?")
    if idea.recurring_revenue and m.yearly_churn < 0.15:
        suspicious.append(f"Churn of {m.yearly_churn:.0%}/year is unusually low for a new product.")
    if m.customer_acquisition_cost < 10:
        suspicious.append(f"An acquisition cost of ${m.customer_acquisition_cost:,.0f} is very optimistic.")
    if m.demand_growth > 0.3:
        suspicious.append(f"{m.demand_growth:.0%} yearly market growth is exceptional. Check the source.")
    if m.unit_cost >= m.willingness_to_pay:
        suspicious.append("Unit cost is at or above what buyers pay: the product can't be profitable as-is.")
    if m.potential_customers >= 5_000_000:
        suspicious.append(f"{m.potential_customers:,} potential customers is a whole mass market; "
                          "a narrower first segment is more realistic.")

    sens = sensitivity(idea, mk.total_profit)
    questions = [f"{QUESTIONS[r['field']]} (A 20% error here changes 3-year profit by "
                 f"${abs(r['profit_loss']):,.0f}.)" for r in sens[:3] if r["profit_loss"] > 0]

    be = f"breaks even in month {mk.break_even_month}" if mk.break_even_month else "doesn't break even in 3 years"
    summary = (f"{idea.title} scores {analysis.score:.0%} ({analysis.verdict.lower()}). At the "
               f"profit-maximizing price of ${mk.optimal_price:,.2f} it projects "
               f"${mk.total_profit:,.0f} profit over 3 years and {be}. "
               f"The profit depends most on {sens[0]['label'].lower()}"
               + (f" and {sens[1]['label'].lower()}" if len(sens) > 1 else "")
               + ", so validate those first.")
    return {"summary": summary, "hidden_risks": risks or ["No major red flags in the numbers."],
            "opportunities": opportunities, "questions_to_validate": questions,
            "suspicious_inputs": suspicious or ["No inputs look unusual."],
            "sensitivity": sens, "source": "offline"}
