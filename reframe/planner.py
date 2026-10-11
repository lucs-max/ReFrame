"""Step-by-step build plans.

A plan is made of phases (Validate → Design → Build → Launch → Grow). The
Build phase depends on the idea's category and includes concrete commands
and starter code. Extra steps are inserted to address the specific risks
the analysis found, and the pricing step uses the analysis' optimal price.
"""

from __future__ import annotations

import html
from dataclasses import asdict, dataclass, field

from .analyzer import Analysis
from .models import Idea


@dataclass
class Step:
    title: str
    why: str
    actions: list[str]
    done_when: str
    code: str | None = None
    code_language: str | None = None


@dataclass
class Phase:
    name: str
    goal: str
    steps: list[Step] = field(default_factory=list)


@dataclass
class BuildPlan:
    idea_title: str
    category: str
    stack: list[str]
    score: float
    verdict: str
    phases: list[Phase]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [f"# Build plan: {self.idea_title}", "",
                 f"**Category:** {self.category}  ", f"**Suggested stack:** {', '.join(self.stack)}  ",
                 f"**ReFrame success score:** {self.score:.0%} ({self.verdict})", ""]
        if self.score < 0.35:
            lines += ["> ⚠️ ReFrame rates this idea unlikely to work as-is. Do Phases 1–2 and re-run",
                      "> the analysis before investing in the build.", ""]
        n = 0
        for phase in self.phases:
            lines += [f"## {phase.name}", f"_{phase.goal}_", ""]
            for step in phase.steps:
                n += 1
                lines += [f"### Step {n}: {step.title}", "", f"**Why:** {step.why}", ""]
                lines += [f"- [ ] {a}" for a in step.actions]
                if step.code:
                    lines += ["", f"```{step.code_language or ''}", step.code.strip(), "```"]
                lines += ["", f"**Done when:** {step.done_when}", ""]
        return "\n".join(lines)


STACKS = {
    "saas": ["Python + FastAPI", "PostgreSQL", "React or HTMX front end", "Stripe Billing", "Render / Fly.io"],
    "mobile_app": ["React Native (Expo)", "Supabase (auth + database)", "RevenueCat for in-app purchases"],
    "ecommerce": ["Shopify or WooCommerce", "Stripe", "Klaviyo for email", "Meta / Google ads"],
    "marketplace": ["Next.js", "PostgreSQL", "Stripe Connect for payouts", "Algolia or Postgres search"],
    "content": ["Ghost or Substack", "YouTube / podcast host", "Stripe or Memberful for memberships"],
    "physical_product": ["CAD (Fusion 360)", "Alibaba / local manufacturer", "Shopify", "ShipBob / 3PL"],
    "service": ["Website (Webflow / Carrd)", "Cal.com booking", "Stripe invoicing", "CRM (HubSpot free)"],
    "api": ["Python + FastAPI", "PostgreSQL + Redis", "API keys + usage metering", "Stripe metered billing"],
}

FASTAPI_STARTER = '''
# app.py — run with:  pip install fastapi uvicorn  &&  uvicorn app:app --reload
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="{title}")
items: dict[int, dict] = {{}}

class Item(BaseModel):
    name: str
    notes: str = ""

@app.post("/items")
def create_item(item: Item):
    item_id = len(items) + 1
    items[item_id] = item.model_dump()
    return {{"id": item_id, **items[item_id]}}

@app.get("/items/{{item_id}}")
def read_item(item_id: int):
    if item_id not in items:
        raise HTTPException(404, "not found")
    return items[item_id]
'''

API_KEY_STARTER = '''
# Require an API key and count usage per key (swap the dicts for Postgres/Redis).
from fastapi import Depends, FastAPI, Header, HTTPException

app = FastAPI()
API_KEYS = {"demo-key": "customer_1"}
usage: dict[str, int] = {}

def customer(x_api_key: str = Header(...)) -> str:
    if x_api_key not in API_KEYS:
        raise HTTPException(401, "invalid API key")
    cid = API_KEYS[x_api_key]
    usage[cid] = usage.get(cid, 0) + 1   # report this to Stripe metered billing
    return cid

@app.get("/v1/result")
def result(q: str, cid: str = Depends(customer)):
    return {"query": q, "customer": cid, "calls_this_period": usage[cid]}
'''

