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
