"""Offline brainstorming: proven business-model templates applied to a topic.

No API key or internet needed. Each template is a common way to make money
around a topic, with starting market numbers typical for that model. The
numbers are placeholders, not research: ReFrame analyzes every template,
keeps the ones its AI rates best, and you should replace the numbers with
what you learn from real customers (``reframe edit`` or the Inputs tab).
"""

from __future__ import annotations

from .analyzer import analyze
from .brain import ViabilityModel
from .models import Idea, MarketInputs

# (title, description, category, recurring, market overrides)
TEMPLATES = [
    ("Scheduling & admin software for {t}",
     "A simple subscription tool that automates bookings, reminders and paperwork for {t}.",
     "saas", True,
     dict(potential_customers=50_000, willingness_to_pay=29, competitors=8, differentiation=0.5,
          unit_cost=3, customer_acquisition_cost=90, build_complexity=0.5)),
    ("Marketplace connecting {t} with local freelancers",
     "Matches {t} with vetted local freelancers and takes a fee on each job.",
     "marketplace", False,
     dict(potential_customers=30_000, willingness_to_pay=150, purchases_per_year=4, competitors=4,
          differentiation=0.5, unit_cost=120, customer_acquisition_cost=60, build_complexity=0.6)),
    ("Done-for-you marketing service for {t}",
     "A fixed-price monthly package that handles social media, reviews and ads for {t}.",
     "service", True,
     dict(potential_customers=20_000, willingness_to_pay=400, yearly_churn=0.4, competitors=25,
          differentiation=0.4, unit_cost=180, customer_acquisition_cost=300,
          fixed_costs_per_year=6_000, upfront_investment=1_500, build_complexity=0.2)),
    ("Paid newsletter & course about {t}",
     "Practical weekly lessons and a premium course for people working in {t}.",
     "content", True,
     dict(potential_customers=100_000, willingness_to_pay=10, yearly_churn=0.45, competitors=15,
          differentiation=0.45, unit_cost=0.5, customer_acquisition_cost=15,
          fixed_costs_per_year=3_000, upfront_investment=1_000, build_complexity=0.2)),
    ("Customer mobile app for {t}",
     "A branded app for the customers of {t}: ordering, loyalty points and notifications.",
     "mobile_app", True,
     dict(potential_customers=40_000, willingness_to_pay=49, competitors=12, differentiation=0.45,
          unit_cost=5, customer_acquisition_cost=150, upfront_investment=12_000,
          build_complexity=0.65)),
    ("Data & pricing API for {t}",
     "An API that gives software companies serving {t} clean, up-to-date data.",
     "api", True,
     dict(potential_customers=3_000, willingness_to_pay=99, competitors=3, differentiation=0.55,
          unit_cost=10, customer_acquisition_cost=250, build_complexity=0.6, skill_fit=0.4)),
    ("Online store for {t} supplies",
     "A niche e-commerce store selling the supplies {t} reorder most often, with subscriptions.",
     "ecommerce", True,
     dict(potential_customers=60_000, willingness_to_pay=60, purchases_per_year=6, yearly_churn=0.5,
          competitors=30, differentiation=0.35, unit_cost=36, customer_acquisition_cost=35,
          upfront_investment=6_000, build_complexity=0.3)),
    ("Physical product solving a daily problem in {t}",
     "A durable, well-designed product that fixes a frustrating everyday problem in {t}.",
     "physical_product", False,
     dict(potential_customers=80_000, willingness_to_pay=70, purchases_per_year=1, competitors=20,
          differentiation=0.5, unit_cost=25, customer_acquisition_cost=25,
          upfront_investment=15_000, build_complexity=0.6)),
]


def offline_brainstorm(topic: str, count: int = 5,
                       model: ViabilityModel | None = None) -> list[Idea]:
    """Apply every template to the topic and return the ``count`` best-rated ideas."""
    topic = " ".join(topic.split()) or "small businesses"
    ideas = []
    for title, desc, category, recurring, market in TEMPLATES:
        ideas.append(Idea(title.format(t=topic), desc.format(t=topic), category, recurring,
                          MarketInputs(**market)))
    scored = sorted(ideas, key=lambda i: analyze(i, model).score, reverse=True)
    return scored[:max(1, count)]
