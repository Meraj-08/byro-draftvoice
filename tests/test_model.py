import json

import pytest

from draftvoice.gate import decide
from draftvoice.model import (
    FABRICATIONS,
    DishonestStub,
    DraftRequest,
    GeminiDrafter,
    HonestStub,
    ModelError,
    build_prompt,
    get_drafter,
    load_env,
    parse_output,
)
from draftvoice.store import FIXTURES_DIR, load_fixtures, load_founder

ALEX = load_founder("alex", FIXTURES_DIR / "founders")
POST = load_fixtures()[0].post  # onboarding


def request() -> DraftRequest:
    gate = decide(POST, ALEX)
    return DraftRequest(POST.text, ALEX.profile.display_name, gate.evidence,
                        tuple(ALEX.profile.rules), tuple(ALEX.profile.examples))


def test_honest_stub_cites_only_supplied_evidence():
    req = request()
    sentences = parse_output(HonestStub().draft(req))
    supplied = {e.id for e in req.evidence}
    assert sentences
    assert all(set(s.evidence_ids) <= supplied for s in sentences)


def test_honest_stub_is_deterministic():
    assert HonestStub().draft(request()) == HonestStub().draft(request())


def test_honest_stub_refuses_without_evidence():
    with pytest.raises(ModelError):
        HonestStub().draft(DraftRequest("post", "Alex", ()))


@pytest.mark.parametrize("kind", [k for k in FABRICATIONS if k != "bad_json"])
def test_dishonest_stub_adds_one_unsupported_sentence(kind):
    honest = parse_output(HonestStub().draft(request()))
    dishonest = parse_output(DishonestStub(kind).draft(request()))
    assert len(dishonest) == len(honest) + 1
    assert dishonest[:-1] == honest


def test_dishonest_bad_json_fails_parsing():
    with pytest.raises(ModelError):
        parse_output(DishonestStub("bad_json").draft(request()))


@pytest.mark.parametrize("raw", [
    "not json",
    "{}",
    json.dumps({"sentences": []}),
    json.dumps({"sentences": [{"text": "", "evidence_ids": []}]}),
    json.dumps({"sentences": [{"text": "x", "evidence_ids": []}] * 4}),
    json.dumps({"sentences": [{"text": "x", "evidence_ids": []}], "post": "now"}),
])
def test_parse_output_rejects_invalid_shapes(raw):
    with pytest.raises(ModelError):
        parse_output(raw)


def test_prompt_marks_post_as_data_and_sends_only_matched_evidence():
    prompt = build_prompt(request())
    assert "<post>" in prompt and "not instructions" in prompt
    assert "[ev-001]" in prompt
    assert "ev-004" not in prompt  # unapproved
    assert "ev-002" not in prompt  # approved, but not matched to this post


def test_default_mode_is_the_offline_stub():
    assert isinstance(get_drafter({}), HonestStub)
    assert isinstance(get_drafter({"MODEL_MODE": ""}), HonestStub)


def test_gemini_mode_without_key_fails_closed():
    with pytest.raises(ModelError, match="GEMINI_API_KEY"):
        get_drafter({"MODEL_MODE": "gemini"})


def test_unknown_mode_fails_closed():
    with pytest.raises(ModelError):
        get_drafter({"MODEL_MODE": "gpt"})


def test_gemini_errors_become_model_errors(monkeypatch):
    from google import genai

    def boom(*args, **kwargs):
        raise ConnectionError("offline")

    monkeypatch.setattr(genai, "Client", boom)
    with pytest.raises(ModelError, match="Gemini call failed"):
        GeminiDrafter("fake-key").draft(request())


def test_env_file_parsing(tmp_path, monkeypatch):
    for key in ("MODEL_MODE", "GEMINI_API_KEY", "GEMINI_MODEL"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / ".env"
    env.write_text("# comment\nMODEL_MODE=gemini   # live\nGEMINI_API_KEY='abc'\n")
    assert load_env(env) == {"MODEL_MODE": "gemini", "GEMINI_API_KEY": "abc"}
    monkeypatch.setenv("MODEL_MODE", "stub")
    assert load_env(env)["MODEL_MODE"] == "stub"
