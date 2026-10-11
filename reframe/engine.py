"""High-level operations used by the CLI and the web app."""

from __future__ import annotations

from .analyzer import Analysis, analyze
from .brain import ViabilityModel, featurize
from .market import analyze_market
from .models import Idea
from .planner import BuildPlan, build_plan
from .storage import Store


class Engine:
    def __init__(self, store: Store | None = None):
        self.store = store or Store()
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
