"""Regenerate docs/cli-reference.md from the CLI's own help text.

Run from the repository root:  python tools/gen_cli_reference.py
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reframe.cli import build_parser  # noqa: E402


def _sentence(text: str) -> str:
    return (text[:1].upper() + text[1:] + ("" if text.endswith(".") else ".")) if text else ""


def main() -> None:
    parser = build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    help_by = {c.dest: c.help for c in sub._choices_actions}
    out = ["# Command reference", "",
           "*Generated from `reframe --help` by `tools/gen_cli_reference.py`.*", "",
           "Every command also works as `python -m reframe <command>`. Add `--help` to any "
           "command for details.", "",
           "**Global options:** `--home DIR` uses another data folder (default `~/.reframe` or "
           "`$REFRAME_HOME`); `--offline` runs one command in offline mode whatever the saved mode.", "",
           "| Command | What it does |", "|---|---|"]
    out += [f"| [`{name}`](#{name}) | {help_by.get(name, '')} |" for name in sub.choices]
    for name, sp in sub.choices.items():
        out += ["", f"## {name}", "", _sentence(help_by.get(name, "")), "",
                "```", sp.format_usage().replace("usage: ", "").strip(), "```"]
        rows = []
        for a in sp._actions:
            if isinstance(a, argparse._HelpAction):
                continue
            flag = ", ".join(a.option_strings) if a.option_strings else a.dest
            choices = f" One of: {', '.join(map(str, a.choices))}." if a.choices else ""
            default = (f" Default: `{a.default}`."
                       if a.default not in (None, False, [], argparse.SUPPRESS) else "")
            text = (a.help or "").replace("|", "/")
            if text and (choices or default) and not text.endswith((".", ")")):
                text += "."
            rows.append(f"| `{flag}` | {text}{choices}{default} |")
        if rows:
            out += ["", "| Argument | Meaning |", "|---|---|", *rows]
    Path("docs/cli-reference.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("wrote docs/cli-reference.md")


if __name__ == "__main__":
    main()
