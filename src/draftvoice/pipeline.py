"""One place where a post becomes a proposal: gate -> draft -> validate. Every failure ends in do nothing."""

import hashlib
import uuid

import json
from dataclasses import dataclass

from draftvoice.gate import MAX_EVIDENCE, GateResult, decide
from draftvoice.grounding import copy_check, relevant
from draftvoice.model import Drafter, DraftRequest, ModelError, declined
from draftvoice.models import Post, Proposal
from draftvoice.store import Founder
from draftvoice.validate import content_words, validate

# The gate decided; these reasons mean the founder can still ask for a draft ("Draft anyway").
OVERRIDABLE = ("off_topic", "celebration", "no_evidence", "sensitive")
OVERRIDE_MIN_SHARED = 2


def post_from_text(text: str) -> Post:
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    return Post(id=f"text-{digest}", text=text, source="user", label="user-confirmed")


@dataclass(frozen=True)
class Step:
    """One stage of the run, as it really happened. status: done, stopped, or not_reached."""

    key: str
    label: str
    status: str
    detail: str


def _override_evidence(post: Post, founder: Founder):
    """When the founder overrules the gate: their approved claim evidence that shares the most words
    with the post, at least two (one shared word like "first" is not relevance). The validators
    still check the draft against it."""
    words = content_words(post.text)
    shared = lambda e: len(content_words(e.text) & words)
    ranked = sorted((e for e in founder.evidence if e.use != "voice"), key=lambda e: (-shared(e), e.id))
    return tuple(e for e in ranked if shared(e) >= OVERRIDE_MIN_SHARED)[:MAX_EVIDENCE]


def propose(post: Post, founder: Founder, drafter: Drafter, override: bool = False) -> Proposal:
    return run(post, founder, drafter, override)[0]


def run(post: Post, founder: Founder, drafter: Drafter, override: bool = False) -> tuple[Proposal, list[Step]]:
    """The proposal plus the steps that produced it, stopping where the run stopped."""
    base = dict(
        id=f"pr-{uuid.uuid4().hex[:8]}",
        founder_id=founder.id,
        post_id=post.id,
        profile_version=founder.profile.version,
    )

    words = len(post.text.split())
    steps = [Step("reading", "Reading the post", "done", f"{words} words, treated as data, not instructions")]

    def stop(key, label, detail, proposal):
        steps.append(Step(key, label, "stopped", detail))
        order = ["reading", "topics", "evidence", "drafting", "checks"]
        for k in order[order.index(key) + 1:]:
            steps.append(Step(k, LABELS[k], "not_reached", ""))
        return proposal, steps

    gate = decide(post, founder)
    if gate.reason_code == "celebration" and not override:
        return _react(post, founder, gate, base, steps, stop)
    overruled = override and not gate.engage and gate.reason_code in OVERRIDABLE
    original_reason = gate.reason
    if overruled:
        gate = GateResult(True, f"Drafted at your request. The gate said: {gate.reason}", None,
                          gate.topics, _override_evidence(post, founder))

    if not gate.engage and gate.reason_code != "no_evidence":
        return stop("topics", LABELS["topics"], gate.reason,
                    Proposal(**base, decision="do_nothing", reason=gate.reason, reason_code=gate.reason_code))
    if overruled:
        topic_note = f"Overruled by you. The gate said: {original_reason}"
    else:
        topic_note = f"On topic: {', '.join(gate.topics)}"
    steps.append(Step("topics", LABELS["topics"], "done", topic_note))

    if not gate.engage or not gate.evidence:
        reason = gate.reason if not gate.engage else "No approved evidence shares anything with this post."
        return stop("evidence", LABELS["evidence"], reason,
                    Proposal(**base, decision="do_nothing", reason=reason, reason_code="no_evidence"))
    # The gate ranks by shared words but keeps its best even when that is only "agent".
    evidence = relevant(post.text, gate.evidence)
    if not evidence:
        reason = "No evidence relates to this post."
        return stop("evidence", LABELS["evidence"], reason,
                    Proposal(**base, decision="do_nothing", reason=reason, reason_code="no_evidence"))
    steps.append(Step("evidence", LABELS["evidence"], "done",
                      f"{len(evidence)} approved item(s): {', '.join(e.id for e in evidence)}"))

    request = DraftRequest(
        post_text=post.text,
        founder_name=founder.profile.display_name,
        evidence=evidence,
        rules=tuple(founder.profile.rules),
        examples=tuple(founder.profile.examples),
    )
    try:
        raw = drafter.draft(request)
    except ModelError as exc:
        reason = f"Model failed: {exc}"
        return stop("drafting", LABELS["drafting"], reason,
                    Proposal(**base, decision="do_nothing", reason=reason, reason_code="model_error"))
    if declined(raw):
        reason = "The model found no point in the evidence that responds to this post."
        return stop("drafting", LABELS["drafting"], reason,
                    Proposal(**base, decision="do_nothing", reason=reason, reason_code="no_evidence"))
    writer = ("the offline test writer, which pastes evidence; turn on Live model for a real draft"
              if drafter.name == "honest-stub" else drafter.name)
    steps.append(Step("drafting", LABELS["drafting"], "done", f"Drafted by {writer}"))

    result = validate(raw, post.text, evidence, founder.profile)
    if not result.passed:
        names = ", ".join(c.check for c in result.failed)
        # The blocked draft is not kept: only the checks, so nothing unsupported can be copied.
        reason = f"Draft blocked by {names}."
        return stop("checks", LABELS["checks"], reason, Proposal(
            **base,
            decision="do_nothing",
            reason=reason,
            reason_code="check_failed",
            checks=list(result.checks),
        ))

    checks = copy_check(result.sentences, post.text, evidence, result.checks)
    specific = all(c.passed for c in checks if c.check == "V5 generic")
    notes = sum(1 for c in checks if not c.blocking and not c.passed and c.check.startswith("voice"))
    summary = "V1–V7 passed" if specific else "V1–V4, V6–V7 passed; V5 not met: reuses your earlier wording"
    if any(c.check == "copy" for c in checks) and specific:
        summary += ", reuses your earlier wording"
    steps.append(Step("checks", LABELS["checks"], "done",
                      summary + (f", {notes} voice note(s)" if notes else "")))
    return Proposal(
        **base,
        decision="draft",
        reason=gate.reason,
        sentences=list(result.sentences),
        checks=checks,
    ), steps


