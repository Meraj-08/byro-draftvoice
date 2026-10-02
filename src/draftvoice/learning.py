"""Reviews, rule suggestions, and profile versions. The founder approves every change.

Everything is append-only JSONL under DRAFTVOICE_HOME (default .draftvoice/). Profile versions are
immutable files; "active" is a pointer, so revert only moves the pointer back. The founder data in
data/founders/ is never modified: it is version 1.
"""

import json
import os
import re
import uuid
from pathlib import Path

from draftvoice.models import Proposal, Review, Rule, RuleProposal, VoiceCheck, VoiceProfile
from draftvoice.store import ROOT, Founder, find_founder
from draftvoice.validate import EMOJI

# One edit never makes a rule.
EDITS_FOR_A_RULE = 2
SHORTER = 0.7  # an edit "shortens" a draft when it keeps at most 70% of the words


class ReviewError(ValueError):
    pass


def home() -> Path:
    path = Path(os.environ.get("DRAFTVOICE_HOME", ROOT / ".draftvoice"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _append(name: str, record: dict) -> None:
    with (home() / name).open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _read(name: str) -> list[dict]:
    path = home() / name
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


# ---------- profile versions ----------

def _profile_dir(founder_id: str) -> Path:
    path = home() / "profiles" / founder_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _history(founder_id: str) -> list[int]:
    path = _profile_dir(founder_id) / "history.json"
    return json.loads(path.read_text()) if path.exists() else [1]


def current_founder(founder_id: str) -> Founder:
    """The founder with their active profile version applied."""
    base = find_founder(founder_id)
    version = _history(founder_id)[-1]
    if version == 1:
        return base
    profile = VoiceProfile.model_validate_json((_profile_dir(founder_id) / f"v{version}.json").read_text())
    return Founder(profile, base.evidence)


def _activate(founder_id: str, version: int) -> None:
    history = _history(founder_id) + [version]
    (_profile_dir(founder_id) / "history.json").write_text(json.dumps(history))


# ---------- proposals and reviews ----------

def save_proposal(proposal: Proposal, post_text: str) -> None:
    _append("proposals.jsonl", {"proposal": proposal.model_dump(mode="json"), "post_text": post_text})


def get_proposal(proposal_id: str) -> Proposal:
    for record in reversed(_read("proposals.jsonl")):
        if record["proposal"]["id"] == proposal_id:
            return Proposal.model_validate(record["proposal"])
    raise ReviewError(f"unknown proposal '{proposal_id}'")


def draft_text(proposal: Proposal) -> str:
    return " ".join(s.text for s in proposal.sentences)


def review(proposal_id: str, action: str, edited_text: str | None = None) -> tuple[Review, RuleProposal | None]:
    """Save the founder's decision. Returns the review and, if this edit repeats an earlier one, a suggested rule."""
    proposal = get_proposal(proposal_id)
    if action in ("accept", "edit") and proposal.decision != "draft":
        raise ReviewError("there is no draft to accept or edit; DraftVoice proposed doing nothing")
    if action == "edit" and not (edited_text and edited_text.strip()):
        raise ReviewError("an edit needs the edited text")
    if any(r["proposal_id"] == proposal_id for r in _read("reviews.jsonl")):
        raise ReviewError(f"proposal '{proposal_id}' was already reviewed")
    rv = Review(id=f"rv-{uuid.uuid4().hex[:8]}", proposal_id=proposal_id, action=action,
                edited_text=edited_text.strip() if action == "edit" else None)
    _append("reviews.jsonl", {**rv.model_dump(mode="json"), "founder_id": proposal.founder_id,
                              "draft_text": draft_text(proposal)})
    return rv, (_suggest(proposal.founder_id) if action == "edit" else None)


# ---------- learning ----------

def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def signals(draft: str, edited: str) -> dict[str, int | bool]:
    """What an edit changed, in terms the voice checks understand."""
    out: dict[str, int | bool] = {}
    d_words, e_words = len(draft.split()), len(edited.split())
    if e_words <= SHORTER * d_words and d_words - e_words >= 3:
        out["max_words"] = e_words
    d_sent, e_sent = _sentences(draft), _sentences(edited)
    if len(e_sent) < len(d_sent):
        out["max_sentences"] = len(e_sent)
    if any(s[:1].isupper() for s in d_sent) and e_sent and not any(s[:1].isupper() for s in e_sent):
        out["lowercase"] = True
    if EMOJI.search(draft) and not EMOJI.search(edited):
        out["max_emoji"] = 0
    if re.search(r"#\w", draft) and not re.search(r"#\w", edited):
        out["no_hashtags"] = True
    return out


RULE_TEXT = {
    "max_words": "Keep it to {v} words or fewer.",
    "max_sentences": "At most {v} sentence(s).",
    "lowercase": "Write in lowercase.",
    "max_emoji": "No emoji.",
    "no_hashtags": "No hashtags.",
}


def _covered(profile: VoiceProfile, kind: str, value) -> bool:
    for rule in profile.rules:
        current = getattr(rule.check, kind, None) if rule.check else None
        if current is None:
            continue
        if kind in ("max_words", "max_sentences", "max_emoji"):
            if current <= value:
                return True
        elif current:
            return True
    return False


def rule_proposals(founder_id: str | None = None) -> list[RuleProposal]:
    """Current state of each suggestion (the last event for each id wins)."""
    latest: dict[str, dict] = {}
    for event in _read("rules.jsonl"):
        latest[event["id"]] = event
    rules = [RuleProposal.model_validate(e) for e in latest.values()]
    return [r for r in rules if founder_id in (None, r.founder_id)]


def _suggest(founder_id: str) -> RuleProposal | None:
    edits = [r for r in _read("reviews.jsonl") if r["founder_id"] == founder_id and r["action"] == "edit"]
    profile = current_founder(founder_id).profile
    pending = {k for r in rule_proposals(founder_id) if r.status == "suggested" and r.check
               for k, v in r.check.model_dump(exclude_none=True).items()}
    used = {i for r in rule_proposals(founder_id) for i in r.source_review_ids}
    by_kind: dict[str, list[tuple[str, int | bool]]] = {}
    for r in edits:
        if r["id"] in used:
            continue
        for kind, value in signals(r["draft_text"], r["edited_text"]).items():
            by_kind.setdefault(kind, []).append((r["id"], value))
    for kind, hits in by_kind.items():
        if len(hits) < EDITS_FOR_A_RULE or kind in pending:
            continue
        values = [v for _, v in hits]
        value = max(values) if kind in ("max_words", "max_sentences") else values[0]
        if _covered(profile, kind, value):
            continue
        proposal = RuleProposal(
            id=f"rule-{uuid.uuid4().hex[:6]}", founder_id=founder_id,
            rule=RULE_TEXT[kind].format(v=value), check=VoiceCheck(**{kind: value}),
            source_review_ids=[i for i, _ in hits],
        )
        _append("rules.jsonl", proposal.model_dump(mode="json"))
        return proposal
    return None


def _get_rule(rule_id: str) -> RuleProposal:
    for r in rule_proposals():
        if r.id == rule_id:
            return r
    raise ReviewError(f"unknown rule suggestion '{rule_id}'")


def approve(rule_id: str) -> int:
    """Apply a suggested rule: a new, immutable profile version. Returns the new version number."""
    suggestion = _get_rule(rule_id)
    if suggestion.status != "suggested":
        raise ReviewError(f"'{rule_id}' is {suggestion.status}, not waiting for approval")
    founder = current_founder(suggestion.founder_id)
    existing = sorted(int(p.stem[1:]) for p in _profile_dir(suggestion.founder_id).glob("v*.json"))
    version = max([1, *existing]) + 1
    learned = Rule(id=f"r-learned-{version}", text=suggestion.rule, origin="learned", check=suggestion.check)
    profile = founder.profile.model_copy(update={"version": version, "rules": [*founder.profile.rules, learned]})
    (_profile_dir(suggestion.founder_id) / f"v{version}.json").write_text(profile.model_dump_json(indent=2))
    _activate(suggestion.founder_id, version)
    _append("rules.jsonl", suggestion.model_copy(update={"status": "approved", "profile_version": version}).model_dump(mode="json"))
    return version


def reject(rule_id: str) -> None:
    suggestion = _get_rule(rule_id)
    if suggestion.status != "suggested":
        raise ReviewError(f"'{rule_id}' is {suggestion.status}, not waiting for approval")
    _append("rules.jsonl", suggestion.model_copy(update={"status": "rejected"}).model_dump(mode="json"))


def revert(founder_id: str) -> int:
    """Go back to the previous profile version. Returns the version now active."""
    history = _history(founder_id)
    if len(history) < 2:
        raise ReviewError(f"{founder_id} is already on the original profile (version 1)")
    undone = history[-1]
    (_profile_dir(founder_id) / "history.json").write_text(json.dumps(history[:-1]))
    for r in rule_proposals(founder_id):
        if r.status == "approved" and r.profile_version == undone:
            _append("rules.jsonl", r.model_copy(update={"status": "reverted"}).model_dump(mode="json"))
    return history[-2]


def versions(founder_id: str) -> tuple[int, list[int]]:
    """(active version, all versions ever created)."""
    created = sorted(int(p.stem[1:]) for p in _profile_dir(founder_id).glob("v*.json"))
    return _history(founder_id)[-1], [1, *created]
