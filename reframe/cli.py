"""Command-line interface: ``reframe <command>``."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .analyzer import Analysis
from .engine import Engine
from .models import CATEGORIES, Idea, MarketInputs
from .storage import Store

EXAMPLES = Path(__file__).parent / "examples.json"

PROMPTS = {
    "potential_customers": "How many people/businesses have this problem in your target market?",
    "demand_growth": "Yearly growth of that market (0.1 = 10%)?",
    "willingness_to_pay": "Typical (median) price buyers would pay per purchase, in $?",
    "price_elasticity": "Price sensitivity (0.5 low .. 3 very high)?",
    "purchases_per_year": "Purchases per customer per year (12 = monthly subscription, 1 = one-off)?",
    "yearly_churn": "Share of customers lost per year (0.3 = 30%)?",
    "competitors": "How many direct competitors/alternatives exist?",
    "differentiation": "How different/better are you (0..1)?",
    "unit_cost": "Variable cost per purchase, in $?",
    "customer_acquisition_cost": "Cost to acquire one customer, in $?",
    "fixed_costs_per_year": "Fixed costs per year (tools, salaries, rent), in $?",
    "upfront_investment": "Upfront investment to build/launch, in $?",
    "build_complexity": "How hard is it to build (0 trivial .. 1 very hard)?",
    "skill_fit": "How well do your skills match what's needed (0..1)?",
    "budget": "How much money can you invest, in $?",
}


def money(x: float) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def _can_print(text: str) -> bool:
    try:
        text.encode(sys.stdout.encoding or "ascii")
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def bar(x: float, width: int = 20) -> str:
    filled = round(max(0.0, min(1.0, x)) * width)
    full, empty = ("█", "░") if _can_print("█░") else ("#", ".")
    return full * filled + empty * (width - filled)


def print_analysis(idea: Idea, a: Analysis) -> None:
    m = a.market
    print(f"\n=== {idea.title}  (#{idea.id}, {idea.category}) ===")
    print(f"Success score  {bar(a.score)} {a.score:.0%}   => {a.verdict}")
    trained = (f"trained on {a.model_trained_on} real outcomes" if a.model_trained_on
               else "using built-in priors; record outcomes to teach it")
    print(f"AI model       {trained}")
    print("\n-- Market & profit (3-year projection) --")
    print(f"Optimal price  ${m.optimal_price:,.2f} ({m.price_vs_wtp:.0%} of typical willingness to pay)")
    for y in m.years:
        print(f"  Year {y.year}: {y.customers:>9,.0f} customers  revenue {money(y.revenue):>12}  "
              f"profit {money(y.profit):>12}")
    print(f"Total profit   {money(m.total_profit)}  (ROI {m.roi:.0%}, after upfront investment)")
    be = f"month {m.break_even_month}" if m.break_even_month else "not within 3 years"
    print(f"Break-even     {be}")
    print(f"Gross margin   {m.gross_margin:.0%}    LTV/CAC {m.ltv_to_cac:.1f}x")
    print(f"Market gap     {bar(m.market_gap, 10)} {m.demand_per_competitor:,.0f} buyers per supplier")
    if m.funding_gap > 0:
        print(f"Funding gap    {money(m.funding_gap)} more than your budget is needed")
    if a.strengths:
        print("\n-- What works --")
        for s in a.strengths:
            print(f"  + {s['label']} (+{s['impact']:.2f})")
    if a.risks:
        print("\n-- What doesn't --")
        for r in a.risks:
            print(f"  - {r['label']} ({r['impact']:.2f}): {r['advice']}")
    print("\n-- Best experiments to try --")
    for e in a.experiments[:3]:
        print(f"  * {e.name}: score {e.score_change:+.0%}, profit {money(e.profit_change)}")
    if a.defaulted_inputs:
        print(f"\nNote: defaults used for {', '.join(a.defaulted_inputs)}")
    print()


def _ask(prompt: str, default: object) -> str:
    try:
        value = input(f"{prompt} [{default}] ").strip()
    except EOFError:
        value = ""
    return value or str(default)


def cmd_new(engine: Engine, args: argparse.Namespace) -> None:
    if args.file:
        raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            idea = engine.store.add_idea(Idea.from_dict(item))
            print(f"Saved idea #{idea.id}: {idea.title}")
        return
    title = args.title or _ask("Idea title?", "My idea")
    description = _ask("Describe it in one or two sentences:", "")
    category = _ask(f"Category ({', '.join(CATEGORIES)})?", "saas")
    recurring = _ask("Recurring revenue? (y/n)", "y").lower().startswith("y")
    defaults = MarketInputs()
    market = {k: _ask(q, getattr(defaults, k)) for k, q in PROMPTS.items()}
    idea = engine.store.add_idea(Idea(title, description, category, recurring,
                                      MarketInputs.from_dict(market)))
    print(f"\nSaved idea #{idea.id}.")
    print_analysis(idea, engine.analyze(idea))


def cmd_list(engine: Engine, args: argparse.Namespace) -> None:
    ideas = engine.store.list_ideas()
    if not ideas:
        print("No ideas yet. Try `reframe new` or `reframe demo`.")
        return
    print(f"{'#':>3}  {'score':>5}  {'3y profit':>12}  {'outcome':<8} title")
    for idea in ideas:
        a = engine.analyze(idea)
        o = engine.store.outcome_for(idea.id)
        outcome = "" if o is None else ("success" if o["success"] else "failure")
        print(f"{idea.id:>3}  {a.score:>5.0%}  {money(a.market.total_profit):>12}  {outcome:<8} {idea.title}")


def cmd_analyze(engine: Engine, args: argparse.Namespace) -> None:
    idea = engine.store.get_idea(args.id)
    a = engine.analyze(idea)
    if args.json:
        print(json.dumps(a.to_dict(), indent=2))
    else:
        print_analysis(idea, a)


def cmd_plan(engine: Engine, args: argparse.Namespace) -> None:
    idea = engine.store.get_idea(args.id)
    plan = engine.plan(idea)
    text = json.dumps(plan.to_dict(), indent=2) if args.json else plan.to_markdown()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Plan written to {args.out}")
    else:
        print(text)


def cmd_edit(engine: Engine, args: argparse.Namespace) -> None:
    idea = engine.store.get_idea(args.id)
    data = idea.to_dict()
    for assignment in args.set:
        key, _, value = assignment.partition("=")
        if key in data["market"]:
            data["market"][key] = value
        elif key == "recurring_revenue":
            data[key] = value.lower() in ("1", "true", "yes", "y")
        elif key in ("title", "description", "category", "keywords"):
            data[key] = value
        else:
            sys.exit(f"Unknown field: {key}")
    idea = Idea.from_dict(data)
    engine.store.update_idea(idea)
    print_analysis(idea, engine.analyze(idea))


def cmd_delete(engine: Engine, args: argparse.Namespace) -> None:
    engine.store.delete_idea(args.id)
    print(f"Deleted idea #{args.id}")


def cmd_outcome(engine: Engine, args: argparse.Namespace) -> None:
    n = engine.record_outcome(args.id, args.result == "success", args.profit, args.notes or "")
    acc = engine.accuracy()
    print(f"Recorded. The AI retrained on {n} outcome(s); it now explains "
          f"{acc['accuracy']:.0%} of them correctly.")


def cmd_rank(engine: Engine, args: argparse.Namespace) -> None:
    ideas = engine.store.list_ideas()
    ranked = sorted(((engine.analyze(i), i) for i in ideas),
                    key=lambda t: (t[0].score, t[0].market.total_profit), reverse=True)
    for n, (a, idea) in enumerate(ranked, 1):
        print(f"{n}. {idea.title} (#{idea.id}) - {a.score:.0%}, 3y profit {money(a.market.total_profit)}, "
              f"{a.verdict}")


def cmd_insights(engine: Engine, args: argparse.Namespace) -> None:
    acc = engine.accuracy()
    if not acc["samples"]:
        print("No outcomes recorded yet; the AI is using its built-in priors.")
        print("Record results with: reframe outcome <id> success|failure")
    else:
        print(f"Learned from {acc['samples']} outcome(s); explains {acc['accuracy']:.0%} of them.")
    print("\nWhat the AI believes drives success (weight; + helps, - hurts):")
    for row in sorted(engine.model.lessons(), key=lambda r: -abs(r["learned"])):
        shift = f"  (learned {row['shift']:+.2f} vs prior)" if abs(row["shift"]) > 0.01 else ""
        print(f"  {row['label']:<26} {row['learned']:+.2f}{shift}")


def cmd_local(engine: Engine, args: argparse.Namespace) -> None:
    engine.set_local(args.provider, args.url, args.model)
    s = engine.local_settings()
    print(f"Local AI settings: provider={s['local_provider']}, "
          f"url={s['local_url'] or '(default)'}, model={s['local_model'] or '(auto)'}")
    status = engine.local_status()
    print(("Ready: " if status["ready"] else "Not ready: ") + status["message"])
    if status["models"]:
        print("Installed models: " + ", ".join(status["models"]))
    if not status["ready"]:
        from .local_llm import SETUP_HELP
        print("\n" + SETUP_HELP)
    elif engine.mode != "local":
        print("Turn it on with: reframe mode local")


def cmd_brainstorm(engine: Engine, args: argparse.Namespace) -> None:
    from .llm import LLMUnavailable  # importing this never loads the Anthropic SDK
    if args.offline:
        engine.force_offline = True
    if engine.mode == "local":
        print("Thinking with your local AI model... (this can take a minute or two on a CPU)")
    try:
        ideas = engine.brainstorm(args.topic, args.count, args.constraints or "")
    except LLMUnavailable as e:  # only possible in claude mode
        sys.exit(f"{e}\n\nTip: switch to offline mode with `reframe mode offline`.")
    if engine.mode == "offline":
        print("Offline mode: ideas come from business-model templates matched to your topic.\n"
              "The market numbers are starting guesses: replace them with real data using\n"
              "`reframe edit <id> --set field=value` (add --save to keep the ideas).")
    for idea in ideas:
        if args.save:
            engine.store.add_idea(idea)
        print_analysis(idea, engine.analyze(idea))


def cmd_review(engine: Engine, args: argparse.Namespace) -> None:
    from .llm import LLMUnavailable  # importing this never loads the Anthropic SDK
    idea = engine.store.get_idea(args.id)
    try:
        r = engine.review(idea)
    except LLMUnavailable as e:  # only possible in claude mode
        sys.exit(f"{e}\n\nTip: switch to offline mode with `reframe mode offline`.")
    if engine.mode == "local":
        print("Reviewing with your local AI model... (this can take a minute or two on a CPU)")
    source = {"offline": "ReFrame offline reviewer", "local": f"local AI ({r.get('model', '')})"}.get(
        r.get("source"), "Claude")
    print(f"\nReview by {source}\n\n{r['summary']}\n")
    for key, label in (("hidden_risks", "Hidden risks"), ("opportunities", "Opportunities"),
                       ("questions_to_validate", "Questions to validate"),
                       ("suspicious_inputs", "Inputs to double-check")):
        if r.get(key):
            print(f"{label}:")
            for item in r[key]:
                print(f"  - {item}")
            print()
    if r.get("sensitivity"):
        print("What your profit depends on most (3-year profit lost if the input is 20% worse):")
        for row in r["sensitivity"][:5]:
            print(f"  {row['label']:<28} {money(-row['profit_loss'])}")
        print()


def cmd_mode(engine: Engine, args: argparse.Namespace) -> None:
    if args.mode:
        engine.set_mode(args.mode)
    if engine.mode == "offline":
        print("Mode: offline. No AI model and no API: brainstorming uses built-in templates,\n"
              "reviews use the rule-based reviewer. Nothing leaves your PC except optional\n"
              "live market lookups (`reframe live off` to stop those).")
    elif engine.mode == "local":
        status = engine.local_status()
        print("Mode: local AI. Brainstorm and review use a language model running on this PC\n"
              "(Ollama or LM Studio). No API key, no cost, your ideas stay on your computer.")
        print(("  Ready: " if status["ready"] else "  Not ready: ") + status["message"])
        if not status["ready"]:
            from .local_llm import SETUP_HELP
            print("\n" + SETUP_HELP)
    else:
        key = "saved" if engine.store.load_api_key() else "not saved (run `reframe set-key`)"
        print(f"Mode: claude. Brainstorm and review use the Claude API (paid per use). API key: {key}.\n"
              "Switch back any time with `reframe mode offline` or `reframe mode local`.")


def cmd_set_key(engine: Engine, args: argparse.Namespace) -> None:
    if args.remove:
        engine.store.save_api_key(None)
        print("Saved API key removed.")
        return
    import getpass
    print("Create a key at https://console.anthropic.com/settings/keys")
    key = getpass.getpass("Paste your Anthropic API key (input is hidden): ").strip()
    if not key:
        sys.exit("No key entered; nothing saved.")
    if not key.startswith("sk-ant-"):
        print("Warning: Anthropic API keys usually start with 'sk-ant-'. Saving anyway.")
    engine.store.save_api_key(key)
    print(f"Key saved to {engine.store.api_key_path} (only on this computer).")
    if engine.mode == "offline":
        print("You're in offline mode. Turn on Claude with: reframe mode claude")


def print_scan(scan) -> None:
    print(f"\n-- Live market scan for \"{scan.query}\" ({scan.fetched_at}) --")
    if scan.pulse is not None:
        print(f"Market pulse   {bar(scan.pulse, 10)} {scan.pulse:.0%} ({scan.pulse_label})")
    sig = scan.signals
    if "wikipedia" in sig:
        w = sig["wikipedia"]
        print(f"  Wikipedia    '{w['article']}': {w['monthly_views']:,.0f} views/month, "
              f"{w['growth']:+.0%} vs last year")
    if "hackernews" in sig:
        h = sig["hackernews"]
        print(f"  Hacker News  {h['stories_this_year']} stories this year vs {h['stories_last_year']} "
              f"last year ({h['growth']:+.0%})")
    if "appstore" in sig:
        a = sig["appstore"]
        price = f", median paid price ${a['median_paid_price']:.2f}" if a["median_paid_price"] else ""
        rating = f", rated {a['median_rating']:.1f}/5" if a["median_rating"] is not None else ""
        print(f"  App Store    {a['apps_found']}{'+' if a['capped'] else ''} apps, "
              f"{a['established_apps']} established{rating}{price}")
    if "github" in sig:
        print(f"  GitHub       {sig['github']['repositories']:,} repositories")
    for name, err in scan.errors.items():
        print(f"  {name:<12} unavailable: {err}")
    if scan.suggestions:
        print("\nSuggested input updates (current -> suggested, confidence):")
        for x in scan.suggestions:
            print(f"  {x.field:<20} {x.current:>10,.3g} -> {x.suggested:<10,.3g} {x.confidence:.0%}  {x.reason}")
    else:
        print("\nNo input changes suggested.")


def cmd_market(engine: Engine, args: argparse.Namespace) -> None:
    if args.check:
        from .live import check
        print("Checking live market sources (needs internet, no API keys)...")
        for name, status in check(engine.fetcher()).items():
            print(f"  {name:<12} {status}")
        return
    ids = [i.id for i in engine.store.list_ideas()] if args.all else [args.id]
    if ids == [None]:
        sys.exit("Give an idea id, or use --all.")
    for idea_id in ids:
        idea = engine.store.get_idea(idea_id)
        before = engine.analyze(idea)
        scan = engine.scan_market(idea, apply=args.apply, refresh=args.refresh)
        print(f"\n=== {idea.title} (#{idea.id}) ===")
        print_scan(scan)
        if args.apply and scan.suggestions:
            after = engine.analyze(idea)
            print(f"\nApplied. Score {before.score:.0%} -> {after.score:.0%}, 3-year profit "
                  f"{money(before.market.total_profit)} -> {money(after.market.total_profit)}")
        elif scan.suggestions:
            print(f"\nApply them with: reframe market {idea.id} --apply")


def cmd_watch(engine: Engine, args: argparse.Namespace) -> None:
    print(f"Watching the live market every {args.every:g} hour(s). Press Ctrl+C to stop.")
    try:
        while True:
            for idea in engine.store.list_ideas():
                before = engine.analyze(idea)
                scan = engine.scan_market(idea, apply=args.apply, refresh=True)
                after = engine.analyze(idea)
                pulse = f"pulse {scan.pulse:.0%}" if scan.pulse is not None else "no live data"
                change = f"{before.score:.0%} -> {after.score:.0%}" if args.apply else f"{after.score:.0%}"
                print(f"[{scan.fetched_at}] #{idea.id} {idea.title}: score {change}, {pulse}, "
                      f"{len(scan.suggestions)} suggestion(s)")
            if args.once:
                return
            time.sleep(args.every * 3600)
    except KeyboardInterrupt:
        print("\nStopped.")


def cmd_history(engine: Engine, args: argparse.Namespace) -> None:
    idea = engine.store.get_idea(args.id)
    rows = engine.store.score_history(idea.id)
    if not rows:
        print("No history yet. Run `reframe market <id>` or `reframe watch` to start tracking.")
        return
    print(f"Score history for {idea.title}:")
    for r in rows:
        pulse = f"pulse {r['pulse']:.0%}" if r["pulse"] is not None else ""
        print(f"  {r['at']}  {bar(r['score'], 10)} {r['score']:>4.0%}  {money(r['total_profit']):>11}  "
              f"{pulse:<11} {r['note'] or ''}")


def cmd_live(engine: Engine, args: argparse.Namespace) -> None:
    if args.state:
        engine.set_live(args.state == "on")
    if engine.live_enabled:
        print("Live market data: on. Brainstormed ideas are calibrated with live signals from\n"
              "Wikipedia, Hacker News, the App Store and GitHub (internet needed, no API keys).\n"
              "Your search keywords are sent to those sites. Turn off with `reframe live off`.")
    else:
        print("Live market data: off. Nothing is fetched from the internet. "
              "Turn on with `reframe live on`.")


def cmd_demo(engine: Engine, args: argparse.Namespace) -> None:
    for item in json.loads(EXAMPLES.read_text(encoding="utf-8")):
        idea = engine.store.add_idea(Idea.from_dict(item))
        print(f"Saved example #{idea.id}: {idea.title}")
    print("\nNow try: reframe rank   |   reframe analyze 1   |   reframe plan 1")


def cmd_serve(engine: Engine, args: argparse.Namespace) -> None:
    from .web import serve
    serve(engine, args.host, args.port)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="reframe",
                                description="Turn ideas into ranked, profitable, step-by-step plans.")
    p.add_argument("--home", help="data directory (default: ~/.reframe or $REFRAME_HOME)")
    p.add_argument("--offline", action="store_true", dest="force_offline",
                   help="run this command offline, whatever the saved mode")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("new", help="add an idea (interactive, or --file idea.json)")
    s.add_argument("title", nargs="?")
    s.add_argument("--file")
    s.set_defaults(func=cmd_new)

    sub.add_parser("list", help="list ideas with scores").set_defaults(func=cmd_list)
    sub.add_parser("rank", help="rank ideas by success score and profit").set_defaults(func=cmd_rank)
    sub.add_parser("insights", help="what the AI has learned").set_defaults(func=cmd_insights)
    sub.add_parser("demo", help="load example ideas").set_defaults(func=cmd_demo)

    s = sub.add_parser("analyze", help="full market + AI analysis of an idea")
    s.add_argument("id", type=int)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_analyze)

    s = sub.add_parser("plan", help="step-by-step build plan")
    s.add_argument("id", type=int)
    s.add_argument("--out")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("edit", help="change fields, e.g. --set competitors=3 --set unit_cost=2.5")
    s.add_argument("id", type=int)
    s.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE")
    s.set_defaults(func=cmd_edit)

    s = sub.add_parser("delete", help="delete an idea")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_delete)

    s = sub.add_parser("outcome", help="record what really happened; retrains the AI")
    s.add_argument("id", type=int)
    s.add_argument("result", choices=["success", "failure"])
    s.add_argument("--profit", type=float)
    s.add_argument("--notes")
    s.set_defaults(func=cmd_outcome)

    s = sub.add_parser("mode", help="show or set the mode: offline (default), local (AI on this PC) or claude")
    s.add_argument("mode", nargs="?", choices=["offline", "local", "claude"])
    s.set_defaults(func=cmd_mode)

    s = sub.add_parser("local", help="set up / check the local AI (Ollama or LM Studio)")
    s.add_argument("--provider", choices=["auto", "ollama", "openai"],
                   help="auto (default), ollama, or openai for LM Studio / llama.cpp / other compatible servers")
    s.add_argument("--url", help="server address, e.g. http://localhost:11434 or http://localhost:1234/v1")
    s.add_argument("--model", help="model name, e.g. llama3.2 or qwen2.5:7b (blank = auto)")
    s.set_defaults(func=cmd_local)

    s = sub.add_parser("brainstorm", help="generate ideas for a topic (offline or with Claude)")
    s.add_argument("topic")
    s.add_argument("--count", type=int, default=5)
    s.add_argument("--constraints")
    s.add_argument("--save", action="store_true")
    s.add_argument("--offline", action="store_true",
                   help="use built-in business-model templates (no API key or credit needed)")
    s.set_defaults(func=cmd_brainstorm)

    s = sub.add_parser("review", help="expert review of an idea (offline or with Claude)")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("set-key", help="save your Anthropic API key (only needed for claude mode)")
    s.add_argument("--remove", action="store_true", help="delete the saved key")
    s.set_defaults(func=cmd_set_key)

    s = sub.add_parser("market", help="scan live market data for an idea and suggest input updates")
    s.add_argument("id", type=int, nargs="?")
    s.add_argument("--all", action="store_true", help="scan every idea")
    s.add_argument("--apply", action="store_true", help="apply the suggested updates")
    s.add_argument("--refresh", action="store_true", help="ignore the 12-hour cache")
    s.add_argument("--check", action="store_true", help="test that every live source is reachable")
    s.set_defaults(func=cmd_market)

    s = sub.add_parser("watch", help="re-scan the live market for all ideas on a schedule")
    s.add_argument("--every", type=float, default=6, metavar="HOURS")
    s.add_argument("--apply", action="store_true", help="apply suggestions automatically")
    s.add_argument("--once", action="store_true", help="scan once and exit (for cron/Task Scheduler)")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("history", help="score history of an idea over time")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("live", help="turn live market data on or off")
    s.add_argument("state", nargs="?", choices=["on", "off"])
    s.set_defaults(func=cmd_live)

    s = sub.add_parser("serve", help="start the web app")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(func=cmd_serve)
    return p


def _safe_console() -> None:
    """Never crash on characters the terminal can't show (e.g. Windows cp1252 consoles)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> None:
    _safe_console()
    args = build_parser().parse_args(argv)
    engine = Engine(Store(Path(args.home)) if args.home else None, force_offline=args.force_offline)
    try:
        args.func(engine, args)
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