EXPO_STARTER = '''
// App.tsx — create with:  npx create-expo-app@latest __SLUG__  &&  npx expo start
import { useState } from "react";
import { Button, FlatList, Text, TextInput, View } from "react-native";

export default function App() {
  const [text, setText] = useState("");
  const [items, setItems] = useState<string[]>([]);
  return (
    <View style={{ padding: 24, marginTop: 48, gap: 12 }}>
      <Text style={{ fontSize: 24, fontWeight: "600" }}>__TITLE__</Text>
      <TextInput value={text} onChangeText={setText} placeholder="Add..."
                 style={{ borderWidth: 1, padding: 8, borderRadius: 6 }} />
      <Button title="Add" onPress={() => { if (text) { setItems([text, ...items]); setText(""); } }} />
      <FlatList data={items} keyExtractor={(_, i) => String(i)}
                renderItem={({ item }) => <Text>• {item}</Text>} />
    </View>
  );
}
'''

STRIPE_CHECKOUT = '''
# pip install stripe  — create a Product/Price in the Stripe dashboard first.
import os, stripe
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]

def checkout_url(price_id: str, customer_email: str) -> str:
    session = stripe.checkout.Session.create(
        mode="{mode}",
        line_items=[{{"price": price_id, "quantity": 1}}],
        customer_email=customer_email,
        success_url="https://yourapp.com/success",
        cancel_url="https://yourapp.com/pricing",
    )
    return session.url
'''

MARKETPLACE_SCHEMA = '''
-- Core marketplace tables (PostgreSQL)
CREATE TABLE users    (id SERIAL PRIMARY KEY, email TEXT UNIQUE NOT NULL, role TEXT CHECK (role IN ('buyer','seller')));
CREATE TABLE listings (id SERIAL PRIMARY KEY, seller_id INT REFERENCES users(id), title TEXT, price_cents INT, active BOOL DEFAULT true);
CREATE TABLE orders   (id SERIAL PRIMARY KEY, listing_id INT REFERENCES listings(id), buyer_id INT REFERENCES users(id),
                       amount_cents INT, fee_cents INT, status TEXT DEFAULT 'pending', created_at TIMESTAMPTZ DEFAULT now());
'''

LANDING_PAGE = '''
<!-- index.html — a one-page "smoke test" to measure real demand before building -->
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head>
<body style="font-family:system-ui;max-width:640px;margin:64px auto;padding:0 16px">
  <h1>{title}</h1>
  <p>{pitch}</p>
  <form action="https://formspree.io/f/YOUR_FORM_ID" method="POST">
    <input type="email" name="email" placeholder="you@example.com" required>
    <button>Get early access — ${price}</button>
  </form>
</body></html>
'''


def _fmt(template: str, **kw: object) -> str:
    return template.format(**kw)


def _validate_phase(idea: Idea, analysis: Analysis) -> Phase:
    price = analysis.market.optimal_price
    pitch = html.escape(idea.description or idea.title)
    return Phase("Phase 1 — Validate demand", "Prove people will pay before you build.", [
        Step("Interview 10–15 potential customers",
             "Confirms the problem is real and painful, and what buyers use today (your real competition).",
             ["List 30 people who have the problem; reach out on LinkedIn, Reddit, forums or in person",
              "Ask about the last time they hit the problem, what they did, and what it cost them",
              "Don't pitch. Record exact quotes in a spreadsheet",
              "Update ReFrame's market inputs (competitors, willingness to pay) with what you learn"],
             "At least 6 people describe the problem unprompted and say what they pay to solve it today."),
        Step("Launch a smoke-test landing page",
             "Measures real intent (emails, pre-orders) instead of opinions.",
             ["Create the page below and deploy it free (Netlify / GitHub Pages / Carrd)",
              f"Show the price ReFrame suggests (${price:,.2f}) so signups mean willingness to pay",
              "Drive 300–500 visitors with a small ad budget or community posts",
              "Track visit → signup conversion"],
             "Conversion ≥ 5% from targeted traffic, or at least 5 pre-orders.",
             _fmt(LANDING_PAGE, title=html.escape(idea.title), pitch=pitch, price=f"{price:,.2f}"), "html"),
    ])


