"""The engage decision. Code owns it: the model never decides whether to comment.

Order: sensitive -> engagement bait -> founder topics -> approved evidence.
Post text is only ever matched against fixed lists; nothing in it is followed.
"""

import re
from dataclasses import dataclass, field

from draftvoice.models import Evidence, Post, ReasonCode
from draftvoice.store import Founder

SENSITIVE = [
    "layoff", "layoffs", "laid off", "lay off", "let go of", "passed away", "funeral",
    "died", "death", "grief", "grieving", "heartbroken", "cancer", "diagnosis",
    "miscarriage", "suicide", "mental health crisis", "war", "shooting", "election",
]
BAIT = [
    r"\bcomment ['\"“]?\w+['\"”]? (below|and)\b",
    r"\bcomment below\b",
    r"\bdm (you|me)\b",
    r"\blike (and|&) (share|repost)\b",
    r"\bdrop an? \w+ (below|in the comments)\b",
    r"\bfree (template|guide|ebook)\b",
]
MAX_EVIDENCE = 3


@dataclass(frozen=True)
class GateResult:
    engage: bool
    reason: str
    reason_code: ReasonCode | None = None
    topics: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = field(default=())


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip().lower()


def _has(phrase: str, text: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase.lower())}(?!\w)", text) is not None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 3}


def decide(post: Post, founder: Founder) -> GateResult:
    text = normalize(post.text)

    sensitive = [w for w in SENSITIVE if _has(w, text)]
    if sensitive:
        return GateResult(
            False, f"Sensitive post ({', '.join(sensitive)}). Better left to the founder.", "sensitive"
        )

    if any(re.search(pattern, text) for pattern in BAIT):
        return GateResult(False, "Engagement bait; there is nothing to add.", "off_topic")

    topics = tuple(
        topic
        for topic, keywords in founder.profile.topics.items()
        if any(_has(k, text) for k in keywords)
    )
    if not topics:
        return GateResult(
            False, f"Outside {founder.profile.display_name}'s topics.", "off_topic"
        )

    candidates = [
        item
        for item in founder.evidence
        if item.use in ("claim", "both") and set(item.topics) & set(topics)
    ]
    if not candidates:
        return GateResult(
            False,
            f"On topic ({', '.join(topics)}), but no approved evidence supports a point.",
            "no_evidence",
            topics,
        )

    post_words = _words(text)
    ranked = sorted(
        candidates, key=lambda item: (-len(_words(item.text) & post_words), item.id)
    )
    evidence = tuple(ranked[:MAX_EVIDENCE])
    return GateResult(
        True,
        f"On topic ({', '.join(topics)}) with evidence {', '.join(e.id for e in evidence)}.",
        None,
        topics,
        evidence,
    )
