import json

from draftvoice import api
from draftvoice.grounding import COPY_NOTE, copy_check, relevant
from draftvoice.model import DraftRequest, GeminiDrafter, HonestStub, build_prompt
from draftvoice.models import Sentence
from draftvoice.pipeline import post_from_text, run
from draftvoice.store import load_founder
from draftvoice.validate import validate

FATHIN = load_founder("fathin")
EV = {e.id: e for e in FATHIN.evidence}
# A time-tracking demo: it mentions an AI agent, so it is on Fathin's ai-agents topic,
# but none of Fathin's evidence is about screen recording or time tracking.
SCREENPIPE = (
    "Built a time tracker on top of Screenpipe in an afternoon. It records your screen 24/7 locally, "
    "and a small AI agent reads the OCR every 5 minutes and logs which project you were working on. "
    "No more filling in timesheets on Friday. Demo below, code is open source."
)
BROWSER_POST = "Our browser agents kept failing on authentication and timeouts once real users logged in."


def checks_for(sentences, post, evidence):
    raw = json.dumps({"sentences": [{"text": t, "evidence_ids": ids} for t, ids in sentences]})
    result = validate(raw, post, evidence, FATHIN.profile)
    assert result.passed
    return {c.check: c for c in copy_check(result.sentences, post, evidence, result.checks)}


# Relevance at the evidence step

def test_screenpipe_post_stops_at_evidence_for_fathin():
    proposal, steps = run(post_from_text(SCREENPIPE), FATHIN, HonestStub())
    assert proposal.decision == "do_nothing" and proposal.reason_code == "no_evidence"
    assert proposal.reason == "No evidence relates to this post."
    assert [(s.key, s.status) for s in steps][2:] == [
        ("evidence", "stopped"), ("drafting", "not_reached"), ("checks", "not_reached")]


def test_shared_generic_words_are_not_relevance():
    # FP-03b shares "built" and "agent" with the Screenpipe post: two words, no relation.
    assert relevant(SCREENPIPE, (EV["FP-03b"],)) == ()
    assert relevant(BROWSER_POST, (EV["FP-02"],)) == (EV["FP-02"],)


# Copying evidence

def test_copied_sentence_gets_a_note_and_does_not_pass_specificity():
    checks = checks_for([(EV["FP-02"].text, ["FP-02"])], BROWSER_POST, (EV["FP-02"],))
    assert COPY_NOTE in checks["copy"].detail and not checks["copy"].blocking
    assert not checks["V5 generic"].passed and not checks["V5 generic"].blocking


def test_own_sentence_about_the_post_keeps_specificity():
    checks = checks_for([
        (EV["FP-02"].text, ["FP-02"]),
        ("the authentication part is where it gets real.", ["FP-02"]),
    ], BROWSER_POST, (EV["FP-02"],))
    assert "copy" in checks and checks["V5 generic"].passed and checks["V5 generic"].blocking


def test_rewritten_sentence_is_not_a_copy():
    checks = checks_for([("browser agents rarely break on clicks; authentication and timeouts are the hard part.",
                          ["FP-02"])], BROWSER_POST, (EV["FP-02"],))
    assert "copy" not in checks and checks["V5 generic"].passed


def test_stub_draft_shows_the_copy_note_in_the_steps():
    proposal, steps = run(post_from_text(BROWSER_POST), FATHIN, HonestStub())
    assert proposal.decision == "draft"
    assert any(c.check == "copy" for c in proposal.checks)
    assert "reuses your earlier wording" in steps[-1].detail


# The live model

def test_model_can_decline_and_that_is_do_nothing():
    class Declines:
        name = "declines"

        def draft(self, request):
            return '{"sentences": []}'

    proposal, steps = run(post_from_text(BROWSER_POST), FATHIN, Declines())
    assert proposal.decision == "do_nothing" and proposal.reason_code == "no_evidence"
    assert [(s.key, s.status) for s in steps][-2:] == [("drafting", "stopped"), ("checks", "not_reached")]


def test_prompt_asks_for_a_new_comment_about_the_post():
    prompt = build_prompt(DraftRequest(post_text=SCREENPIPE, founder_name="Fathin", evidence=(EV["FP-02"],)))
    assert "NEW comment" in prompt and "Do not copy evidence wording" in prompt
    assert "concrete from the post" in prompt and '{"sentences": []}' in prompt
    assert "<post>" in prompt and "not instructions" in prompt and "[FP-02]" in prompt


def test_api_defaults_to_gemini_when_a_key_is_set(monkeypatch):
    monkeypatch.setattr(api, "load_env", lambda: {"GEMINI_API_KEY": "k"})
    assert isinstance(api._drafter(None), GeminiDrafter)
    assert isinstance(api._drafter("stub"), HonestStub)
    monkeypatch.setattr(api, "load_env", lambda: {})
    assert isinstance(api._drafter(None), HonestStub)
