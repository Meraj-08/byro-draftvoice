"""Local HTTP API for the mock feed and the right-click extension.

Binds to 127.0.0.1 only. Requests from other websites are refused, so a page you happen to visit
cannot use DraftVoice in the background. The API never posts anywhere: approving returns text to copy.
"""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from draftvoice import learning
from draftvoice.model import ModelError, get_drafter, load_env
from draftvoice.models import Proposal
from draftvoice.pipeline import post_from_text, propose
from draftvoice.store import FIXTURES_DIR, DataError, Founder, list_founders

WEB = Path(__file__).parent / "web"
FOUNDERS = ("rico", "fathin")
DRAFTERS = ("stub", "gemini")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def allowed_origin(origin: str | None, port: int) -> bool:
    """Same-page requests send no Origin. Otherwise only this server's own page or a Chrome extension."""
    if not origin:
        return True
    return origin.startswith("chrome-extension://") or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def proposal_view(proposal: Proposal, founder: Founder) -> dict:
    evidence = {e.id: e for e in founder.evidence}
    cited = list(dict.fromkeys(i for s in proposal.sentences for i in s.evidence_ids))
    return {
        "id": proposal.id,
        "founder": {"id": founder.id, "name": founder.profile.display_name, "version": founder.profile.version},
        "decision": proposal.decision,
        "reason": proposal.reason,
        "reason_code": proposal.reason_code,
        "draft": " ".join(s.text for s in proposal.sentences),
        "sentences": [s.model_dump() for s in proposal.sentences],
        "evidence": [{"id": i, "text": evidence[i].text, "source": evidence[i].source} for i in cited if i in evidence],
        "checks": [c.model_dump() for c in proposal.checks if c.blocking],
        "warnings": [c.model_dump() for c in proposal.checks if not c.blocking and not c.passed],
    }


def _drafter(name: str | None):
    env = load_env()
    if name:
        if name not in DRAFTERS:
            raise ApiError(400, f"drafter must be one of {', '.join(DRAFTERS)}")
        env["MODEL_MODE"] = name
    return get_drafter(env)


def handle(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = urlparse(path)
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    body = body or {}
    try:
        if method == "GET" and url.path == "/api/founders":
            return 200, {"founders": [
                {"id": f, "name": learning.current_founder(f).profile.display_name,
                 "version": learning.current_founder(f).profile.version}
                for f in FOUNDERS if f in list_founders()]}

        if method == "GET" and url.path == "/api/feed":
            return 200, json.loads((FIXTURES_DIR / "feed.json").read_text())

        if method == "POST" and url.path == "/api/propose":
            text = (body.get("text") or "").strip()
            if not text:
                raise ApiError(400, "post text is required")
            founder = learning.current_founder(body.get("founder") or "")
            proposal = propose(post_from_text(text), founder, _drafter(body.get("drafter")))
            learning.save_proposal(proposal, text)
            return 200, proposal_view(proposal, founder)

        if method == "POST" and url.path == "/api/review":
            action = body.get("action")
            if action not in ("accept", "edit", "reject", "skip"):
                raise ApiError(400, "action must be accept, edit, reject, or skip")
            rv, suggestion = learning.review(body.get("proposal_id", ""), action, body.get("edited_text"))
            final = None
            if action == "accept":
                final = learning.draft_text(learning.get_proposal(rv.proposal_id))
            elif action == "edit":
                final = rv.edited_text
            return 200, {"review_id": rv.id, "action": action, "final_text": final,
                         "suggestion": suggestion.model_dump(mode="json") if suggestion else None}

        if method == "GET" and url.path == "/api/rules":
            founder = query.get("founder")
            rules = [r.model_dump(mode="json") for r in learning.rule_proposals(founder)]
            active = {f: learning.versions(f)[0] for f in ([founder] if founder else FOUNDERS)}
            return 200, {"rules": rules, "active_version": active}

        if method == "POST" and url.path in ("/api/rules/approve", "/api/rules/reject"):
            rule_id = body.get("id", "")
            if url.path.endswith("approve"):
                return 200, {"id": rule_id, "status": "approved", "version": learning.approve(rule_id)}
            learning.reject(rule_id)
            return 200, {"id": rule_id, "status": "rejected"}

        if method == "POST" and url.path == "/api/rules/revert":
            return 200, {"founder": body.get("founder"), "version": learning.revert(body.get("founder", ""))}

        raise ApiError(404, f"no route for {method} {url.path}")
    except ApiError as exc:
        return exc.status, {"error": str(exc)}
    except (DataError, learning.ReviewError) as exc:
        return 400, {"error": str(exc)}
    except ModelError as exc:
        return 503, {"error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    server_version = "DraftVoice"

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self.send_response(status)
        origin = self.headers.get("Origin")
        if origin and allowed_origin(origin, self.server.server_port):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _guard(self) -> bool:
        if allowed_origin(self.headers.get("Origin"), self.server.server_port):
            return True
        self._json(403, {"error": "requests from other websites are not allowed"})
        return False

    def do_OPTIONS(self):  # CORS preflight from the extension
        if not self._guard():
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
        self.send_header("Access-Control-Allow-Methods", "GET, POST")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if not self._guard():
            return
        if urlparse(self.path).path in ("/", "/feed"):
            self._send(200, (WEB / "feed.html").read_bytes(), "text/html; charset=utf-8")
            return
        self._json(*handle("GET", self.path))

    def do_POST(self):
        if not self._guard():
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "body must be JSON"})
            return
        self._json(*handle("POST", self.path, body))

    def log_message(self, fmt, *args):  # keep the terminal quiet; errors still surface in responses
        pass


def serve(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