def _build_steps(idea: Idea, analysis: Analysis) -> list[Step]:
    c, t = idea.category, idea.title
    slug = "".join(ch if ch.isalnum() else "-" for ch in t.lower()).strip("-") or "app"
    mode = "subscription" if idea.recurring_revenue else "payment"
    pay = Step("Take payments",
               "Revenue is the only real validation; charge from day one.",
               ["Create a Stripe account and a product at the suggested price",
                "Add a checkout link to the app or landing page",
                "Test with a real card, then refund yourself"],
               "A stranger has paid you.",
               _fmt(STRIPE_CHECKOUT, mode=mode), "python")
    if c == "saas":
        return [
            Step("Scaffold the backend", "A working API is the core of the product.",
                 ["Install Python 3.11+", "Create the project and virtual env: `python -m venv .venv`",
                  "Save the starter below as app.py and run it", "Open http://127.0.0.1:8000/docs to try it"],
                 "You can create and read records from the browser.",
                 _fmt(FASTAPI_STARTER, title=t), "python"),
            Step("Add a database and user accounts", "Customers need to log in and keep their data.",
                 ["Create a Postgres database (Supabase/Neon free tier)", "Use SQLModel or SQLAlchemy for tables",
                  "Add auth (Supabase Auth, Clerk, or fastapi-users)"],
                 "Two users each see only their own data."),
            Step("Build the one core screen", "The MVP is the single workflow that solves the problem.",
                 ["Sketch the screen on paper first", "Build it with React (Vite) or server-rendered HTMX",
                  "Cut every feature that is not needed for that one workflow"],
                 "An interviewee completes the core task without help."),
            pay,
            Step("Deploy", "Real users need a real URL.",
                 ["Push to GitHub", "Deploy on Render or Fly.io; add your env vars",
                  "Point a domain at it and turn on HTTPS"],
                 "The app is live at your domain."),
        ]
    if c == "api":
        return [
            Step("Scaffold the API", "The API itself is the product.",
                 ["Save the starter as app.py", "`pip install fastapi uvicorn` then `uvicorn app:app --reload`"],
                 "`curl -H 'x-api-key: demo-key' 'localhost:8000/v1/result?q=test'` returns JSON.",
                 _fmt(FASTAPI_STARTER, title=t), "python"),
            Step("Add API keys and usage metering", "You bill per call, so you must count calls.",
                 ["Issue keys per customer", "Count usage per key and per billing period",
                  "Add rate limits (slowapi) so one customer can't take the service down"],
                 "Calls without a valid key are rejected and usage is counted.",
                 API_KEY_STARTER, "python"),
            Step("Write docs and a quickstart", "Developers buy what they can try in 5 minutes.",
                 ["FastAPI generates OpenAPI docs at /docs", "Write a 3-step quickstart with curl and Python examples"],
                 "A developer friend makes a successful call in under 5 minutes."),
            pay,
        ]
    if c == "mobile_app":
        return [
            Step("Create the app", "Expo lets you run on a real phone in minutes.",
                 ["Install Node.js LTS", f"`npx create-expo-app@latest {slug}`",
                  "Replace App.tsx with the starter below", "`npx expo start` and scan the QR code with Expo Go"],
                 "The app runs on your phone.",
                 EXPO_STARTER.replace("__TITLE__", t).replace("__SLUG__", slug), "tsx"),
            Step("Add accounts and a backend", "Data must survive reinstalling the app.",
                 ["Create a Supabase project", "`npx expo install @supabase/supabase-js`",
                  "Add email or Apple/Google sign-in", "Store the core data in a Supabase table"],
                 "Data is still there after reinstalling."),
            Step("Add in-app purchases", "App stores require their own billing for digital goods.",
                 ["Set up RevenueCat with App Store Connect and Google Play Console",
                  "Create a paywall for the premium feature", "Test with sandbox accounts"],
                 "A sandbox purchase unlocks the premium feature."),
            Step("Ship to the stores", "Store review takes days; start early.",
                 ["`npx eas build` for iOS and Android", "Prepare screenshots, description and privacy policy",
                  "Submit with `npx eas submit`; start with TestFlight / internal testing"],
                 "The app is approved in at least one store."),
        ]
    if c == "marketplace":
        return [
            Step("Do it manually first (concierge MVP)", "Marketplaces fail on liquidity, not software.",
                 ["Recruit 10–20 sellers by hand", "Match buyers to sellers yourself via a form + email/WhatsApp",
                  "Take your fee manually via invoice"],
                 "10 transactions completed with you as the matchmaker."),
            Step("Model the data", "Listings, orders and fees are the core of any marketplace.",
                 ["Create a Postgres database", "Run the schema below", "Build list/search pages with Next.js"],
                 "Sellers can create listings and buyers can browse them.",
                 MARKETPLACE_SCHEMA, "sql"),
            Step("Add payments with payouts", "You need to collect from buyers and pay sellers.",
                 ["Use Stripe Connect (Express accounts) for seller onboarding",
                  "Charge the buyer, keep your fee with `application_fee_amount`, transfer the rest"],
                 "A test order pays out to a test seller minus your fee."),
            Step("Build trust", "Strangers need a reason to transact.",
                 ["Reviews after each order", "Verified seller badges", "A clear refund policy"],
                 "Repeat purchase rate is measurable."),
        ]
    if c == "ecommerce":
        return [
            Step("Source and test the product", "Margins depend on supplier price and quality.",
                 ["Order samples from 3 suppliers", "Compare quality, unit cost and shipping time",
                  f"Confirm landed unit cost is near your input (${idea.market.unit_cost:,.2f})"],
                 "You have a supplier, a sample you'd buy yourself, and a confirmed unit cost."),
            Step("Build the store", "A clean store converts; you don't need custom code.",
                 ["Start a Shopify store (or WooCommerce)", "Write benefit-focused product pages with real photos",
                  "Set shipping rules, taxes and a returns policy"],
                 "You can place a test order end to end."),
            Step("Set up email capture", "Most e-commerce revenue comes from returning customers.",
                 ["Connect Klaviyo", "Create a welcome flow and an abandoned-cart flow"],
                 "Both flows trigger on a test account."),
        ]
    if c == "physical_product":
        return [
            Step("Prototype", "You need something people can hold.",
                 ["Sketch, then model in Fusion 360", "3D print or hand-build 2–3 versions",
                  "Test with 5 interviewees and iterate"],
                 "Testers use it without explanation."),
            Step("Design for manufacturing", "Cost and defects are set at design time.",
                 ["Get quotes from 3 manufacturers (MOQ, unit cost, lead time)",
                  "Order a pre-production sample", "Check certifications needed (CE, FCC, food-safe...)"],
                 f"Quoted unit cost ≤ ${idea.market.unit_cost:,.2f} at your first order size."),
            Step("Pre-sell before the first production run", "Pre-orders fund inventory and prove demand.",
                 ["Run a Kickstarter or a Shopify pre-order page", "Set a pre-order goal that covers the MOQ"],
                 "Pre-orders cover the first production run."),
            Step("Logistics", "Fulfilment mistakes kill reviews.",
                 ["Choose a 3PL or ship yourself at first", "Set up packaging, labels and returns"],
                 "A test shipment arrives intact."),
        ]
    if c == "content":
        return [
            Step("Pick the format and publish 10 pieces", "Consistency beats perfection in content.",
                 ["Choose one platform where your audience already is", "Batch-create 10 pieces",
                  "Publish on a fixed schedule"],
                 "10 pieces published; you know which 2 perform best."),
            Step("Build the email list", "You own your list; you don't own social followers.",
                 ["Set up Ghost/Substack/ConvertKit", "Add a free lead magnet", "Link it from every piece"],
                 "100 subscribers."),
            Step("Add the paid tier", "Monetize the most engaged readers.",
                 ["Offer premium posts, a community, or a course", "Connect Stripe/Memberful"],
                 "First 10 paying members."),
        ]
    # service
    return [
        Step("Package the service", "Productized offers sell faster than hourly work.",
             ["Define one offer with a fixed scope, timeline and price", "Write the deliverables checklist"],
             "You can explain the offer in one sentence."),
        Step("Set up the business basics", "Look credible and get paid on time.",
             ["One-page website with the offer and testimonials", "Cal.com booking link",
              "Stripe invoicing and a simple contract template"],
             "A prospect can book and pay without emailing you."),
        Step("Land the first 3 clients", "Early clients become case studies.",
             ["Contact your network and interviewees", "Offer a launch discount in exchange for a testimonial"],
             "3 paying clients and 2 testimonials."),
    ]


