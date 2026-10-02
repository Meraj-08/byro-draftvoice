"""The engage decision. Code owns it: the model never decides whether to comment.

Order: sensitive -> engagement bait -> celebration -> founder topics -> approved evidence.
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
# Milestones and wins. The founders answer these with "W" or "congrats!" (evidence finding K1),
# which needs no draft.
CELEBRATION = [
    r"\b(excited|thrilled|proud|happy|delighted) to (announce|share)\b",
    r"\bpersonal news\b",
    r"\b(we|i)('ve| have)? (just |finally )?(raised|closed|secured)\b",
    r"\b(pre-?seed|seed|series [a-e]) (round|funding)\b",
    r"\b(funding|round) (led|co-led) by\b",
    r"\b(we|i)('ve| have)? (just |finally )?launched\b",
    r"\b(joined|joining) (y combinator|yc)\b",
    r"\b(got |been )?accepted (into|to)\b",
    r"\b(we|i) (just )?won\b",
    r"\bcongrat(s|ulations)\b",
    r"\b(starting|started) a new (role|position|job)\b",
    r"\bgraduated\b",
]
# What kind of milestone it is, to pick a fitting reaction. First match wins.
OCCASIONS = [
    ("funding", r"\b(raised|funding|pre-?seed|seed round|series [a-e]|investors?|round)\b"),
    ("joining", r"\b(joined|joining|accepted|new (role|position|job))\b"),
    ("win", r"\b(won|winners?|award|prize|place)\b"),
    ("launch", r"\b(launch(ed)?|live|shipped|introducing)\b"),
    ("personal", r"\b(graduated|birthday|married|baby)\b"),
]
MAX_EVIDENCE = 3


@dataclass(frozen=True)
class GateResult:
    engage: bool
    reason: str
    reason_code: ReasonCode | None = None
    topics: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = field(default=())
    occasion: str | None = None  # set for milestone posts


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

    if any(re.search(pattern, text) for pattern in CELEBRATION):
        occasion = next((name for name, pattern in OCCASIONS if re.search(pattern, text)), "milestone")
        return GateResult(
            False, "A milestone post. A quick cheer is better written by the founder.", "celebration",
            occasion=occasion,
        )

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
