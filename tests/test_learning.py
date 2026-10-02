import hashlib
from pathlib import Path

import pytest

from draftvoice import learning
from draftvoice.cli import main
from draftvoice.model import HonestStub
from draftvoice.pipeline import post_from_text, propose
from draftvoice.store import DATA_DIR

POST = "Does your LinkedIn profile matter before an investor meeting?"
SHORT = "if you're invisible you're harder to source fr"


def drafted(founder_id="rico", text=POST):
    founder = learning.current_founder(founder_id)
    proposal = propose(post_from_text(text), founder, HonestStub())
    learning.save_proposal(proposal, text)
    return proposal


def edit(text=SHORT, founder_id="rico"):
    return learning.review(drafted(founder_id).id, "edit", text)


# reviews

def test_accept_and_edit_are_saved_append_only():
    learning.review(drafted().id, "accept")
    learning.review(drafted().id, "edit", SHORT)
    log = (Path(learning.home()) / "reviews.jsonl").read_text().splitlines()
    assert len(log) == 2
    assert '"action": "accept"' in log[0] and SHORT in log[1]


def test_cannot_accept_when_draftvoice_proposed_nothing():
    proposal = drafted(text="Excited to announce we just joined Y Combinator!")
    with pytest.raises(learning.ReviewError):
        learning.review(proposal.id, "accept")
    learning.review(proposal.id, "skip")  # skipping is always allowed


def test_a_proposal_is_reviewed_once():
    proposal = drafted()
    learning.review(proposal.id, "reject")
    with pytest.raises(learning.ReviewError, match="already reviewed"):
        learning.review(proposal.id, "accept")


def test_edit_needs_text():
    with pytest.raises(learning.ReviewError):
        learning.review(drafted().id, "edit", "  ")


# learning

def test_signals_describe_the_edit_in_check_terms():
    s = learning.signals("We pair every customer with an engineer. It works 🚀 #onboarding",
                         "we pair customers with engineers")
    assert s == {"max_words": 5, "max_sentences": 1, "lowercase": True, "max_emoji": 0, "no_hashtags": True}
    assert learning.signals("same words here", "same words here") == {}


def test_one_edit_never_makes_a_rule():
    _, suggestion = edit()
    assert suggestion is None
    assert learning.rule_proposals("rico") == []


def test_two_matching_edits_suggest_one_rule():
    edit()
    _, suggestion = edit()
    assert suggestion is not None
    assert suggestion.check.max_words == len(SHORT.split())
    assert suggestion.status == "suggested" and len(suggestion.source_review_ids) == 2
    _, third = edit()
    assert third is None  # no duplicate while one is pending


def test_different_changes_do_not_add_up():
    edit()  # shortened
    proposal = drafted()
    reworded = learning.draft_text(proposal).replace("linkedin", "profile")  # same length, one word changed
    _, suggestion = learning.review(proposal.id, "edit", reworded)
    assert suggestion is None


def test_founders_learn_separately():
    edit(founder_id="rico")
    fathin_post = "Our AI agent says the task is done, but nobody can verify it actually finished."
    proposal = drafted("fathin", fathin_post)
    _, suggestion = learning.review(proposal.id, "edit", "Prove it finished.")
    assert suggestion is None


# approval, versions, revert

def test_nothing_changes_until_approved():
    edit()
    edit()
    assert learning.current_founder("rico").profile.version == 1


def test_approve_creates_a_new_version_that_drafts_use():
    edit()
    _, suggestion = edit()
    version = learning.approve(suggestion.id)
    rico = learning.current_founder("rico")
    assert version == 2 and rico.profile.version == 2
    assert rico.profile.rules[-1].origin == "learned"
    proposal = drafted()
    assert proposal.profile_version == 2
    assert any(c.check == "voice r-learned-2" for c in proposal.checks)


def test_revert_goes_back_and_marks_the_rule():
    edit()
    _, suggestion = edit()
    learning.approve(suggestion.id)
    assert learning.revert("rico") == 1
    assert learning.current_founder("rico").profile.version == 1
    assert learning.rule_proposals("rico")[0].status == "reverted"
    with pytest.raises(learning.ReviewError):
        learning.revert("rico")


def test_reject_changes_nothing():
    edit()
    _, suggestion = edit()
    learning.reject(suggestion.id)
    assert learning.current_founder("rico").profile.version == 1
    with pytest.raises(learning.ReviewError):
        learning.approve(suggestion.id)


def test_founder_data_files_are_never_modified():
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA_DIR.rglob("*.json")}
    edit()
    _, suggestion = edit()
    learning.approve(suggestion.id)
    learning.revert("rico")
    assert before == {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA_DIR.rglob("*.json")}


# CLI

def test_cli_review_loop(capsys):
    for _ in range(2):
        main(["propose", "--founder", "rico", "--text", POST, "--drafter", "stub"])
        proposal_id = capsys.readouterr().out.split("draftvoice review ")[1].split()[0]
        assert main(["review", proposal_id, "--edit", SHORT]) == 0
    out = capsys.readouterr().out
    assert "Ready to copy" in out and "Suggested rule" in out
    rule_id = out.split("rules approve ")[1].split()[0]
    assert main(["rules", "approve", rule_id]) == 0
    assert "version 2" in capsys.readouterr().out
    assert main(["rules"]) == 0
    assert "active profile v2" in capsys.readouterr().out
    assert main(["rules", "revert", "--founder", "rico"]) == 0
    assert main(["rules", "revert", "--founder", "rico"]) == 2
