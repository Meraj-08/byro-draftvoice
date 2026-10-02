"""Data model from design appendix A. Every record that carries voice or claims has a founder_id."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Observed: seen in a cited source. Synthetic: made-up test data.
Label = Literal["observed", "synthetic", "user-confirmed"]
# What a piece of evidence may be used for (evidence layer 4).
Use = Literal["voice", "claim", "both"]
Decision = Literal["draft", "do_nothing"]
ReasonCode = Literal[
    "off_topic", "sensitive", "celebration", "no_evidence", "model_error", "check_failed"
]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Post(Record):
    id: str
    text: str = Field(min_length=1)
    source: str
    label: Label


class Evidence(Record):
    id: str
    founder_id: str
    text: str = Field(min_length=1)
    topics: list[str] = Field(min_length=1)
    use: Use
    source: str = Field(min_length=1)
    label: Label
    approved: bool


class VoiceCheck(Record):
    """Machine-checkable part of a voice rule. Voice checks only warn."""

    max_words: int | None = Field(default=None, ge=1)
    min_words: int | None = Field(default=None, ge=1)
    max_sentences: int | None = Field(default=None, ge=1)
    max_emoji: int | None = Field(default=None, ge=0)
    lowercase: bool | None = None
    no_hashtags: bool | None = None


class Rule(Record):
    id: str
    text: str
    origin: Literal["seed", "learned"] = "seed"
    check: VoiceCheck | None = None


class Reaction(Record):
    """A short reaction the founder really wrote, reused for milestone posts. Cites its evidence item."""

    text: str = Field(min_length=1)
    evidence_id: str
    occasions: list[str]  # funding, joining, win, launch, personal, milestone


class VoiceProfile(Record):
    founder_id: str
    display_name: str
    version: int = Field(ge=1)
    # topic name -> keywords that signal it in a post
    topics: dict[str, list[str]]
    rules: list[Rule] = []
    # the founder's recent comments, used for voice and the repeats check
    examples: list[str] = []
    reactions: list[Reaction] = []


class Sentence(Record):
    text: str = Field(min_length=1)
    evidence_ids: list[str]


class CheckResult(Record):
    check: str
    passed: bool
    detail: str = ""
    # voice rules only warn; the founder decides
    blocking: bool = True


class Proposal(Record):
    id: str
    founder_id: str
    post_id: str
    decision: Decision
    reason: str
    reason_code: ReasonCode | None = None
    sentences: list[Sentence] = []
    checks: list[CheckResult] = []
    profile_version: int


class Review(Record):
    id: str
    proposal_id: str
    action: Literal["accept", "edit", "reject", "skip"]
    edited_text: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RuleProposal(Record):
    id: str
    founder_id: str
    rule: str
    check: VoiceCheck | None = None
    source_review_ids: list[str]
    status: Literal["suggested", "approved", "rejected", "reverted"] = "suggested"
    profile_version: int | None = None  # the version the approval created


class Expected(Record):
    decision: Decision
    reason_code: ReasonCode | None = None


class Fixture(Record):
    post: Post
    note: str
    # founder_id -> what DraftVoice should decide for that founder
    expected: dict[str, Expected]
