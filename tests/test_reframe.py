import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest

from reframe.analyzer import analyze
from reframe.brain import FEATURES, ViabilityModel, featurize
from reframe.engine import Engine
from reframe.market import analyze_market, buy_fraction, simulate
from reframe.models import Idea, MarketInputs
from reframe.planner import build_plan
from reframe.storage import Store
from reframe.web import make_handler


def make_idea(**market) -> Idea:
    return Idea("Test idea", "A test", "saas", True, MarketInputs(**market))


def test_buy_fraction_is_half_at_willingness_to_pay():
    assert buy_fraction(20, 20, 1.5) == pytest.approx(0.5)
    assert buy_fraction(10, 20, 1.5) > buy_fraction(30, 20, 1.5)


def test_optimal_price_beats_nearby_prices():
    idea = make_idea()
    a = analyze_market(idea)

    def profit(p):
        return sum(y.profit for y in simulate(idea, p))

    assert profit(a.optimal_price) >= profit(a.optimal_price * 0.8)
    assert profit(a.optimal_price) >= profit(a.optimal_price * 1.2)
    assert a.optimal_price > idea.market.unit_cost


def test_more_competitors_means_less_profit_and_lower_score():
    few, many = make_idea(competitors=2), make_idea(competitors=200)
    assert analyze_market(few).total_profit > analyze_market(many).total_profit
    assert analyze(few).score > analyze(many).score


def test_features_are_normalized():
    x = featurize(make_idea(), analyze_market(make_idea()))
    assert set(x) == set(FEATURES)
    assert all(0.0 <= v <= 1.0 for v in x.values())


def test_model_learns_from_outcomes():
    # Outcomes where differentiation decided everything.
    good = {k: 0.5 for k in FEATURES} | {"differentiation": 0.9}
    bad = {k: 0.5 for k in FEATURES} | {"differentiation": 0.1}
    model = ViabilityModel()
    before = model.weights["differentiation"]
    model.train([(good, 1.0)] * 10 + [(bad, 0.0)] * 10)
    assert model.weights["differentiation"] > before
    assert model.predict(good) > model.predict(bad)
    assert model.trained_on == 20


def test_explanations_sum_to_score():
    model = ViabilityModel()
    x = featurize(make_idea(), analyze_market(make_idea()))
    total = model.bias + sum(c.impact for c in model.explain(x))
    assert model._z(x) == pytest.approx(total)


def test_plan_has_phases_code_and_risk_fixes():
    idea = make_idea(competitors=300, differentiation=0.1)
    a = analyze(idea)
    plan = build_plan(idea, a)
    names = [p.name for p in plan.phases]
    assert any("Validate" in n for n in names)
    assert any("risks" in n for n in names)
    assert any(s.code for p in plan.phases for s in p.steps)
    md = plan.to_markdown()
    assert "### Step 1" in md and f"${a.market.optimal_price:,.2f}" in md


@pytest.mark.parametrize("category", ["saas", "mobile_app", "ecommerce", "marketplace", "content",
                                      "physical_product", "service", "api"])
def test_every_category_gets_a_plan(category):
    idea = Idea("<X>", "", category, False, MarketInputs())
    plan = build_plan(idea, analyze(idea))
    assert len(plan.phases) >= 4
    assert "<X>" not in "".join(s.code or "" for p in plan.phases for s in p.steps if s.code_language == "html")


def test_store_and_engine_roundtrip(tmp_path):
    engine = Engine(Store(tmp_path))
    a = engine.store.add_idea(make_idea(differentiation=0.9, competitors=1))
    b = engine.store.add_idea(make_idea(differentiation=0.1, competitors=150))
    assert engine.store.get_idea(a.id).market.competitors == 1
    engine.record_outcome(a.id, True, 50_000)
    n = engine.record_outcome(b.id, False)
    assert n == 2
    assert engine.accuracy()["accuracy"] == 1.0
    # The trained model is persisted and reloaded.
    assert Engine(Store(tmp_path)).model.trained_on == 2


def test_invalid_category_rejected():
    with pytest.raises(ValueError):
        Idea("x", category="spaceship")


