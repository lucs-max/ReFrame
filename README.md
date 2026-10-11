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

### 5. Three modes: offline (default), local AI, or Claude

ReFrame's own AI (scoring, explanations, what-if experiments, learning from outcomes) and
the planner **always run on your PC**. The mode only decides who *writes* brainstormed
ideas and reviews:

| | **Offline** (default) | **Local AI** | **Claude** |
|---|---|---|---|
| Runs where | your PC, no AI model | a language model on **your PC** (Ollama or LM Studio) | Anthropic's cloud |
| Needs | nothing | a free local AI app + a model download (~2–5 GB) | API key with credit |
| Cost | free | free | paid per use |
| Your ideas leave your PC? | no | no | yes (sent to Anthropic) |
| Brainstorm | business-model templates matched to your topic | the local model invents ideas and estimates numbers | Claude invents ideas |
| Review | rule-based checks + sensitivity analysis | local model's critique + the same sensitivity analysis | Claude's critique |

```
reframe mode            # show the current mode
reframe mode offline    # built-in templates, no AI model (default)
reframe mode local      # language model on this PC
reframe mode claude     # Claude API
reframe --offline ...   # force offline for one command, whatever the saved mode
```

Setting the environment variable `REFRAME_OFFLINE=1` locks ReFrame to offline mode. In the
web app, use the mode menu in the top bar.

**Setting up Local AI (one time):**

1. Install **Ollama** from https://ollama.com (Windows, Mac, Linux). It runs in the background.
2. Download a model in a terminal: `ollama pull llama3.2` (about 2 GB, runs on most PCs).
   With 16 GB+ RAM or a graphics card, `ollama pull qwen2.5:7b` gives better ideas.
3. `reframe mode local`, then `reframe local` to check it's found.

Prefer **LM Studio** (https://lmstudio.ai)? Download a model, start its local server
(Developer tab → Start Server) and ReFrame finds it automatically at `localhost:1234`. Other
OpenAI-compatible local servers (llama.cpp `llama-server`, Jan, LocalAI) work too:

```
reframe local                                    # status, installed models
reframe local --model qwen2.5:7b                 # choose a model (default: auto-pick)
reframe local --provider openai --url http://localhost:8080/v1   # any compatible server
```

Local models are smaller than cloud models, so ReFrame checks every answer, repairs
common slips (extra text around the JSON, "15" meaning 15%, unknown categories), keeps
every number in a sensible range, and retries once if the reply is unusable. On a PC
without a graphics card, a brainstorm can take a minute or two.

```
reframe brainstorm "tools for small restaurants" --count 5 --save
reframe review 1   # hidden risks, opportunities, questions to validate, inputs to double-check
```

Offline brainstorm numbers are starting guesses for each business model, not research.
In every mode, replace guesses with real data (Inputs tab, `reframe edit`, or live market
data) and the scores and plans follow.

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

Requires Python 3.9+. The core has no dependencies. Offline and local AI modes need nothing
else from pip (local AI needs the free Ollama or LM Studio app).

```
pip install -e .          # or: pip install -e ".[ai,dev]"
reframe --help
```

Data is stored in `~/.reframe` (SQLite plus the trained model). Set `REFRAME_HOME` or
`--home` to use another folder.

## Starting the web app

- **Windows:** double-click **`Start ReFrame.bat`** in the ReFrame folder.
- **Mac/Linux:** run `./start-reframe.sh`, or `reframe serve` in a terminal.

Your browser opens ReFrame at http://127.0.0.1:8765. **Keep the terminal window open** while
you use it: closing it stops ReFrame. Don't open `reframe/static/index.html` directly; it
can only work through the server. (Use `reframe serve --no-browser` to skip opening the browser.)

## Troubleshooting

| Message | Cause and fix |
|---|---|
| "Failed to fetch" / "Can't reach ReFrame's server" | The server isn't running, or the page was opened as a file. Start it as shown above and reload the page. |
| "Port 8765 is already in use" | ReFrame is already running: just open http://127.0.0.1:8765. Or use `reframe serve --port 8766`. |
| "ReFrame hit an unexpected error" | The details are saved in `.reframe/error.log` in your home folder. Send that file to get it fixed. |
| Live market sources "unavailable" | No internet, or blocked by a firewall/VPN. Everything else still works. Check with `reframe market --check`. |

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
