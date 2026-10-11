"""Local AI: brainstorm and review with a language model running on your own PC.

Works with either of these free apps (nothing leaves your computer):

* **Ollama** (https://ollama.com), at http://localhost:11434 by default.
  Install it, then e.g. ``ollama pull llama3.2``.
* **LM Studio** (https://lmstudio.ai) or any OpenAI-compatible local server
  (llama.cpp ``llama-server``, Jan, LocalAI...). LM Studio's default is
  http://localhost:1234/v1. Start its local server with a model loaded.

With provider ``auto`` (the default) ReFrame looks for Ollama first, then LM
Studio. Local models are smaller than cloud models, so every answer is
checked, repaired where possible, and every number is kept in a sane range.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .analyzer import Analysis
from .llm import LLMUnavailable
from .models import CATEGORIES, Idea, MarketInputs
from .prompts import IDEAS_SCHEMA, REVIEW_SCHEMA, brainstorm_prompt, review_prompt

PROVIDERS = ("auto", "ollama", "openai")
DEFAULT_URLS = {"ollama": "http://localhost:11434", "openai": "http://localhost:1234/v1"}
RECOMMENDED_MODEL = "llama3.2"  # ~2 GB, runs on most PCs; qwen2.5:7b or llama3.1:8b are smarter
GENERATE_TIMEOUT = 600  # seconds: local models on a CPU can be slow
PROBE_TIMEOUT = 3

# Sane ranges for model-generated market inputs.
RANGES = {
    "potential_customers": (10, 100_000_000), "demand_growth": (-0.5, 1.0),
    "willingness_to_pay": (0.5, 100_000), "price_elasticity": (0.2, 4.0),
    "purchases_per_year": (0.1, 365), "yearly_churn": (0.0, 1.0), "competitors": (0, 10_000),
    "differentiation": (0.0, 1.0), "unit_cost": (0.0, 100_000),
    "customer_acquisition_cost": (0.0, 100_000), "fixed_costs_per_year": (0.0, 10_000_000),
    "upfront_investment": (0.0, 10_000_000), "build_complexity": (0.0, 1.0),
    "skill_fit": (0.0, 1.0), "budget": (0.0, 100_000_000),
}


class LocalAIUnavailable(LLMUnavailable):
    pass


SETUP_HELP = (
    "No local AI found on this PC.\n"
    "Option A (recommended): install Ollama from https://ollama.com, then run:\n"
    f"    ollama pull {RECOMMENDED_MODEL}\n"
    "Option B: install LM Studio from https://lmstudio.ai, download a model, and start its\n"
    "    local server (Developer tab -> Start Server).\n"
    "Then try again. Check the setup any time with:  reframe local\n"
    "Or use built-in templates with no AI model:  reframe mode offline"
)


# -- HTTP -------------------------------------------------------------------------

def _request(url: str, body: dict | None = None, timeout: float = PROBE_TIMEOUT) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _list_models(provider: str, url: str) -> list[str]:
    if provider == "ollama":
        return [m["name"] for m in _request(url.rstrip("/") + "/api/tags").get("models", [])]
    return [m["id"] for m in _request(url.rstrip("/") + "/models").get("data", [])]


def detect(provider: str = "auto", url: str = "", model: str = "") -> dict:
    """Find a running local AI server. Never raises; reports what it found."""
    candidates = ([("ollama", url or DEFAULT_URLS["ollama"]), ("openai", DEFAULT_URLS["openai"])]
                  if provider == "auto" else [(provider, url or DEFAULT_URLS[provider])])
    tried = []
    for prov, base in candidates:
        try:
            models = _list_models(prov, base)
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
            tried.append(base)
            continue
        chosen = _choose_model(models, model)
        name = "Ollama" if prov == "ollama" else "OpenAI-compatible server (e.g. LM Studio)"
        if chosen is None:
            hint = (f"run: ollama pull {model or RECOMMENDED_MODEL}" if prov == "ollama"
                    else "load a model in LM Studio")
            msg = (f"{name} is running at {base} but "
                   + (f"model '{model}' isn't installed" if model and models else "has no models")
                   + f"; {hint}")
            return {"ready": False, "provider": prov, "url": base, "models": models,
                    "model": None, "message": msg}
        return {"ready": True, "provider": prov, "url": base, "models": models, "model": chosen,
                "message": f"Using {name} at {base} with model {chosen}"}
    return {"ready": False, "provider": provider, "url": url, "models": [], "model": None,
            "message": f"No local AI server found (tried {', '.join(tried)})."}


def _choose_model(models: list[str], wanted: str) -> str | None:
    if not models:
        return None
    if not wanted:
        for preferred in (RECOMMENDED_MODEL, "qwen2.5", "llama3.1", "mistral", "gemma"):
            for m in models:
                if m.split(":")[0] == preferred or m.startswith(preferred):
                    return m
        return models[0]
    for m in models:
        if m == wanted or m.split(":")[0] == wanted or m == f"{wanted}:latest":
            return m
    return None


# -- generation ---------------------------------------------------------------------

def _chat(server: dict, system: str, prompt: str, schema: dict) -> str:
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    base = server["url"].rstrip("/")
    try:
        if server["provider"] == "ollama":
            r = _request(base + "/api/chat", {"model": server["model"], "messages": messages,
                                              "stream": False, "format": schema,
                                              "options": {"temperature": 0.4}}, GENERATE_TIMEOUT)
            return r["message"]["content"]
        body = {"model": server["model"], "messages": messages, "temperature": 0.4,
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "reframe", "schema": schema, "strict": True}}}
        try:
            r = _request(base + "/chat/completions", body, GENERATE_TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code not in (400, 422):
                raise
            body.pop("response_format")  # server doesn't support schemas: rely on the prompt
            r = _request(base + "/chat/completions", body, GENERATE_TIMEOUT)
        return r["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        raise LocalAIUnavailable(f"The local AI server returned HTTP {e.code}. Is the model loaded?") from e
    except (urllib.error.URLError, OSError) as e:
        if "timed out" in str(e):
            raise LocalAIUnavailable("The local AI took too long. Try a smaller model, "
                                     f"e.g. `ollama pull {RECOMMENDED_MODEL}`.") from e
        raise LocalAIUnavailable("Lost connection to the local AI server.\n" + SETUP_HELP) from e
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise LocalAIUnavailable("The local AI server sent an unexpected response.") from e


def extract_json(text: str) -> object:
    """Parse JSON from a model reply, tolerating ```fences``` and extra prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("no JSON found in the model's reply")


