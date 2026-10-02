import pytest

from draftvoice.cli import main
from draftvoice.model import DishonestStub, HonestStub, ModelError
from draftvoice.pipeline import post_from_text, propose
from draftvoice.store import FIXTURES_DIR, load_fixtures, load_founder

ALEX = load_founder("alex", FIXTURES_DIR / "founders")
FIXTURES = {f.post.id: f for f in load_fixtures()}


class BrokenModel:
    name = "broken"

    def draft(self, request):
        raise ModelError("timeout")


@pytest.mark.parametrize("post_id", list(FIXTURES))
def test_pipeline_matches_expected_decision(post_id):
    fixture = FIXTURES[post_id]
    proposal = propose(fixture.post, ALEX, HonestStub())
    assert proposal.decision == fixture.expected["alex"].decision
    assert proposal.reason


def test_draft_carries_evidence_and_checks():
    proposal = propose(FIXTURES["p-onboarding"].post, ALEX, HonestStub())
    assert proposal.sentences and all(s.evidence_ids for s in proposal.sentences)
    assert {c.check for c in proposal.checks if c.blocking} >= {
        "V1 evidence", "V2 numbers", "V3 names", "V4 first person", "V5 generic", "V6 repeats", "V7 format"}
    assert proposal.profile_version == ALEX.profile.version


def test_model_failure_becomes_do_nothing():
    proposal = propose(FIXTURES["p-onboarding"].post, ALEX, BrokenModel())
    assert proposal.decision == "do_nothing"
    assert proposal.reason_code == "model_error"


def test_blocked_draft_keeps_checks_but_not_the_text():
    proposal = propose(FIXTURES["p-onboarding"].post, ALEX, DishonestStub("number"))
    assert proposal.decision == "do_nothing"
    assert proposal.reason_code == "check_failed"
    assert "V2 numbers" in proposal.reason
    assert proposal.sentences == []


def test_skipped_posts_never_reach_the_model():
    class Spy(BrokenModel):
        called = False

        def draft(self, request):
            Spy.called = True
            return super().draft(request)

    propose(FIXTURES["p-offtopic"].post, ALEX, Spy())
    assert not Spy.called


def test_celebration_is_left_to_the_founder():
    proposal = propose(FIXTURES["p-celebration"].post, ALEX, HonestStub())
    assert proposal.reason_code == "celebration"


def test_pasted_text_gets_a_stable_id():
    assert post_from_text("hello").id == post_from_text("hello").id
    assert post_from_text("hello").label == "user-confirmed"


# CLI

def test_cli_drafts_for_a_fixture(capsys):
    assert main(["propose", "--founder", "alex", "--post", "p-onboarding", "--drafter", "stub"]) == 0
    out = capsys.readouterr().out
    assert "DRAFT" in out and "[ev-001]" in out and "Nothing was posted" in out


def test_cli_shows_the_blocking_check(capsys):
    main(["propose", "--founder", "alex", "--post", "p-agents", "--drafter", "dishonest-name"])
    out = capsys.readouterr().out
    assert "DO NOTHING" in out and "✗ V3 names" in out


def test_cli_routes_pasted_text_per_founder(capsys):
    text = "Founders: does your LinkedIn profile matter before an investor meeting?"
    main(["propose", "--founder", "rico", "--text", text, "--drafter", "stub"])
    rico = capsys.readouterr().out
    main(["propose", "--founder", "fathin", "--text", text, "--drafter", "stub"])
    fathin = capsys.readouterr().out
    assert "DRAFT" in rico
    assert "DO NOTHING" in fathin


def test_cli_rejects_unknown_founder(capsys):
    assert main(["propose", "--founder", "nobody", "--text", "x", "--drafter", "stub"]) == 2
    assert "unknown founder" in capsys.readouterr().err


def test_cli_needs_exactly_one_post_source():
    with pytest.raises(SystemExit):
        main(["propose", "--founder", "rico"])
    with pytest.raises(SystemExit):
        main(["propose", "--founder", "rico", "--text", "x", "--post", "p-agents"])