def test_web_api(tmp_path):
    engine = Engine(Store(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(engine))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path, method="GET", body=None):
        req = urllib.request.Request(base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        status, created = call("/api/ideas", "POST", {"title": "Web idea", "market": {"competitors": 3}})
        assert status == 201 and created["idea"]["id"] == 1
        assert created["plan"]["phases"]
        assert call("/api/ideas")[1][0]["title"] == "Web idea"
        assert call("/api/ideas/1/outcome", "POST", {"success": True})[1]["trained_on"] == 1
        assert call("/api/ideas/99")[0] == 404
        assert call("/api/ideas", "POST", {"title": "x", "category": "nope"})[0] == 400
        with urllib.request.urlopen(base + "/") as r:
            assert b"ReFrame" in r.read()
    finally:
        server.shutdown()


def test_cli_works_on_non_utf8_console(tmp_path):
    # Windows consoles often use cp1252, which can't encode symbols like █ or →.
    import os
    import subprocess
    import sys
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "REFRAME_HOME": str(tmp_path)}
    for args in (["demo"], ["analyze", "1"], ["plan", "1"], ["rank"], ["insights"],
                 ["plan", "1", "--out", str(tmp_path / "plan.md")]):
        r = subprocess.run([sys.executable, "-m", "reframe", *args], env=env, capture_output=True)
        assert r.returncode == 0, r.stderr.decode(errors="replace")
    assert "→" in (tmp_path / "plan.md").read_text(encoding="utf-8")


def test_missing_api_key_gives_friendly_error(tmp_path, monkeypatch):
    pytest.importorskip("anthropic")
    from reframe import llm
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no `ant auth login` profile
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(llm.MissingAPIKey, match="needs an Anthropic API key"):
        llm.brainstorm("restaurants", 1)


def test_api_key_is_saved_and_removed(tmp_path):
    store = Store(tmp_path)
    assert store.load_api_key() is None
    store.save_api_key("  sk-ant-test  ")
    assert store.load_api_key() == "sk-ant-test"
    store.save_api_key(None)
    assert store.load_api_key() is None


def test_offline_brainstorm_returns_best_rated_ideas():
    from reframe.templates import TEMPLATES, offline_brainstorm
    ideas = offline_brainstorm("dog groomers", 3)
    assert len(ideas) == 3
    assert all("dog groomers" in i.title for i in ideas)
    scores = [analyze(i).score for i in ideas]
    assert scores == sorted(scores, reverse=True)
    all_scores = [analyze(i).score for i in offline_brainstorm("dog groomers", len(TEMPLATES))]
    assert scores[-1] >= max(all_scores[3:])