RISK_STEPS = {
    "differentiation": Step(
        "Differentiation sprint", "The analysis shows buyers may not see why you're different.",
        ["List the top 5 competitors and what reviewers complain about (G2, App Store, Amazon reviews)",
         "Pick the one complaint you'll solve best and make it your headline",
         "Re-test the landing page with the new headline"],
        "Interviewees can repeat your difference back to you."),
    "unit_economics": Step(
        "Fix unit economics", "Acquiring a customer currently costs too much relative to their value.",
        ["Test 3 cheap channels: SEO content, communities, partnerships/referrals",
         "Add an annual plan or bundle to raise customer value",
         "Measure real CAC per channel and drop the expensive ones"],
        "LTV / CAC ≥ 3 on at least one channel."),
    "competition": Step(
        "Pick a beachhead niche", "The market is crowded; win a small segment first.",
        ["Segment the market by industry, region or use case", "Choose the segment competitors serve worst",
         "Re-run ReFrame with that segment's numbers"],
        "ReFrame's competition and market-gap scores improve for the niche."),
    "funding": Step(
        "Close the funding gap", "Projected cash needs exceed your budget.",
        ["Pre-sell or take deposits", "Cut fixed costs (no office, no-code tools, part-time contractors)",
         "If still short: small grants, a friends-and-family round, or revenue-based financing"],
        "Committed cash covers the projected cash dip."),
    "gross_margin": Step(
        "Raise gross margin", "Each sale leaves too little money to cover other costs.",
        ["Renegotiate supplier or hosting costs", "Remove expensive features from the base tier",
         "Add a premium tier"], "Gross margin ≥ 50% (≥ 70% for software)."),
    "build_complexity": Step(
        "Cut scope", "The build is complex; complexity delays revenue.",
        ["Write the single job the product must do", "Replace custom parts with off-the-shelf/no-code tools",
         "Move everything else to a 'later' list"], "MVP can ship in 4–6 weeks."),
    "skill_fit": Step(
        "Cover your skills gap", "You're missing skills the build needs.",
        ["List required skills and mark the ones you lack", "Find a co-founder, freelancer, or no-code tool for each"],
        "Every required skill has an owner."),
    "market_gap": Step(
        "Find more demand per competitor", "There are few buyers per competitor.",
        ["Look for an adjacent customer segment or geography", "Check search trends and community size"],
        "You've identified a segment with more buyers per competitor."),
}