def _number(value, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").replace("$", "").replace("%", "").strip()
        try:
            n = float(cleaned)
            return n / 100 if value.strip().endswith("%") else n
        except ValueError:
            return default
    return default


def sanitize_market(raw: object) -> MarketInputs:
    defaults = MarketInputs()
    raw = raw if isinstance(raw, dict) else {}
    values = {}
    for name, (lo, hi) in RANGES.items():
        v = _number(raw.get(name), getattr(defaults, name))
        if hi <= 1.0 and 1.0 < v <= 100:  # "15" meant 15% for a 0..1 field
            v /= 100
        v = min(hi, max(lo, v))
        values[name] = int(round(v)) if isinstance(getattr(defaults, name), int) else v
    return MarketInputs(**values)


def sanitize_ideas(data: object, topic: str) -> list[Idea]:
    items = data.get("ideas", []) if isinstance(data, dict) else data if isinstance(data, list) else []
    ideas = []
    for d in items:
        if not isinstance(d, dict) or not str(d.get("title", "")).strip():
            continue
        category = str(d.get("category", "saas")).strip().lower().replace(" ", "_").replace("-", "_")
        ideas.append(Idea(
            title=str(d["title"]).strip()[:120],
            description=str(d.get("description", "")).strip()[:600],
            category=category if category in CATEGORIES else "saas",
            recurring_revenue=bool(d.get("recurring_revenue", True)),
            market=sanitize_market(d.get("market")),
            keywords=topic,
        ))
    return ideas


def _with_format_hint(prompt: str, schema: dict) -> str:
    return (prompt + "\n\nReply with JSON only (no other text), matching this JSON schema:\n"
            + json.dumps(schema))


# -- public API ---------------------------------------------------------------------------

def brainstorm(topic: str, count: int, constraints: str, settings: dict) -> list[Idea]:
    server = _ready_server(settings)
    system, prompt = brainstorm_prompt(topic, count, constraints)
    prompt = _with_format_hint(prompt, IDEAS_SCHEMA)
    for attempt in range(2):  # small models occasionally produce broken JSON: retry once
        try:
            ideas = sanitize_ideas(extract_json(_chat(server, system, prompt, IDEAS_SCHEMA)), topic)
        except ValueError:
            ideas = []
        if ideas:
            return ideas[:count]
    raise LocalAIUnavailable(f"The local model ({server['model']}) didn't return usable ideas. "
                             "Try again, or use a larger model such as qwen2.5:7b.")


def review(idea: Idea, analysis: Analysis, settings: dict) -> dict:
    server = _ready_server(settings)
    system, prompt = review_prompt(idea, analysis)
    prompt = _with_format_hint(prompt, REVIEW_SCHEMA)
    for attempt in range(2):
        try:
            data = extract_json(_chat(server, system, prompt, REVIEW_SCHEMA))
        except ValueError:
            continue
        if isinstance(data, dict) and str(data.get("summary", "")).strip():
            out = {"summary": str(data["summary"]).strip()}
            for key in ("hidden_risks", "opportunities", "questions_to_validate", "suspicious_inputs"):
                items = data.get(key, [])
                out[key] = [str(i).strip() for i in (items if isinstance(items, list) else [items])
                            if str(i).strip()]
            return out | {"source": "local", "model": server["model"]}
    raise LocalAIUnavailable(f"The local model ({server['model']}) didn't return a usable review. "
                             "Try again, or use a larger model such as qwen2.5:7b.")


def _ready_server(settings: dict) -> dict:
    found = detect(settings.get("local_provider", "auto"), settings.get("local_url", ""),
                   settings.get("local_model", ""))
    if not found["ready"]:
        raise LocalAIUnavailable(found["message"] + "\n\n" + SETUP_HELP)
    return found
