"""Minimal web app (standard library only): JSON API + single-page UI."""

from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .engine import Engine
from .models import CATEGORIES, Idea, MarketInputs

STATIC = Path(__file__).parent / "static"
IDEA_PATH = re.compile(r"^/api/ideas/(\d+)(/outcome|/review|/market)?$")


def _summary(engine: Engine, idea: Idea) -> dict:
    a = engine.analyze(idea)
    o = engine.store.outcome_for(idea.id)
    return {"id": idea.id, "title": idea.title, "category": idea.category, "score": a.score,
            "verdict": a.verdict, "total_profit": a.market.total_profit,
            "outcome": None if o is None else bool(o["success"])}


def _full(engine: Engine, idea: Idea) -> dict:
    a = engine.analyze(idea)
    return {"idea": idea.to_dict(), "analysis": a.to_dict(),
            "plan": engine.plan(idea, a).to_dict(),
            "outcome": engine.store.outcome_for(idea.id) if idea.id else None}


def _settings(engine: Engine) -> dict:
    return {"mode": engine.mode, "locked_offline": engine.force_offline,
            "has_key": engine.store.load_api_key() is not None, "live": engine.live_enabled}


def _market(engine: Engine, idea_id: int) -> dict:
    return {"scan": engine.store.latest_scan(idea_id), "history": engine.store.score_history(idea_id),
            "live": engine.live_enabled}


def make_handler(engine: Engine) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:  # keep the console quiet
            pass

        def _send(self, status: int, body: bytes, ctype: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: object, status: int = 200) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _error(self, status: int, message: str) -> None:
            self._json({"error": message}, status)

        def _llm_error(self, e: Exception) -> None:
            from .llm import MissingAPIKey, NoCredits
            if isinstance(e, MissingAPIKey):
                self._json({"error": str(e), "needs_key": True}, 401)
            elif isinstance(e, NoCredits):
                self._json({"error": str(e), "needs_credits": True}, 402)
            else:
                self._json({"error": str(e), "offline_available": True}, 503)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/meta":
                self._json({"categories": CATEGORIES, "defaults": MarketInputs().to_dict()})
            elif path == "/api/settings":
                self._json(_settings(engine))
            elif path == "/api/local":
                self._json(engine.local_status() | engine.local_settings())
            elif path == "/api/ideas":
                self._json([_summary(engine, i) for i in engine.store.list_ideas()])
            elif path == "/api/insights":
                self._json({"accuracy": engine.accuracy(), "lessons": engine.model.lessons(),
                            "trained_on": engine.model.trained_on})
            elif (m := IDEA_PATH.match(path)) and m.group(2) == "/review":
                from .llm import LLMUnavailable
                idea = engine.store.get_idea(int(m.group(1)))
                try:
                    self._json(engine.review(idea))
                except LLMUnavailable as e:
                    self._llm_error(e)
            elif (m := IDEA_PATH.match(path)) and m.group(2) == "/market":
                idea_id = int(m.group(1))
                engine.store.get_idea(idea_id)
                self._json(_market(engine, idea_id))
            elif (m := IDEA_PATH.match(path)) and not m.group(2):
                self._json(_full(engine, engine.store.get_idea(int(m.group(1)))))
            else:
                self._error(404, "not found")

        def do_POST(self) -> None:
            path = self.path.split("?")[0]
            body = self._body()
            if path == "/api/analyze":  # analyze without saving (live what-if)
                idea = Idea.from_dict(body)
                self._json(_full(engine, idea))
            elif path == "/api/ideas":
                idea = engine.store.add_idea(Idea.from_dict(body))
                self._json(_full(engine, idea), 201)
            elif path == "/api/brainstorm":
                from .llm import LLMUnavailable
                topic, count = body.get("topic", ""), int(body.get("count", 3))
                try:
                    ideas = engine.brainstorm(topic, count)
                except LLMUnavailable as e:
                    return self._llm_error(e)
                saved = [engine.store.add_idea(i) for i in ideas]
                self._json([_summary(engine, i) for i in saved], 201)
            elif path == "/api/settings":
                if "mode" in body:
                    engine.set_mode(str(body["mode"]))
                if "live" in body:
                    engine.set_live(bool(body["live"]))
                self._json(_settings(engine))
            elif path == "/api/local":
                engine.set_local(body.get("provider"), body.get("url"), body.get("model"))
                self._json(engine.local_status() | engine.local_settings())
            elif (m := IDEA_PATH.match(path)) and m.group(2) == "/market":
                idea = engine.store.get_idea(int(m.group(1)))
                engine.scan_market(idea, apply=bool(body.get("apply")), refresh=bool(body.get("refresh")))
                self._json(_market(engine, idea.id) | {"full": _full(engine, engine.store.get_idea(idea.id))})
            elif path == "/api/key":  # save the Anthropic API key locally
                key = str(body.get("key", "")).strip()
                if not key:
                    return self._error(400, "Paste a key first.")
                engine.store.save_api_key(key)
                self._json({"saved": True})
            elif (m := IDEA_PATH.match(path)) and m.group(2) == "/outcome":
                n = engine.record_outcome(int(m.group(1)), bool(body.get("success")),
                                          body.get("actual_profit"), body.get("notes", ""))
                self._json({"trained_on": n, "accuracy": engine.accuracy()})
            else:
                self._error(404, "not found")

        def do_PUT(self) -> None:
            m = IDEA_PATH.match(self.path)
            if not m or m.group(2):
                return self._error(404, "not found")
            body = self._body()
            body["id"] = int(m.group(1))
            engine.store.get_idea(body["id"])
            idea = Idea.from_dict(body)
            engine.store.update_idea(idea)
            self._json(_full(engine, engine.store.get_idea(idea.id)))

        def do_DELETE(self) -> None:
            m = IDEA_PATH.match(self.path)
            if not m or m.group(2):
                return self._error(404, "not found")
            engine.store.delete_idea(int(m.group(1)))
            self._json({"deleted": int(m.group(1))})

        def handle_one_request(self) -> None:
            try:
                super().handle_one_request()
            except KeyError as e:
                self._error(HTTPStatus.NOT_FOUND, str(e).strip("'\""))
            except (ValueError, TypeError) as e:
                self._error(HTTPStatus.BAD_REQUEST, str(e))

    return Handler


def serve(engine: Engine, host: str = "127.0.0.1", port: int = 8765) -> None:
    server = HTTPServer((host, port), make_handler(engine))
    print(f"ReFrame running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