def test_no_credit_error_is_explained(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    httpx2 = pytest.importorskip("httpx2")
    from reframe import llm
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    resp = httpx2.Response(400, request=req)
    body = {"type": "error", "error": {"type": "invalid_request_error",
            "message": "Your credit balance is too low to access the Anthropic API."}}
    err = anthropic.BadRequestError(body["error"]["message"], response=resp, body=body)

    class FakeClient:
        class beta:
            class messages:
                @staticmethod
                def create(**kw):
                    raise err

    monkeypatch.setattr(llm, "_client", lambda key=None: (anthropic, FakeClient))
    with pytest.raises(llm.NoCredits, match="no API credit"):
        llm.brainstorm("restaurants", 1, api_key="sk-ant-x")


def test_offline_mode_is_default_and_never_loads_anthropic(tmp_path):
    import subprocess
    import sys
    # Run in a fresh interpreter so we can check what gets imported.
    code = f"""
import sys
from pathlib import Path
from reframe.engine import Engine
from reframe.storage import Store
e = Engine(Store(Path({str(tmp_path)!r})))
e.store.save_api_key("sk-ant-should-not-be-used")
e.set_live(False)
assert e.mode == "offline"
ideas = e.brainstorm("small restaurants", 3)
idea = e.store.add_idea(ideas[0])
review = e.review(idea)
assert review["source"] == "offline" and review["summary"]
assert "anthropic" not in sys.modules, "offline mode loaded the Anthropic SDK"
print("ok")
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr


def test_mode_switching_and_forced_offline(tmp_path, monkeypatch):
    engine = Engine(Store(tmp_path))
    engine.set_mode("claude")
    assert Engine(Store(tmp_path)).mode == "claude"
    assert Engine(Store(tmp_path), force_offline=True).mode == "offline"
    monkeypatch.setenv("REFRAME_OFFLINE", "1")
    assert Engine(Store(tmp_path)).mode == "offline"
    with pytest.raises(ValueError):
        engine.set_mode("gpt")


def test_offline_brainstorm_matches_audience():
    from reframe.templates import detect_audience, offline_brainstorm
    assert detect_audience("small restaurants") == "business"
    assert detect_audience("dog owners") == "consumer"
    biz = {i.title for i in offline_brainstorm("dental clinics", 12)}
    con = {i.title for i in offline_brainstorm("college students", 12)}
    assert any("Scheduling & admin software" in t for t in biz)
    assert not any("Scheduling & admin software" in t for t in con)
    assert any("Subscription box" in t for t in con)


def test_offline_review_flags_problems():
    from reframe.reviewer import offline_review
    idea = make_idea(competitors=0, differentiation=0.95, customer_acquisition_cost=500)
    r = offline_review(idea, analyze(idea))
    text = " ".join(r["hidden_risks"] + r["suspicious_inputs"])
    assert "Zero competitors" in text and "Differentiation" in text
    assert r["sensitivity"][0]["profit_loss"] >= r["sensitivity"][-1]["profit_loss"]
    assert len(r["questions_to_validate"]) >= 1


def test_web_mode_and_review(tmp_path):
    engine = Engine(Store(tmp_path))
    server = HTTPServer(("127.0.0.1", 0), make_handler(engine))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body else None,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    engine.set_live(False)
    try:
        assert call("/api/settings")["mode"] == "offline"
        ideas = call("/api/brainstorm", {"topic": "pet owners", "count": 2})
        assert len(ideas) == 2
        review = call(f"/api/ideas/{ideas[0]['id']}/review")
        assert review["source"] == "offline" and review["sensitivity"]
        assert call("/api/settings", {"mode": "claude"})["mode"] == "claude"
    finally:
        server.shutdown()


# -- live market data -------------------------------------------------------------

def _fake_fetcher(tmp_path, calls=None, fail=()):
    from reframe.live import Fetcher, SourceError

    class Fake(Fetcher):
        def get_json(self, url, headers=None):
            if calls is not None:
                calls.append(url)
            host = url.split("/")[2]
            if host in fail:
                raise SourceError(f"can't reach {host}")
            if "opensearch" in url:
                return ["invoice", ["Invoice"], [""], ["https://en.wikipedia.org/wiki/Invoice"]]
            if host == "wikimedia.org":  # 24 months: 1000/month last year, 2000/month this year
                return {"items": [{"views": 1000} for _ in range(12)] + [{"views": 2000} for _ in range(12)]}
            if host == "hn.algolia.com":
                return {"nbHits": 150 if "created_at_i%3E" in url and url.count("%3E") else 0,
                        "hits": []}
            if host == "itunes.apple.com":
                apps = [{"trackName": f"App {i}", "price": 4.99 if i % 2 else 0.0,
                         "userRatingCount": 500 if i < 12 else 3, "averageUserRating": 3.6}
                        for i in range(30)]
                return {"resultCount": len(apps), "results": apps}
            if host == "api.github.com":
                return {"total_count": 1000, "items": []}
            raise AssertionError(url)

    return Fake(tmp_path / "cache.json")


def test_live_scan_signals_and_calibration(tmp_path):
    from reframe import live
    idea = Idea("Invoice reminders", category="mobile_app", keywords="invoice",
                market=MarketInputs(demand_growth=0.05, competitors=2, willingness_to_pay=20,
                                    differentiation=0.5))
    scan = live.scan(idea, _fake_fetcher(tmp_path))
    assert not scan.errors, scan.errors
    assert scan.signals["wikipedia"]["growth"] == pytest.approx(1.0)  # 1000 -> 2000 views
    assert scan.signals["appstore"]["established_apps"] == 12
    by_field = {s.field: s for s in scan.suggestions}
    # Growth moves toward the (capped) live signal, but only part of the way.
    g = by_field["demand_growth"]
    assert 0.05 < g.suggested < g.signal <= 0.6
    # 12 established apps vs 2 entered competitors: suggested count rises, not all the way.
    c = by_field["competitors"]
    assert 2 < c.suggested < 12
    assert by_field["willingness_to_pay"].signal == pytest.approx(4.99)
    assert by_field["differentiation"].suggested > 0.5  # competitors rated 3.6/5
    assert scan.pulse is not None and scan.pulse_label
    live.apply(idea, scan)
    assert idea.market.competitors == c.suggested and isinstance(idea.market.competitors, int)


def test_live_scan_is_cached_and_consistent(tmp_path):
    from reframe import live
    calls = []
    idea = Idea("Invoice reminders", category="saas", keywords="invoice")
    now = 1_760_000_000
    first = live.scan(idea, _fake_fetcher(tmp_path, calls), now=now)
    n = len(calls)
    second = live.scan(idea, _fake_fetcher(tmp_path, calls), now=now + 3600)  # new process, same cache file
    assert len(calls) == n, "second scan within 12h should come from the cache"
    assert [s.suggested for s in first.suggestions] == [s.suggested for s in second.suggestions]


def test_live_scan_tolerates_unreachable_sources(tmp_path):
    from reframe import live
    idea = Idea("Invoice reminders", category="saas", keywords="invoice")
    scan = live.scan(idea, _fake_fetcher(tmp_path, fail={"itunes.apple.com", "api.github.com"}))
    assert set(scan.errors) == {"appstore", "github"}
    assert "wikipedia" in scan.signals
    assert all(s.field == "demand_growth" for s in scan.suggestions)


def test_keywords_from_title():
    from reframe.live import keywords_for
    assert keywords_for(Idea("Scheduling & admin software for small restaurants")) == "scheduling admin restaurants"
    assert keywords_for(Idea("x", keywords="dog grooming")) == "dog grooming"


def test_engine_scan_records_history(tmp_path, monkeypatch):
    engine = Engine(Store(tmp_path))
    monkeypatch.setattr(engine, "fetcher", lambda: _fake_fetcher(tmp_path))
    idea = engine.store.add_idea(Idea("Invoice reminders", category="saas", keywords="invoice"))
    engine.scan_market(idea)
    engine.scan_market(idea, apply=True)
    hist = engine.store.score_history(idea.id)
    assert [h["note"] for h in hist] == ["live scan", "live data applied"]
    assert engine.store.latest_scan(idea.id)["applied"] is True
    assert engine.store.get_idea(idea.id).market.demand_growth != MarketInputs().demand_growth


def test_brainstorm_uses_live_data_unless_off(tmp_path, monkeypatch):
    engine = Engine(Store(tmp_path))
    monkeypatch.setattr(engine, "fetcher", lambda: _fake_fetcher(tmp_path))
    live_ideas = engine.brainstorm("invoice", 3)
    engine.set_live(False)
    plain = engine.brainstorm("invoice", 3)
    assert {i.market.demand_growth for i in live_ideas} != {i.market.demand_growth for i in plain}


def test_capped_app_search_never_lowers_competitors():
    from reframe.live import calibrate
    idea = Idea("Fitness app", category="mobile_app", market=MarketInputs(competitors=400))
    signals = {"appstore": {"apps_found": 50, "capped": True, "established_apps": 30, "paid_apps": 0,
                            "median_paid_price": None, "median_rating": 4.5, "total_ratings": 0,
                            "top_apps": [], "url": ""}}
    assert "competitors" not in {s.field for s in calibrate(idea, signals)}
    idea.market.competitors = 5
    assert {s.field: s for s in calibrate(idea, signals)}["competitors"].suggested > 5


def test_unreachable_host_is_tried_once_per_run(tmp_path):
    calls = []
    fetch = _fake_fetcher(tmp_path, calls, fail={"itunes.apple.com"})
    from reframe import live
    for title in ("A invoice app", "B invoice app", "C invoice app"):
        live.scan(Idea(title, category="mobile_app", keywords=title), fetch)
    assert sum("itunes.apple.com" in u for u in calls) == 1


# -- local AI (Ollama / LM Studio) ----------------------------------------------------

def _fake_local_server(kind, replies, models=("llama3.2:latest",), reject_schema=False):
    """Start a fake Ollama ('ollama') or OpenAI-compatible ('openai') server."""
    from http.server import BaseHTTPRequestHandler
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if kind == "ollama" and self.path == "/api/tags":
                return self._send(200, {"models": [{"name": m} for m in models]})
            if kind == "openai" and self.path == "/v1/models":
                return self._send(200, {"data": [{"id": m} for m in models]})
            self._send(404, {})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append(body)
            if reject_schema and "response_format" in body:
                return self._send(400, {"error": "response_format not supported"})
            text = replies.pop(0) if len(replies) > 1 else replies[0]
            if kind == "ollama" and self.path == "/api/chat":
                return self._send(200, {"message": {"role": "assistant", "content": text}, "done": True})
            if kind == "openai" and self.path == "/v1/chat/completions":
                return self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}]})
            self._send(404, {})

    server = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}" + ("/v1" if kind == "openai" else "")
    return server, base, seen


MESSY_IDEAS = """Sure! Here are your ideas:
```json
{"ideas": [
  {"title": "Shift planner for cafes", "description": "Staff scheduling", "category": "SaaS",
   "recurring_revenue": true,
   "market": {"potential_customers": "25,000", "demand_growth": 15, "willingness_to_pay": "$39",
              "competitors": 12, "differentiation": 0.6, "yearly_churn": "30%"}},
  {"title": "Coffee bean subscription", "category": "food delivery", "market": {"willingness_to_pay": -5}},
  {"description": "no title, should be skipped"}
]}
```
Hope this helps!"""


def test_local_ai_brainstorm_with_ollama_repairs_messy_output(tmp_path):
    server, base, seen = _fake_local_server("ollama", ["not json at all", MESSY_IDEAS])
    try:
        engine = Engine(Store(tmp_path))
        engine.set_live(False)
        engine.set_mode("local")
        engine.set_local(provider="ollama", url=base)
        assert engine.local_status()["ready"]
        ideas = engine.brainstorm("cafes", 3)
    finally:
        server.shutdown()
    assert len(seen) == 2, "broken JSON should trigger exactly one retry"
    assert seen[0]["model"] == "llama3.2:latest" and seen[0]["format"]["type"] == "object"
    assert [i.title for i in ideas] == ["Shift planner for cafes", "Coffee bean subscription"]
    a, b = ideas
    assert a.category == "saas" and a.market.potential_customers == 25_000
    assert a.market.demand_growth == pytest.approx(0.15)   # "15" meant 15%
    assert a.market.willingness_to_pay == 39 and a.market.yearly_churn == pytest.approx(0.30)
    assert b.category == "saas" and b.market.willingness_to_pay >= 0.5  # clamped into range
    assert all(i.keywords == "cafes" for i in ideas)


def test_local_ai_review_with_openai_compatible_server(tmp_path):
    review_json = json.dumps({"summary": "Solid niche.", "hidden_risks": ["Seasonality"],
                              "opportunities": "Upsell analytics", "questions_to_validate": [],
                              "suspicious_inputs": []})
    server, base, seen = _fake_local_server("openai", [review_json], models=("qwen2.5-7b-instruct",),
                                            reject_schema=True)
    try:
        engine = Engine(Store(tmp_path))
        engine.set_mode("local")
        engine.set_local(provider="openai", url=base)
        idea = engine.store.add_idea(make_idea())
        r = engine.review(idea)
    finally:
        server.shutdown()
    assert "response_format" in seen[0] and "response_format" not in seen[1]  # fell back
    assert r["source"] == "local" and r["model"] == "qwen2.5-7b-instruct"
    assert r["summary"] == "Solid niche." and r["opportunities"] == ["Upsell analytics"]
    assert r["sensitivity"], "local reviews keep ReFrame's numeric sensitivity analysis"


def test_local_ai_not_running_gives_setup_help(tmp_path):
    from reframe.local_llm import LocalAIUnavailable
    engine = Engine(Store(tmp_path))
    engine.set_live(False)
    engine.set_mode("local")
    engine.set_local(provider="ollama", url="http://127.0.0.1:9")  # nothing listens on port 9
    assert not engine.local_status()["ready"]
    with pytest.raises(LocalAIUnavailable, match="ollama pull"):
        engine.brainstorm("cafes", 2)


def test_local_ai_missing_model_is_reported(tmp_path):
    server, base, _ = _fake_local_server("ollama", ["{}"], models=("mistral:latest",))
    try:
        from reframe.local_llm import detect
        assert detect("ollama", base, "")["model"] == "mistral:latest"  # auto-picks installed model
        status = detect("ollama", base, "qwen2.5:7b")
    finally:
        server.shutdown()
    assert not status["ready"] and "ollama pull qwen2.5:7b" in status["message"]


def test_local_mode_never_loads_anthropic(tmp_path):
    import subprocess
    import sys
    code = f"""
import sys
from pathlib import Path
from reframe.engine import Engine
from reframe.storage import Store
e = Engine(Store(Path({str(tmp_path)!r})))
e.set_mode("local"); e.set_local(provider="ollama", url="http://127.0.0.1:9"); e.set_live(False)
try:
    e.brainstorm("x", 1)
except Exception:
    pass
assert "anthropic" not in sys.modules
print("ok")
"""
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.stdout.strip() == "ok", r.stderr
