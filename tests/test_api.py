import json
import threading
import urllib.error
import urllib.request

import pytest

from draftvoice.api import allowed_origin, handle, serve

LINKEDIN_POST = "Does your LinkedIn profile matter before an investor meeting?"


def post(path, body):
    return handle("POST", path, body)


def test_founders_and_feed():
    status, data = handle("GET", "/api/founders")
    assert status == 200 and {f["id"] for f in data["founders"]} == {"rico", "fathin"}
    status, feed = handle("GET", "/api/feed")
    assert status == 200 and len(feed["posts"]) >= 5


def test_propose_returns_draft_with_evidence_and_checks():
    status, p = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"})
    assert status == 200 and p["decision"] == "draft"
    assert p["evidence"] and all(e["source"] for e in p["evidence"])
    assert {c["check"].split()[0] for c in p["checks"]} >= {"V1", "V2", "V3", "V4", "V5", "V6", "V7"}


def test_same_post_differs_per_founder():
    _, rico = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"})
    _, fathin = post("/api/propose", {"founder": "fathin", "text": LINKEDIN_POST, "drafter": "stub"})
    assert rico["decision"] == "draft" and fathin["decision"] == "do_nothing"


def test_bad_requests_are_400():
    assert post("/api/propose", {"founder": "rico", "text": ""})[0] == 400
    assert post("/api/propose", {"founder": "nobody", "text": "x", "drafter": "stub"})[0] == 400
    assert post("/api/propose", {"founder": "rico", "text": "x", "drafter": "gpt"})[0] == 400
    assert post("/api/review", {"proposal_id": "pr-missing", "action": "accept"})[0] == 400
    assert handle("GET", "/api/nope")[0] == 404


def test_review_loop_through_the_api():
    edited = "if you're invisible you're harder to source fr"
    suggestion = None
    for _ in range(2):
        _, p = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"})
        status, r = post("/api/review", {"proposal_id": p["id"], "action": "edit", "edited_text": edited})
        assert status == 200 and r["final_text"] == edited
        suggestion = r["suggestion"] or suggestion
    assert suggestion is not None
    status, approved = post("/api/rules/approve", {"id": suggestion["id"]})
    assert status == 200 and approved["version"] == 2
    _, p = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"})
    assert p["founder"]["version"] == 2
    assert post("/api/rules/revert", {"founder": "rico"})[1]["version"] == 1


def test_only_local_page_and_extensions_are_allowed():
    assert allowed_origin(None, 8765)
    assert allowed_origin("http://127.0.0.1:8765", 8765)
    assert allowed_origin("chrome-extension://abcdefghijklmnop", 8765)
    assert not allowed_origin("https://www.linkedin.com", 8765)
    assert not allowed_origin("https://evil.example", 8765)


