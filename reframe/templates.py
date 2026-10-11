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

BUSINESS_WORDS = {
    "business", "businesses", "company", "companies", "restaurant", "restaurants", "clinic",
    "clinics", "dentist", "dentists", "lawyer", "lawyers", "agency", "agencies", "shop", "shops",
    "store", "stores", "salon", "salons", "contractor", "contractors", "farm", "farms", "school",
    "schools", "hotel", "hotels", "gym", "gyms", "startup", "startups", "b2b", "office", "offices",
    "retailer", "retailers", "landlord", "landlords", "accountant", "accountants", "freelancer",
    "freelancers", "plumber", "plumbers", "groomer", "groomers", "bakery", "bakeries", "cafe",
    "cafes", "studio", "studios", "warehouse", "warehouses", "manufacturer", "manufacturers",
    "realtor", "realtors", "doctor", "doctors", "therapist", "therapists", "coach", "coaches",
}
CONSUMER_WORDS = {
    "parent", "parents", "kid", "kids", "student", "students", "pet", "pets", "dog", "dogs", "cat",
    "cats", "gamer", "gamers", "gaming", "fitness", "travel", "travelers", "home", "homeowners",
    "people", "seniors", "teens", "families", "family", "hobby", "hobbyists", "cooking", "fans",
    "beginners", "women", "men", "couples", "music", "fashion", "beauty", "gardening", "runners",
}

# Market adjustments by audience (multipliers on customers and price)
AUDIENCE_ADJUST = {
    "business": dict(potential_customers=0.6, willingness_to_pay=1.6, customer_acquisition_cost=1.4),
    "consumer": dict(potential_customers=4.0, willingness_to_pay=0.4, customer_acquisition_cost=0.8),
    "any": {},
}


def detect_audience(topic: str) -> str:
    words = {w.strip(".,!?;:()\"'").lower() for w in topic.split()}
    b, c = len(words & BUSINESS_WORDS), len(words & CONSUMER_WORDS)
    if b > c:
        return "business"
    if c > b:
        return "consumer"
    return "any"