def build_plan(idea: Idea, analysis: Analysis) -> BuildPlan:
    m = analysis.market
    phases = [_validate_phase(idea, analysis)]

    fixes = [RISK_STEPS[r["feature"]] for r in analysis.risks if r["feature"] in RISK_STEPS]
    if fixes:
        phases.append(Phase("Phase 2 — Fix the biggest risks",
                            "ReFrame's AI flagged these as the main reasons this could fail.", fixes))

    phases.append(Phase(f"Phase {len(phases) + 1} — Build the MVP",
                        "Build the smallest thing customers will pay for.", _build_steps(idea, analysis)))

    phases.append(Phase(f"Phase {len(phases) + 1} — Launch", "Get the first paying customers.", [
        Step("Set the launch price",
             "ReFrame's supply/demand model found the price that maximizes 3-year profit.",
             [f"Launch at ${m.optimal_price:,.2f} ({m.price_vs_wtp:.0%} of buyers' typical willingness to pay)",
              "Offer an early-bird discount with a deadline to create urgency",
              "Re-run ReFrame after 50 sales with real conversion data"],
             "Pricing page is live."),
        Step("Launch publicly", "Concentrated attention gives you your first users and feedback.",
             ["Email everyone from the smoke test", "Post on Product Hunt / relevant subreddits / LinkedIn",
              "Personally onboard the first 20 customers"],
             "First 10 paying customers."),
    ]))

    phases.append(Phase(f"Phase {len(phases) + 1} — Measure & grow",
                        "Let the numbers tell you what works.", [
        Step("Track the metrics that matter", "You can't improve what you don't measure.",
             ["Weekly: revenue, new customers, CAC per channel, churn, gross margin",
              "Compare against ReFrame's projection: "
              f"year 1 revenue ${m.years[0].revenue:,.0f}, profit ${m.years[0].profit:,.0f}"],
             "A weekly dashboard exists."),
        Step("Feed results back into ReFrame", "This is how ReFrame's AI learns what works.",
             ["Update the idea's market inputs with real numbers and re-analyze",
              "When the project clearly succeeds or fails, record it: `reframe outcome <id> success|failure`"],
             "The outcome is recorded and the model retrained."),
    ]))

    return BuildPlan(idea.title, idea.category, STACKS[idea.category], analysis.score,
                     analysis.verdict, phases)
