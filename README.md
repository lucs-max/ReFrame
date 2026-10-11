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

### 4. Live market data (`reframe/live.py`)
ReFrame checks your inputs against the live market using free public sources. It needs
internet but **no API keys and no Anthropic account**, so it works in offline mode too.

| Source | What it measures | Inputs it calibrates |
|---|---|---|
| Wikipedia page views (last 24 complete months) | interest in the topic and its year-over-year growth | market growth |
| Hacker News stories (this year vs last year) | discussion trend, strongest for tech topics | market growth |
| Apple App Store search | established competitors, their ratings and prices | competitors, willingness to pay (apps), differentiation room |
| GitHub search | open-source alternatives | competitors (software ideas) |

**The calibration algorithm.** Every signal proposes a value for an input, with a confidence
based on how much data backs it (more page views, more stories, more apps → higher
confidence). The suggestion is `current + confidence × (signal − current)`: thin evidence
nudges your number, strong evidence moves it most of the way. Your own knowledge isn't
thrown away, and one noisy reading can't swing the result.

**Consistency.** Fixed time windows (complete months, whole days), medians instead of
averages, and a 12-hour cache mean repeat scans give the same answer. A capped App Store
search (50 results) is treated as a minimum and never lowers your competitor count.

**Market pulse.** A 0–100% summary of the live data (growth up, saturation down, weak
competitor ratings = room to win), shown next to the idea's score.

```
reframe market --check        # test that every source is reachable from your computer
reframe market 1              # live signals + suggested input updates for idea #1
reframe market 1 --apply      # apply them (the scan and the new score are recorded)
reframe market --all --apply  # every idea
reframe watch --every 6       # re-scan all ideas every 6 hours (add --apply to auto-update)
reframe watch --once --apply  # one pass, for cron / Windows Task Scheduler
reframe history 1             # how the idea's score moved over time
reframe live off|on           # turn live data off/on (on by default)
```

With live data on, brainstormed ideas are calibrated automatically. Each idea has a
**market keywords** field (Inputs tab, or `reframe edit 1 --set keywords="dog grooming"`)
that sets what's searched. By default it's taken from the title. In the web app, use the
**Market** tab and the *Live market data* switch in the top bar.

Privacy: your keywords (not your numbers) are sent to Wikipedia, Hacker News (Algolia),
Apple and GitHub. Turn this off with `reframe live off`. GitHub allows about 10 searches a
minute without an account, so big `--all` scans may show a temporary rate-limit message.

These are *proxies* for supply and demand, not sales data. They make your numbers more
grounded and comparable, but customer interviews and real sales still beat any signal.

### 5. Two modes: offline (default) or Claude

| | **Offline mode** (default) | **Claude mode** |
|---|---|---|
| API key / internet | none needed; never contacts Anthropic | Anthropic API key with credit |
| Cost | free | paid per use |
| Brainstorm | business-model templates matched to your topic's audience (businesses vs consumers), ranked by ReFrame's AI | Claude invents ideas and estimates market numbers for your topic |
| Review | rule-based checks + sensitivity analysis (which inputs your profit depends on most) | Claude's written critique |
| Scoring, ranking, plans, learning | same in both modes (always offline) | same |

```
reframe mode            # show the current mode
reframe mode offline    # never use the Anthropic API (default)
reframe mode claude     # use Claude for brainstorm and review
reframe --offline ...   # force offline for one command, whatever the saved mode
```

Setting the environment variable `REFRAME_OFFLINE=1` locks ReFrame to offline mode. In the
web app, use the mode switch in the top bar.

```
reframe brainstorm "tools for small restaurants" --count 5 --save
reframe review 1   # hidden risks, opportunities, questions to validate, inputs to double-check
```

Offline brainstorm numbers are starting guesses for each business model, not research.
Replace them with real data (Inputs tab or `reframe edit`) and the scores and plans follow.

**Using Claude mode.** Install the `ai` extra, save an Anthropic API key (create one at
https://console.anthropic.com/settings/keys) and switch modes:

```
pip install -e ".[ai]"
reframe set-key     # paste your key once; it's saved in ~/.reframe on this computer only
reframe mode claude
```

The Claude API is paid per use and billed separately from a Claude.ai subscription. If you
see "credit balance is too low", add credit at https://console.anthropic.com/settings/billing
or go back to `reframe mode offline`. An `ANTHROPIC_API_KEY` environment variable, if set,
takes priority over the saved key. Remove the saved key with `reframe set-key --remove`.
Claude requests use the server-side refusal fallback (`fallbacks: "default"`).

## Install

Requires Python 3.9+. The core has no dependencies, and offline mode needs nothing else.

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