# (title, description, category, recurring, market overrides, audiences it fits)
TEMPLATES = [
    ("Scheduling & admin software for {t}",
     "A simple subscription tool that automates bookings, reminders and paperwork for {t}.",
     "saas", True,
     dict(potential_customers=50_000, willingness_to_pay=29, competitors=8, differentiation=0.5,
          unit_cost=3, customer_acquisition_cost=90, build_complexity=0.5), ("business",)),
    ("Marketplace connecting {t} with local freelancers",
     "Matches {t} with vetted local freelancers and takes a fee on each job.",
     "marketplace", False,
     dict(potential_customers=30_000, willingness_to_pay=150, purchases_per_year=4, competitors=4,
          differentiation=0.5, unit_cost=120, customer_acquisition_cost=60, build_complexity=0.6), ("any",)),
    ("Done-for-you marketing service for {t}",
     "A fixed-price monthly package that handles social media, reviews and ads for {t}.",
     "service", True,
     dict(potential_customers=20_000, willingness_to_pay=400, yearly_churn=0.4, competitors=25,
          differentiation=0.4, unit_cost=180, customer_acquisition_cost=300,
          fixed_costs_per_year=6_000, upfront_investment=1_500, build_complexity=0.2), ("business",)),
    ("Paid newsletter & course for {t}",
     "Practical weekly lessons and a premium course for {t}.",
     "content", True,
     dict(potential_customers=100_000, willingness_to_pay=10, yearly_churn=0.45, competitors=15,
          differentiation=0.45, unit_cost=0.5, customer_acquisition_cost=15,
          fixed_costs_per_year=3_000, upfront_investment=1_000, build_complexity=0.2), ("any",)),
    ("Customer mobile app for {t}",
     "A branded app for the customers of {t}: ordering, loyalty points and notifications.",
     "mobile_app", True,
     dict(potential_customers=40_000, willingness_to_pay=49, competitors=12, differentiation=0.45,
          unit_cost=5, customer_acquisition_cost=150, upfront_investment=12_000,
          build_complexity=0.65), ("business",)),
    ("Data & pricing API for {t}",
     "An API that gives software companies serving {t} clean, up-to-date data.",
     "api", True,
     dict(potential_customers=3_000, willingness_to_pay=99, competitors=3, differentiation=0.55,
          unit_cost=10, customer_acquisition_cost=250, build_complexity=0.6, skill_fit=0.4), ("business",)),
    ("Online store for {t} supplies",
     "A niche e-commerce store selling the supplies {t} reorder most often, with subscriptions.",
     "ecommerce", True,
     dict(potential_customers=60_000, willingness_to_pay=60, purchases_per_year=6, yearly_churn=0.5,
          competitors=30, differentiation=0.35, unit_cost=36, customer_acquisition_cost=35,
          upfront_investment=6_000, build_complexity=0.3), ("any",)),
    ("Physical product solving a daily problem in {t}",
     "A durable, well-designed product that fixes a frustrating everyday problem in {t}.",
     "physical_product", False,
     dict(potential_customers=80_000, willingness_to_pay=70, purchases_per_year=1, competitors=20,
          differentiation=0.5, unit_cost=25, customer_acquisition_cost=25,
          upfront_investment=15_000, build_complexity=0.6), ("any",)),
    ("Mobile app for {t}",
     "A simple, focused app that solves one everyday problem for {t}, with a premium subscription.",
     "mobile_app", True,
     dict(potential_customers=500_000, willingness_to_pay=6, yearly_churn=0.6, competitors=40,
          differentiation=0.45, unit_cost=0.6, customer_acquisition_cost=4,
          upfront_investment=8_000, build_complexity=0.55), ("consumer",)),
    ("Subscription box for {t}",
     "A curated monthly box of products {t} love, delivered to the door.",
     "ecommerce", True,
     dict(potential_customers=300_000, willingness_to_pay=35, yearly_churn=0.6, competitors=25,
          differentiation=0.45, unit_cost=20, customer_acquisition_cost=30,
          upfront_investment=5_000, build_complexity=0.3), ("consumer",)),
    ("Paid online community for {t}",
     "A members-only community with expert sessions, challenges and resources for {t}.",
     "content", True,
     dict(potential_customers=200_000, willingness_to_pay=12, yearly_churn=0.5, competitors=20,
          differentiation=0.5, unit_cost=1, customer_acquisition_cost=12,
          fixed_costs_per_year=4_000, upfront_investment=1_000, build_complexity=0.2), ("consumer",)),
    ("Local service business for {t}",
     "A trusted, bookable local service for {t}, starting in one neighborhood.",
     "service", True,
     dict(potential_customers=15_000, willingness_to_pay=60, purchases_per_year=6, yearly_churn=0.4,
          competitors=15, differentiation=0.45, unit_cost=30, customer_acquisition_cost=40,
          fixed_costs_per_year=5_000, upfront_investment=2_000, build_complexity=0.2), ("consumer",)),
]


def offline_brainstorm(topic: str, count: int = 5,
                       model: ViabilityModel | None = None) -> list[Idea]:
    """Apply the templates that fit the topic's audience and return the ``count`` best-rated."""
    topic = " ".join(topic.split()) or "small businesses"
    audience = detect_audience(topic)
    adjust = AUDIENCE_ADJUST[audience]
    ideas = []
    for title, desc, category, recurring, market, fits in TEMPLATES:
        if audience != "any" and audience not in fits and "any" not in fits:
            continue
        market = dict(market)
        if "any" in fits:
            for field, factor in adjust.items():
                market[field] = type(market.get(field, getattr(MarketInputs(), field)))(
                    market.get(field, getattr(MarketInputs(), field)) * factor)
        ideas.append(Idea(title.format(t=topic), desc.format(t=topic), category, recurring,
                          MarketInputs(**market), keywords=topic))
    scored = sorted(ideas, key=lambda i: analyze(i, model).score, reverse=True)
    return scored[:max(1, count)]
