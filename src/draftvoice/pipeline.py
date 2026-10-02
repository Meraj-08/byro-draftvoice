"""One place where a post becomes a proposal: gate -> draft -> validate. Every failure ends in do nothing."""

import hashlib
import uuid

from dataclasses import dataclass

from draftvoice.gate import MAX_EVIDENCE, GateResult, decide
from draftvoice.model import Drafter, DraftRequest, ModelError
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
    steps.append(Step("evidence", LABELS["evidence"], "done",
                      f"{len(gate.evidence)} approved item(s): {', '.join(e.id for e in gate.evidence)}"))

    request = DraftRequest(
        post_text=post.text,
        founder_name=founder.profile.display_name,
        evidence=gate.evidence,
        rules=tuple(founder.profile.rules),
        examples=tuple(founder.profile.examples),
    )
    try:
        raw = drafter.draft(request)
    except ModelError as exc:
        reason = f"Model failed: {exc}"
        return stop("drafting", LABELS["drafting"], reason,
                    Proposal(**base, decision="do_nothing", reason=reason, reason_code="model_error"))
    steps.append(Step("drafting", LABELS["drafting"], "done", f"Drafted by {drafter.name}"))

    result = validate(raw, post.text, gate.evidence, founder.profile)
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

    notes = len(result.warnings)
    steps.append(Step("checks", LABELS["checks"], "done",
                      "V1–V7 passed" + (f", {notes} voice note(s)" if notes else "")))
    return Proposal(
        **base,
        decision="draft",
        reason=gate.reason,
        sentences=list(result.sentences),
        checks=list(result.checks),
    ), steps


LABELS = {
    "reading": "Reading the post",
    "topics": "Checking topic and tone",
    "evidence": "Finding approved evidence",
    "drafting": "Drafting",
    "checks": "Checking every claim",
}
