"""Checks the pipeline runs around validate.py: is the evidence about this post, and did the draft
respond to the post or just repeat the evidence? validate.py and gate.py stay frozen, so these live here.
"""

from draftvoice.models import CheckResult, Evidence, Sentence
from draftvoice.validate import content_words

# Words nearly every post in the founders' lanes uses. Sharing only these is not relevance:
# "built an agent" matches every agent post ever written.
GENERIC = content_words("""
agent agents agentic built build building builder work working works time demo code source open
product products team teams user users system systems data tool tools record records model models
startup startups founder founders company people person persons thing real today week year need needs using used
post posts everyone become becomes next try trying check feel feels it's
""")
# Share of a cited evidence item's words a sentence may reuse before it reads as a copy.
COPY_SHARE = 0.6
COPY_NOTE = "Reuses your earlier wording"


def shared_words(post_text: str, item: Evidence) -> set[str]:
    return content_words(post_text) & content_words(item.text)


def relates(post_text: str, item: Evidence) -> bool:
    """Real overlap: at least one shared word beyond the generic ones. Counting words is not enough:
    "built" + "agent" is two words and no relation, while one shared "linkedin" can be the whole point."""
    return bool(shared_words(post_text, item) - GENERIC)


def relevant(post_text: str, evidence: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
    """The gate's evidence, keeping only items with real overlap with the post."""
    return tuple(e for e in evidence if relates(post_text, e))


def reuse(sentence: Sentence, item: Evidence) -> float:
    words = content_words(item.text)
    return len(content_words(sentence.text) & words) / len(words) if words else 0.0


def copied(sentence: Sentence, by_id: dict[str, Evidence]) -> list[str]:
    """IDs of the cited evidence this sentence mostly repeats."""
    return [i for i in sentence.evidence_ids if i in by_id and reuse(sentence, by_id[i]) > COPY_SHARE]


def copy_check(sentences: tuple[Sentence, ...], post_text: str, evidence: tuple[Evidence, ...],
               checks: tuple[CheckResult, ...]) -> list[CheckResult]:
    """Adds a soft copy note. A sentence that repeats its evidence is specific only because the evidence
    is, so V5 is re-judged on the other sentences alone: they must share a non-generic word with the post.
    Nothing here blocks; the founder decides."""
    by_id = {e.id: e for e in evidence}
    copies = [(s, ids) for s in sentences if (ids := copied(s, by_id))]
    if not copies:
        return list(checks)
    detail = f"{COPY_NOTE} ({', '.join(dict.fromkeys(i for _, ids in copies for i in ids))})"
    note = CheckResult(check="copy", passed=False, detail=detail, blocking=False)
    post_words = content_words(post_text) - GENERIC
    own = [s for s in sentences if not copied(s, by_id)]
    if any(content_words(s.text) & post_words for s in own):
        return [*checks, note]
    v5 = CheckResult(check="V5 generic", passed=False, blocking=False,
                     detail=f"Not counted as specific: {COPY_NOTE.lower()}, nothing responds to the post")
    return [v5 if c.check == "V5 generic" and c.passed else c for c in checks] + [note]
