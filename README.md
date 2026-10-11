# ReFrame: idea lab

ReFrame helps you **write down ideas, find out which ones can make money, and follow a
step-by-step plan to build them**. It has its own AI that scores every idea, explains
**what works and what doesn't**, and **learns from real results** each time you
record whether a project succeeded or failed.

```
reframe demo        # load 4 example ideas
reframe rank        # which idea is most likely to succeed and make the most profit?
reframe analyze 1   # market, pricing, profit, strengths, risks, what-if experiments
reframe plan 1      # step-by-step build plan with commands and starter code
reframe serve       # the same, as a web app at http://127.0.0.1:8765
```

## How it works

```
 your idea + market inputs
          │
          ▼
 ┌──────────────────────┐   optimal price, customers, revenue, profit,
 │ Supply & demand model│── break-even, LTV/CAC, market gap, funding gap
 └──────────────────────┘
          │ features
          ▼
 ┌──────────────────────┐   success score, what works / what doesn't,
 │ ReFrame AI (learns)  │── what-if experiments
 └──────────────────────┘
          │                  ▲
          ▼                  │ record real outcomes → retrain
 ┌──────────────────────┐    │
 │ Step-by-step planner │── Validate → Fix risks → Build MVP → Launch → Grow
 └──────────────────────┘
```

### 1. Supply & demand model (`reframe/market.py`)
- **Demand:** your *willingness to pay* input is treated as the median price buyers accept.
  Price sensitivity (elasticity) controls how fast buyers drop off as the price goes up.
- **Supply:** your share of the market shrinks with every competitor and grows with
  differentiation. A new entrant realistically wins a small part (10%) of its "fair share".
- **Growth & adoption:** the market grows every year and your adoption ramps up over three years.
- **Pricing:** ReFrame searches for the price that **maximizes 3-year profit**. This is
  the price used in the plan.
- **Outputs:** customers, revenue, costs and profit per year, ROI, break-even month,
  gross margin, LTV/CAC, buyers per competitor, and how much funding you're short.

### 2. ReFrame AI (`reframe/brain.py`)
An interpretable logistic-regression model over 12 features (market gap, growth,
competition, differentiation, margin, LTV/CAC, profit, time to break even,
complexity, skill fit, funding, recurring revenue).

- It **starts from built-in priors**, common startup knowledge about what tends to work.
- When you run `reframe outcome <id> success|failure`, it **retrains** on every recorded
  outcome. It is regularized toward the priors so a handful of results can't make it
  overconfident.
- Every score is **fully explained**: each factor's exact contribution, plus advice on
  the biggest risks.
- **What-if experiments** re-run the whole analysis with changes you control (sharper
  differentiation, cheaper acquisition, a niche market, lower churn…) and rank them by impact.
- `reframe insights` shows what the model has learned and how well it explains your history.

### 3. Step-by-step planner (`reframe/planner.py`)
Plans adapt to the idea's category (`saas`, `mobile_app`, `ecommerce`, `marketplace`,
`content`, `physical_product`, `service`, `api`) and to the analysis:

1. **Validate demand:** customer interviews and a ready-to-deploy smoke-test landing page.
2. **Fix the biggest risks:** steps added only for the risks the AI flagged.
3. **Build the MVP:** concrete commands and starter code (FastAPI, Expo/React Native,
   Stripe checkout, marketplace SQL schema, API-key metering…).
4. **Launch:** at the model's optimal price.
5. **Measure & grow:** track against the projection and feed results back to the AI.

Each step has *why*, a checklist, and a *done when* condition. `reframe plan 1 --out plan.md`
writes it as a Markdown checklist. In the web app you can tick steps off.

### 4. Optional: Claude for brainstorming and expert review (`reframe/llm.py`)
ReFrame's scoring and learning run fully offline. If you install the `ai` extra and set
`ANTHROPIC_API_KEY`, you can also use Claude:

```
pip install -e ".[ai]"
reframe brainstorm "tools for independent restaurants" --count 5 --save
reframe review 1   # hidden risks, opportunities, questions to validate, suspicious inputs
```

Brainstormed ideas come with estimated market inputs and go through the same analysis.
Requests use the server-side refusal fallback (`fallbacks: "default"`).

## Install

Requires Python 3.10+. The core has no dependencies.

```
pip install -e .          # or: pip install -e ".[ai,dev]"
reframe --help
```

Data is stored in `~/.reframe` (SQLite plus the trained model). Set `REFRAME_HOME` or
`--home` to use another folder.

## Adding your own ideas

Interactive: `reframe new "My idea"`, which asks for each market input with a sensible default.

From a file: `reframe new --file ideas.json`. See `reframe/examples.json` for the format.

Change an input and re-analyze: `reframe edit 1 --set competitors=3 --set unit_cost=2.5`

| Input | Meaning |
|---|---|
| `potential_customers` | people/businesses with the problem in your target market |
| `demand_growth` | yearly market growth (0.1 = 10%) |
| `willingness_to_pay` | median price per purchase buyers accept |
| `price_elasticity` | 0.5 = not price-sensitive … 3 = very price-sensitive |
| `purchases_per_year` | 12 for a monthly subscription, 1 for a one-off |
| `yearly_churn` | share of paying customers lost per year |
| `competitors` | direct alternatives buyers use today |
| `differentiation` | 0–1, how clearly better/different you are |
| `unit_cost` | variable cost per purchase |
| `customer_acquisition_cost` | cost to win one customer |
| `fixed_costs_per_year`, `upfront_investment`, `budget` | money in $ |
| `build_complexity`, `skill_fit` | 0–1 |

## Honest limits

ReFrame's numbers are only as good as its inputs. The model is a transparent
simplification, not a guarantee of profit. Use it to compare ideas, find the weak
spots, and decide what to validate next. Then replace the guesses with real data from
interviews, smoke tests and early sales. The more outcomes you record, the more the AI
reflects what actually works for you.

## Development

```
pip install -e ".[dev]"
pytest
```
