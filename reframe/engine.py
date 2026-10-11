"""High-level operations used by the CLI and the web app."""

from __future__ import annotations

import os

from .analyzer import Analysis, analyze
from .brain import ViabilityModel, featurize
from .market import analyze_market
from .models import Idea
from .planner import BuildPlan, build_plan
from .storage import Store


MODES = ("offline", "local", "claude")


class Engine:
    """Shared logic for the CLI and web app.

    Modes decide who writes brainstormed ideas and reviews:

    * ``offline`` (default): built-in templates and the rule-based reviewer.
    * ``local``: a language model running on this PC (Ollama or LM Studio).
    * ``claude``: the Claude API (needs an Anthropic key with API credit).

    Scoring, ranking, plans and learning always run locally in every mode.
    """

    def __init__(self, store: Store | None = None, force_offline: bool = False):
        self.store = store or Store()
        self.force_offline = force_offline or os.environ.get("REFRAME_OFFLINE", "") not in ("", "0")
        self._model_mtime: float | None = None
        self.model = ViabilityModel()
        self._refresh_model()

    def _refresh_model(self) -> None:
        """Reload the model if another process (e.g. the CLI) retrained it."""
        path = self.store.model_path
        mtime = path.stat().st_mtime if path.exists() else None
        if mtime != self._model_mtime:
            self.model = ViabilityModel.load(path)
            self._model_mtime = mtime

    def analyze(self, idea: Idea) -> Analysis:
        self._refresh_model()
        return analyze(idea, self.model)

    def plan(self, idea: Idea, analysis: Analysis | None = None) -> BuildPlan:
        return build_plan(idea, analysis or self.analyze(idea))

    def retrain(self) -> int:
        """Retrain the AI on every recorded outcome. Returns the sample count."""
        samples = []
        for idea, outcome in self.store.outcomes():
            x = featurize(idea, analyze_market(idea))
            samples.append((x, 1.0 if outcome["success"] else 0.0))
        model = ViabilityModel()
        model.train(samples)
        model.save(self.store.model_path)
        self.model = model
        self._model_mtime = self.store.model_path.stat().st_mtime
        return len(samples)

    def record_outcome(self, idea_id: int, success: bool, actual_profit: float | None = None,
                       notes: str = "") -> int:
        self.store.record_outcome(idea_id, success, actual_profit, notes)
        return self.retrain()

    def accuracy(self) -> dict:
        """How well the current model explains the recorded outcomes."""
        self._refresh_model()
        data = self.store.outcomes()
        if not data:
            return {"samples": 0, "accuracy": None}
        hits = 0
        for idea, outcome in data:
            p = self.model.predict(featurize(idea, analyze_market(idea)))
            hits += (p >= 0.5) == outcome["success"]
        return {"samples": len(data), "accuracy": hits / len(data)}

    # -- mode -------------------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.force_offline:
            return "offline"
        mode = self.store.load_config().get("mode", "offline")
        return mode if mode in MODES else "offline"

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Mode must be one of: {', '.join(MODES)}")
        self.store.save_config(mode=mode)

    def brainstorm(self, topic: str, count: int = 5, constraints: str = "") -> list[Idea]:
        """Raises llm.LLMUnavailable (only in claude mode) if Claude can't be used."""
        if self.mode == "offline":
            from .templates import offline_brainstorm
            ideas = offline_brainstorm(topic, count, self.model)
        elif self.mode == "local":
            from . import local_llm
            ideas = local_llm.brainstorm(topic, count, constraints, self.store.load_config())
        else:
            from .llm import brainstorm
            ideas = brainstorm(topic, count, constraints, self.store.load_api_key())
            for idea in ideas:
                idea.keywords = idea.keywords or topic
        return self.calibrate_new_ideas(ideas) if self.live_enabled else ideas

    def review(self, idea: Idea, analysis: Analysis | None = None) -> dict:
        """Raises llm.LLMUnavailable (only in claude mode) if Claude can't be used."""
        analysis = analysis or self.analyze(idea)
        if self.mode == "offline":
            from .reviewer import offline_review
            return offline_review(idea, analysis)
        if self.mode == "local":
            from . import local_llm
            from .reviewer import offline_review
            result = local_llm.review(idea, analysis, self.store.load_config())
            # Keep the exact numeric sensitivity analysis alongside the model's opinion.
            return result | {"sensitivity": offline_review(idea, analysis)["sensitivity"]}
        from .llm import review
        result = review(idea, analysis, self.store.load_api_key())
        return result | {"source": "claude"}

    # -- local AI ---------------------------------------------------------------------
    def local_settings(self) -> dict:
        c = self.store.load_config()
        return {"local_provider": c.get("local_provider", "auto"), "local_url": c.get("local_url", ""),
                "local_model": c.get("local_model", "")}

    def set_local(self, provider: str | None = None, url: str | None = None,
                  model: str | None = None) -> None:
        from .local_llm import PROVIDERS
        changes = {}
        if provider is not None:
            if provider not in PROVIDERS:
                raise ValueError(f"Provider must be one of: {', '.join(PROVIDERS)}")
            changes["local_provider"] = provider
        if url is not None:
            changes["local_url"] = url.strip()
        if model is not None:
            changes["local_model"] = model.strip()
        if changes:
            self.store.save_config(**changes)

    def local_status(self) -> dict:
        from .local_llm import detect
        s = self.local_settings()
        return detect(s["local_provider"], s["local_url"], s["local_model"])

    # -- live market data ---------------------------------------------------------
    @property
    def live_enabled(self) -> bool:
        return bool(self.store.load_config().get("live_data", True))

    def set_live(self, enabled: bool) -> None:
        self.store.save_config(live_data=bool(enabled))

    def fetcher(self):
        from .live import Fetcher
        return Fetcher(self.store.home / "market_cache.json")

    def scan_market(self, idea: Idea, apply: bool = False, refresh: bool = False):
        """Fetch live signals for a saved idea, optionally apply the suggestions.

        Every scan is stored, and the idea's score is added to its history, so
        you can follow how the live market moves the score over time.
        """
        from . import live
        result = live.scan(idea, self.fetcher(), refresh=refresh)
        if apply and result.suggestions:
            live.apply(idea, result)
            self.store.update_idea(idea)
        if idea.id is not None:
            self.store.add_scan(idea.id, result.to_dict(), apply and bool(result.suggestions))
            a = self.analyze(idea)
            note = "live data applied" if apply and result.suggestions else "live scan"
            self.store.add_score(idea.id, a.score, a.market.total_profit, result.pulse, note)
        return result

    def calibrate_new_ideas(self, ideas: list[Idea], budget_seconds: float = 20) -> list[Idea]:
        """Apply live signals to freshly brainstormed ideas.

        Best effort: brainstorming never fails or hangs because of live data. If
        the internet is slow or blocked, the remaining ideas keep their numbers.
        """
        import time
        from . import live
        fetch = self.fetcher()
        start = time.monotonic()
        for idea in ideas:
            if time.monotonic() - start > budget_seconds:
                break
            try:
                live.apply(idea, live.scan(idea, fetch))
            except Exception:  # noqa: BLE001 - live data is optional
                continue
        return ideas
