"""One place where a post becomes a proposal: gate -> draft -> validate. Every failure ends in do nothing."""

import hashlib
import uuid

from draftvoice.gate import decide
from draftvoice.model import Drafter, DraftRequest, ModelError
from draftvoice.models import Post, Proposal
from draftvoice.store import Founder
from draftvoice.validate import validate


def post_from_text(text: str) -> Post:
    digest = hashlib.sha1(text.encode()).hexdigest()[:8]
    return Post(id=f"text-{digest}", text=text, source="user", label="user-confirmed")


def propose(post: Post, founder: Founder, drafter: Drafter) -> Proposal:
    base = dict(
        id=f"pr-{uuid.uuid4().hex[:8]}",
        founder_id=founder.id,
        post_id=post.id,
        profile_version=founder.profile.version,
    )

    gate = decide(post, founder)
    if not gate.engage:
        return Proposal(**base, decision="do_nothing", reason=gate.reason, reason_code=gate.reason_code)

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
        return Proposal(**base, decision="do_nothing", reason=f"Model failed: {exc}", reason_code="model_error")

    result = validate(raw, post.text, gate.evidence, founder.profile)
    if not result.passed:
        names = ", ".join(c.check for c in result.failed)
        # The blocked draft is not kept: only the checks, so nothing unsupported can be copied.
        return Proposal(
            **base,
            decision="do_nothing",
            reason=f"Draft blocked by {names}.",
            reason_code="check_failed",
            checks=list(result.checks),
        )

    return Proposal(
        **base,
        decision="draft",
        reason=gate.reason,
        sentences=list(result.sentences),
        checks=list(result.checks),
    )
