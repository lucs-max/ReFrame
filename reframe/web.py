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
IDEA_PATH = re.compile(r"^/api/ideas/(\d+)(/outcome)?$")


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

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/meta":
                self._json({"categories": CATEGORIES, "defaults": MarketInputs().to_dict()})
            elif path == "/api/ideas":
                self._json([_summary(engine, i) for i in engine.store.list_ideas()])
            elif path == "/api/insights":
                self._json({"accuracy": engine.accuracy(), "lessons": engine.model.lessons(),
                            "trained_on": engine.model.trained_on})
            elif m := IDEA_PATH.match(path):
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
                from .llm import LLMUnavailable, MissingAPIKey, NoCredits, brainstorm
                topic, count = body.get("topic", ""), int(body.get("count", 3))
                if body.get("offline"):
                    from .templates import offline_brainstorm
                    ideas = offline_brainstorm(topic, count, engine.model)
                else:
                    try:
                        ideas = brainstorm(topic, count, api_key=engine.store.load_api_key())
                    except MissingAPIKey as e:
                        return self._json({"error": str(e), "needs_key": True}, 401)
                    except NoCredits as e:
                        return self._json({"error": str(e), "needs_credits": True}, 402)
                    except LLMUnavailable as e:
                        return self._json({"error": str(e), "offline_available": True}, 503)
                saved = [engine.store.add_idea(i) for i in ideas]
                self._json([_summary(engine, i) for i in saved], 201)
            elif path == "/api/key":  # save the Anthropic API key locally
                key = str(body.get("key", "")).strip()
                if not key:
                    return self._error(400, "Paste a key first.")
                engine.store.save_api_key(key)
                self._json({"saved": True})
            elif (m := IDEA_PATH.match(path)) and m.group(2):
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