def _react(post: Post, founder: Founder, gate: GateResult, base: dict, steps: list, stop):
    """Milestone posts get one of the founder's own past reactions, not a written comment (finding K1).
    No model is called. The reaction still has to pass every check against the evidence it cites."""
    name = founder.profile.display_name
    approved = {e.id: e for e in founder.evidence}
    # Reactions written for this kind of milestone first, then general ones.
    fitting = [r for r in founder.profile.reactions
               if r.evidence_id in approved and (gate.occasion in r.occasions or "milestone" in r.occasions)]
    fitting.sort(key=lambda r: gate.occasion not in r.occasions)
    for reaction in fitting:
        evidence = (approved[reaction.evidence_id],)
        raw = json.dumps({"sentences": [{"text": reaction.text, "evidence_ids": [reaction.evidence_id]}]})
        result = validate(raw, post.text, evidence, founder.profile)
        if not result.passed:
            continue
        steps.append(Step("topics", LABELS["topics"], "done",
                          f"A milestone ({gate.occasion}). {name} usually answers these with a short reaction."))
        steps.append(Step("evidence", LABELS["evidence"], "done",
                          f"{name}'s own past reaction: {reaction.evidence_id}"))
        steps.append(Step("drafting", LABELS["drafting"], "done",
                          f"Picked from {name}'s past reactions; no model was used"))
        steps.append(Step("checks", LABELS["checks"], "done", "V1–V7 passed"))
        return Proposal(
            **base, decision="draft",
            reason=f"A milestone post. Suggested: a reaction {name} has written before.",
            sentences=list(result.sentences), checks=list(result.checks),
        ), steps
    reason = (f"A milestone post. {name} has no recorded reaction for this kind of post, "
              "so a cheer is better written by them.")
    return stop("topics", LABELS["topics"], reason,
                Proposal(**base, decision="do_nothing", reason=reason, reason_code="celebration"))


LABELS = {
    "reading": "Reading the post",
    "topics": "Checking topic and tone",
    "evidence": "Finding approved evidence",
    "drafting": "Drafting",
    "checks": "Checking every claim",
}
