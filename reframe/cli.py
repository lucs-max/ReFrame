"""Command-line interface: ``reframe <command>``."""

from __future__ import annotations

import argparse
import json
import sys
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
        elif key in ("title", "description", "category"):
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


def cmd_brainstorm(engine: Engine, args: argparse.Namespace) -> None:
    from .llm import LLMUnavailable, brainstorm
    try:
        ideas = brainstorm(args.topic, args.count, args.constraints or "")
    except LLMUnavailable as e:
        sys.exit(str(e))
    for idea in ideas:
        if args.save:
            engine.store.add_idea(idea)
        print_analysis(idea, engine.analyze(idea))


def cmd_review(engine: Engine, args: argparse.Namespace) -> None:
    from .llm import LLMUnavailable, review
    idea = engine.store.get_idea(args.id)
    try:
        r = review(idea, engine.analyze(idea))
    except LLMUnavailable as e:
        sys.exit(str(e))
    print(f"\n{r['summary']}\n")
    for key, label in (("hidden_risks", "Hidden risks"), ("opportunities", "Opportunities"),
                       ("questions_to_validate", "Questions to validate"),
                       ("suspicious_inputs", "Inputs to double-check")):
        print(f"{label}:")
        for item in r[key]:
            print(f"  - {item}")
        print()


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

    s = sub.add_parser("brainstorm", help="generate ideas with Claude (optional)")
    s.add_argument("topic")
    s.add_argument("--count", type=int, default=5)
    s.add_argument("--constraints")
    s.add_argument("--save", action="store_true")
    s.set_defaults(func=cmd_brainstorm)

    s = sub.add_parser("review", help="expert review of an idea with Claude (optional)")
    s.add_argument("id", type=int)
    s.set_defaults(func=cmd_review)

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
    engine = Engine(Store(Path(args.home)) if args.home else None)
    try:
        args.func(engine, args)
    except (KeyError, ValueError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
