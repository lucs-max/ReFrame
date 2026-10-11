# Command reference

*Generated from `reframe --help` by `tools/gen_cli_reference.py`.*

Every command also works as `python -m reframe <command>`. Add `--help` to any command for details.

**Global options:** `--home DIR` uses another data folder (default `~/.reframe` or `$REFRAME_HOME`); `--offline` runs one command in offline mode whatever the saved mode.

| Command | What it does |
|---|---|
| [`new`](#new) | add an idea (interactive, or --file idea.json) |
| [`list`](#list) | list ideas with scores |
| [`rank`](#rank) | rank ideas by success score and profit |
| [`insights`](#insights) | what the AI has learned |
| [`demo`](#demo) | load example ideas |
| [`analyze`](#analyze) | full market + AI analysis of an idea |
| [`plan`](#plan) | step-by-step build plan |
| [`edit`](#edit) | change fields, e.g. --set competitors=3 --set unit_cost=2.5 |
| [`delete`](#delete) | delete an idea |
| [`outcome`](#outcome) | record what really happened; retrains the AI |
| [`mode`](#mode) | show or set the mode: offline (default), local (AI on this PC) or claude |
| [`local`](#local) | set up / check the local AI (Ollama or LM Studio) |
| [`brainstorm`](#brainstorm) | generate ideas for a topic (templates, local AI or Claude, by mode) |
| [`review`](#review) | critical review of an idea (rule-based, local AI or Claude, by mode) |
| [`set-key`](#set-key) | save your Anthropic API key (only needed for claude mode) |
| [`market`](#market) | scan live market data for an idea and suggest input updates |
| [`watch`](#watch) | re-scan the live market for all ideas on a schedule |
| [`history`](#history) | score history of an idea over time |
| [`live`](#live) | turn live market data on or off |
| [`serve`](#serve) | start the web app |

## new

Add an idea (interactive, or --file idea.json).

```
reframe new [-h] [--file FILE] [title]
```

| Argument | Meaning |
|---|---|
| `title` | idea title (you're asked for the rest) |
| `--file` | JSON file with one idea or a list of ideas (see reframe/examples.json) |

## list

List ideas with scores.

```
reframe list [-h]
```

## rank

Rank ideas by success score and profit.

```
reframe rank [-h]
```

## insights

What the AI has learned.

```
reframe insights [-h]
```

## demo

Load example ideas.

```
reframe demo [-h]
```

## analyze

Full market + AI analysis of an idea.

```
reframe analyze [-h] [--json] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |
| `--json` | output JSON |

## plan

Step-by-step build plan.

```
reframe plan [-h] [--out OUT] [--json] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |
| `--out` | write the plan to a file (Markdown checklist) instead of the screen |
| `--json` | output JSON |

## edit

Change fields, e.g. --set competitors=3 --set unit_cost=2.5.

```
reframe edit [-h] [--set FIELD=VALUE] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |
| `--set` | field to change; repeat for several (market inputs, title, description, category, keywords, recurring_revenue) |

## delete

Delete an idea.

```
reframe delete [-h] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |

## outcome

Record what really happened; retrains the AI.

```
reframe outcome [-h] [--profit PROFIT] [--notes NOTES]
                       id {success,failure}
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |
| `result` | what happened. One of: success, failure. |
| `--profit` | actual profit, if known |
| `--notes` | what you learned |

## mode

Show or set the mode: offline (default), local (AI on this PC) or claude.

```
reframe mode [-h] [{offline,local,claude}]
```

| Argument | Meaning |
|---|---|
| `mode` | mode to switch to (omit to show the current one) One of: offline, local, claude. |

## local

Set up / check the local AI (Ollama or LM Studio).

```
reframe local [-h] [--provider {auto,ollama,openai}] [--url URL]
                     [--model MODEL]
```

| Argument | Meaning |
|---|---|
| `--provider` | auto (default), ollama, or openai for LM Studio / llama.cpp / other compatible servers. One of: auto, ollama, openai. |
| `--url` | server address, e.g. http://localhost:11434 or http://localhost:1234/v1 |
| `--model` | model name, e.g. llama3.2 or qwen2.5:7b (blank = auto) |

## brainstorm

Generate ideas for a topic (templates, local AI or Claude, by mode).

```
reframe brainstorm [-h] [--count COUNT] [--constraints CONSTRAINTS]
                          [--save] [--offline]
                          topic
```

| Argument | Meaning |
|---|---|
| `topic` | what the ideas should be about, e.g. "dog groomers" |
| `--count` | how many ideas. Default: `5`. |
| `--constraints` | your limits, e.g. "no coding, under $1,000" (local AI / Claude) |
| `--save` | save the ideas (otherwise they're only shown) |
| `--offline` | use built-in business-model templates (no API key or credit needed) |

## review

Critical review of an idea (rule-based, local AI or Claude, by mode).

```
reframe review [-h] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |

## set-key

Save your Anthropic API key (only needed for claude mode).

```
reframe set-key [-h] [--remove]
```

| Argument | Meaning |
|---|---|
| `--remove` | delete the saved key |

## market

Scan live market data for an idea and suggest input updates.

```
reframe market [-h] [--all] [--apply] [--refresh] [--check] [id]
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |
| `--all` | scan every idea |
| `--apply` | apply the suggested updates |
| `--refresh` | ignore the 12-hour cache |
| `--check` | test that every live source is reachable |

## watch

Re-scan the live market for all ideas on a schedule.

```
reframe watch [-h] [--every HOURS] [--apply] [--once]
```

| Argument | Meaning |
|---|---|
| `--every` | hours between scans. Default: `6`. |
| `--apply` | apply suggestions automatically |
| `--once` | scan once and exit (for cron/Task Scheduler) |

## history

Score history of an idea over time.

```
reframe history [-h] id
```

| Argument | Meaning |
|---|---|
| `id` | idea number (see `reframe list`) |

## live

Turn live market data on or off.

```
reframe live [-h] [{on,off}]
```

| Argument | Meaning |
|---|---|
| `state` | omit to show the current setting. One of: on, off. |

## serve

Start the web app.

```
reframe serve [-h] [--host HOST] [--port PORT] [--no-browser]
```

| Argument | Meaning |
|---|---|
| `--host` | address to listen on (keep 127.0.0.1 to stay private) Default: `127.0.0.1`. |
| `--port` | port to listen on. Default: `8765`. |
| `--no-browser` | don't open the browser automatically |