@pytest.fixture
def server():
    srv = serve(0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def request(url, body=None, origin=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
    try:
        with urllib.request.urlopen(req) as res:
            return res.status, res.read().decode(), dict(res.headers)
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode(), dict(err.headers)


def test_server_serves_the_feed_page(server):
    status, html, _ = request(server + "/")
    assert status == 200 and "DraftVoice" in html and "never posts" in html


def test_server_refuses_other_websites(server):
    status, body, _ = request(server + "/api/propose", {"founder": "rico", "text": LINKEDIN_POST},
                              origin="https://evil.example")
    assert status == 403 and "not allowed" in body


def test_server_allows_the_extension(server):
    status, body, headers = request(server + "/api/propose",
                                    {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"},
                                    origin="chrome-extension://abc")
    assert status == 200 and json.loads(body)["decision"] == "draft"
    assert headers["Access-Control-Allow-Origin"] == "chrome-extension://abc"


# Steps: the real outcome of each stage, stopping where the run stopped

def steps_of(view):
    return [(s["key"], s["status"]) for s in view["steps"]]


def test_steps_for_a_draft_are_all_done():
    _, view = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub", "author": "Mara Lind"})
    assert steps_of(view) == [(k, "done") for k in ("reading", "topics", "evidence", "drafting", "checks")]
    assert "RP-20" in view["steps"][2]["detail"]
    assert view["post"]["author"] == "Mara Lind"


def test_steps_stop_at_the_topic_step():
    _, view = post("/api/propose", {"founder": "rico", "text": "Excited to announce we just joined Y Combinator!",
                                    "drafter": "stub"})
    assert steps_of(view) == [("reading", "done"), ("topics", "stopped"), ("evidence", "not_reached"),
                              ("drafting", "not_reached"), ("checks", "not_reached")]
    assert "milestone" in view["steps"][1]["detail"]
    assert view["can_override"]


def test_steps_stop_at_the_evidence_step():
    _, view = post("/api/propose", {"founder": "fathin", "text": "AI comments are ruining LinkedIn.", "drafter": "stub"})
    assert ("evidence", "stopped") in steps_of(view)
    assert view["reason_code"] == "no_evidence"


def test_steps_stop_at_the_checks_step(monkeypatch):
    from draftvoice import api
    from draftvoice.model import DishonestStub
    monkeypatch.setattr(api, "_drafter", lambda name: DishonestStub("number"))
    _, view = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST})
    assert steps_of(view)[-1] == ("checks", "stopped")
    assert "V2 numbers" in view["steps"][-1]["detail"] and view["draft"] == ""


def test_steps_stop_at_drafting_when_the_model_fails(monkeypatch):
    from draftvoice import api
    from draftvoice.model import ModelError

    class Down:
        name = "down"

        def draft(self, request):
            raise ModelError("503")

    monkeypatch.setattr(api, "_drafter", lambda name: Down())
    _, view = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST})
    assert steps_of(view)[-2:] == [("drafting", "stopped"), ("checks", "not_reached")]


def test_draft_anyway_overrules_the_gate_but_not_the_checks():
    text = "Excited to announce we just joined Y Combinator! Turns out being invisible on LinkedIn makes you harder to source."
    _, skipped = post("/api/propose", {"founder": "rico", "text": text, "drafter": "stub"})
    assert skipped["decision"] == "do_nothing"
    _, forced = post("/api/propose", {"founder": "rico", "text": text, "drafter": "stub", "override": True})
    assert forced["decision"] == "draft"
    assert "Overruled by you. The gate said: A milestone post" in forced["steps"][1]["detail"]
    assert all(c["passed"] for c in forced["checks"])  # the validators still ran


def test_draft_anyway_without_any_matching_evidence_still_does_nothing():
    _, view = post("/api/propose", {"founder": "fathin", "text": "Won our first padel tournament this weekend.",
                                    "drafter": "stub", "override": True})
    assert view["decision"] == "do_nothing" and ("evidence", "stopped") in steps_of(view)


def test_rules_reject_through_the_api():
    edited = "if you're invisible you're harder to source fr"
    suggestion = None
    for _ in range(2):
        _, p = post("/api/propose", {"founder": "rico", "text": LINKEDIN_POST, "drafter": "stub"})
        suggestion = post("/api/review", {"proposal_id": p["id"], "action": "edit", "edited_text": edited})[1]["suggestion"] or suggestion
    assert post("/api/rules/reject", {"id": suggestion["id"]})[1]["status"] == "rejected"
    status, rules = handle("GET", "/api/rules?founder=rico")
    assert status == 200 and rules["rules"][0]["status"] == "rejected" and rules["active_version"] == {"rico": 1}


# The shared review panel

def test_server_serves_the_panel_files(server):
    for name, kind in [("panel.html", "text/html"), ("panel.css", "text/css"), ("panel.js", "text/javascript")]:
        status, body, headers = request(f"{server}/{name}")
        assert status == 200 and headers["Content-Type"].startswith(kind) and body


def test_server_only_serves_known_files(server):
    assert request(server + "/../pyproject.toml")[0] == 404
    assert request(server + "/api.py")[0] == 404


def test_panel_has_no_inline_scripts_or_handlers():
    # Extension pages (MV3) block inline scripts and inline event handlers.
    import re
    from draftvoice.api import WEB
    html = (WEB / "panel.html").read_text()
    assert re.findall(r"<script[^>]*>", html) == ['<script src="panel.js">']
    assert not re.search(r"\son[a-z]+=", html)
    assert "Nothing is sent to LinkedIn." in html and "untrusted input" in html
