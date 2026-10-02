import json

import pytest

from draftvoice.gate import decide
from draftvoice.model import EXPECTED_CHECK, FABRICATIONS, DishonestStub, DraftRequest, HonestStub
from draftvoice.models import Evidence, Rule, VoiceCheck, VoiceProfile
from draftvoice.store import FIXTURES_DIR, load_fixtures, load_founder
from draftvoice.validate import validate

ALEX = load_founder("alex", FIXTURES_DIR / "founders")
ENGAGED = [f for f in load_fixtures() if f.expected["alex"].decision == "draft"]


def gate_and_request(fixture):
    gate = decide(fixture.post, ALEX)
    req = DraftRequest(fixture.post.text, "Alex", gate.evidence,
                       tuple(ALEX.profile.rules), tuple(ALEX.profile.examples))
    return gate, req


def draft(*sentences):
    return json.dumps({"sentences": [{"text": t, "evidence_ids": ids} for t, ids in sentences]})


def check(raw, post="A post about onboarding new customers.", evidence=None, profile=None):
    evidence = evidence if evidence is not None else ALEX.evidence
    return validate(raw, post, evidence, profile or ALEX.profile)


def failed(v):
    return {c.check for c in v.failed}


@pytest.mark.parametrize("fixture", ENGAGED, ids=lambda f: f.post.id)
def test_honest_drafts_pass(fixture):
    gate, req = gate_and_request(fixture)
    v = validate(HonestStub().draft(req), fixture.post.text, gate.evidence, ALEX.profile)
    assert v.passed, v.failed


@pytest.mark.parametrize("kind", list(FABRICATIONS))
@pytest.mark.parametrize("fixture", ENGAGED, ids=lambda f: f.post.id)
def test_each_fabrication_is_blocked_by_its_own_check(fixture, kind):
    gate, req = gate_and_request(fixture)
    v = validate(DishonestStub(kind).draft(req), fixture.post.text, gate.evidence, ALEX.profile)
    assert not v.passed
    assert failed(v) == {EXPECTED_CHECK[kind]}


# V1 evidence
def test_uncited_sentence_is_blocked():
    assert "V1 evidence" in failed(check(draft(("Onboarding is hard.", []))))


def test_unapproved_evidence_cannot_be_cited():
    raw = draft(("We grew revenue 4x last year after automating onboarding.", ["ev-004"]))
    assert "V1 evidence" in failed(check(raw))


def test_evidence_not_matched_to_this_post_cannot_be_cited():
    onboarding_only = tuple(e for e in ALEX.evidence if e.id == "ev-001")
    raw = draft(("Agents should stop before billing.", ["ev-002"]))
    assert "V1 evidence" in failed(check(raw, evidence=onboarding_only))


# V2 numbers
def test_numbers_from_the_evidence_pass():
    raw = draft(("We went from 14 days to 3 for onboarding new customers.", ["ev-001"]))
    assert "V2 numbers" not in failed(check(raw))


def test_number_words_are_checked_too():
    raw = draft(("Onboarding took us twenty days.", ["ev-001"]))
    assert "V2 numbers" in failed(check(raw))


def test_numbers_quoted_from_the_post_pass():
    raw = draft(("312% is a big jump for onboarding.", ["ev-001"]))
    assert "V2 numbers" not in failed(check(raw, post="Our onboarding activation rose 312%."))


# V3 names
def test_names_from_the_post_pass():
    raw = draft(("Acme is right about onboarding.", ["ev-001"]))
    assert "V3 names" not in failed(check(raw, post="Acme shared how they do onboarding."))


def test_links_and_handles_need_a_source():
    raw = draft(("See getwidget.io for onboarding.", ["ev-001"]))
    assert "V3 names" in failed(check(raw))


# V4 first person
def test_first_person_claim_backed_by_evidence_passes():
    raw = draft(("We pair each new customer with an engineer for their first week.", ["ev-001"]))
    assert "V4 first person" not in failed(check(raw))


def test_first_person_cannot_lean_on_voice_only_evidence():
    voice = Evidence(id="v-1", founder_id="alex", text="We ship every Friday.",
                     topics=["onboarding"], use="voice", source="test", label="synthetic", approved=True)
    raw = draft(("We ship every Friday.", ["v-1"]))
    assert "V4 first person" in failed(check(raw, evidence=(voice,)))


# V5 generic
def test_stock_phrases_are_blocked():
    raw = draft(("Great post, thanks for sharing! Onboarding matters.", ["ev-001"]))
    assert "V5 generic" in failed(check(raw))


# V6 repeats
def test_repeating_a_recent_comment_is_blocked():
    raw = draft(("Agents should stop and ask before anything that touches money.", ["ev-002"]))
    assert "V6 repeats" in failed(check(raw))


# V7 format
def test_overlong_draft_is_blocked():
    raw = draft(("Onboarding " + "matters a lot " * 60, ["ev-001"]))
    assert "V7 format" in failed(check(raw))


# Voice rules warn, never block
def test_voice_rules_warn_but_do_not_block():
    profile = VoiceProfile(founder_id="alex", display_name="Alex", version=1, topics={},
                           rules=[Rule(id="r-x", text="lowercase, short",
                                       check=VoiceCheck(max_words=3, lowercase=True, max_emoji=0))])
    v = check(draft(("Onboarding customers takes a week 🚀", ["ev-001"])), profile=profile)
    assert v.passed
    assert [w.check for w in v.warnings] == ["voice r-x"]
    assert "words" in v.warnings[0].detail and "emoji" in v.warnings[0].detail


def test_names_mid_sentence_and_multiword_names_are_caught():
    assert "V3 names" in failed(check(draft(("Onboarding at Stripe takes a week.", ["ev-001"]))))
    assert "V3 names" in failed(check(draft(("Goldman Sachs does onboarding well.", ["ev-001"]))))
    assert "V3 names" in failed(check(draft(("OpenAI does onboarding well.", ["ev-001"]))))


def test_known_gap_single_name_starting_a_sentence_passes():
    # A one-word name as the first word looks like any sentence start. Reported in eval.
    assert "V3 names" not in failed(check(draft(("Stripe does onboarding well.", ["ev-001"]))))


def test_known_gap_vague_unsupported_claim_passes():
    # No number, name, or first person: the checks cannot tell this is unsupported. Reported in eval.
    raw = draft(("Most onboarding problems disappear once activation is measured.", ["ev-001"]))
    assert check(raw).passed


def test_rico_real_evidence_passes_honest_stub():
    rico = load_founder("rico")
    from draftvoice.models import Post
    post = Post(id="x", text="Does your LinkedIn profile matter before an investor meeting?",
                source="user", label="user-confirmed")
    gate = decide(post, rico)
    req = DraftRequest(post.text, "Rico", gate.evidence, tuple(rico.profile.rules), tuple(rico.profile.examples))
    v = validate(HonestStub().draft(req), post.text, gate.evidence, rico.profile)
    assert v.passed, v.failed
