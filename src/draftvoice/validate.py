"""Draft validation. Assume the model lies: every sentence is re-checked against the evidence it cites.

V1-V7 block. Voice rules only warn; the founder decides.
"""

import re
from dataclasses import dataclass

from draftvoice.model import ModelError, parse_output
from draftvoice.models import CheckResult, Evidence, Sentence, VoiceProfile

MAX_CHARS = 600
# Share of a first-person sentence's content words that must appear in its cited evidence.
FIRST_PERSON_SUPPORT = 0.5
# Word overlap with a recent comment that counts as a repeat.
REPEAT_SIMILARITY = 0.8

STOCK_PHRASES = [
    "great post", "thanks for sharing", "thank you for sharing", "love this", "so true",
    "couldn't agree more", "could not agree more", "this is gold", "well said", "game changer",
    "game-changer", "in today's fast-paced", "this resonates", "really resonates", "spot on",
    "totally agree", "absolutely agree", "100% agree", "insightful post", "great insights",
    "valuable insights", "food for thought", "keep up the great work", "what a great read",
    "this is so important", "needed to hear this",
]

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each even every few for from
further had has have having he her here hers him his how i if in into is it its itself just
like more most much must my no nor not now of off on once only or other our ours out over own
really same she should so some still such than that the their them then there these they this
those through to too under until up very was we were what when where which while who whom why
will with would you your yours yourself thing things make makes made get gets got going way
""".split())

# Capitalised words that are not names when they start a sentence or are common in this domain.
COMMON_CAPS = STOPWORDS | set("""
yes yeah agreed exactly totally honestly interesting nice great good cool true fair same love
loved congrats congratulations thanks thank sometimes most many everyone nobody someone
shipping building ship build hard easy wild crazy facts big small first next last one two
ai llm llms gtm b2b saas mvp api apis ceo cto vc vcs linkedin x ok okay ngl lfg w fr
""".split())

NUMBER_WORDS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "twenty": "20",
    "thirty": "30", "forty": "40", "fifty": "50", "hundred": "100", "thousand": "1000",
    "million": "1000000", "billion": "1000000000",
}

FIRST_PERSON = re.compile(
    r"\b(we|we're|we've|we'd|our|ours|us|i built|i've built|i run|i made|i launched|"
    r"i founded|i raised|i grew|i hired|my team|my company|my startup|my customers)\b",
    re.IGNORECASE,
)
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
URL_OR_HANDLE = re.compile(r"(https?://\S+|www\.\S+|\b[\w-]+\.(?:com|io|ai|dev|ee|co)\b|@\w+)", re.I)


@dataclass(frozen=True)
class Validation:
    passed: bool
    checks: tuple[CheckResult, ...]
    sentences: tuple[Sentence, ...] = ()

    @property
    def failed(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.blocking and not c.passed)

    @property
    def warnings(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if not c.blocking and not c.passed)


def validate(raw: str, post_text: str, evidence: tuple[Evidence, ...], profile: VoiceProfile) -> Validation:
    """`evidence` is what the gate supplied: approved and matched to this post. Nothing else may be cited."""
    try:
        sentences = parse_output(raw)
    except ModelError as exc:
        return Validation(False, (CheckResult(check="V7 format", passed=False, detail=str(exc)),))

    by_id = {e.id: e for e in evidence}
    text = " ".join(s.text for s in sentences)
    checks = [
        _v1_evidence(sentences, by_id),
        _v2_numbers(sentences, by_id, post_text),
        _v3_names(sentences, by_id, post_text, profile),
        _v4_first_person(sentences, by_id),
        _v5_generic(text, post_text, evidence),
        _v6_repeats(text, profile.examples),
        _v7_length(text),
        *_voice(text, sentences, profile),
    ]
    passed = all(c.passed for c in checks if c.blocking)
    return Validation(passed, tuple(checks), tuple(sentences))


def _result(check: str, problems: list[str]) -> CheckResult:
    return CheckResult(check=check, passed=not problems, detail="; ".join(problems))


def _cited(sentence: Sentence, by_id: dict[str, Evidence]) -> str:
    return " ".join(by_id[i].text for i in sentence.evidence_ids if i in by_id)


def _v1_evidence(sentences: list[Sentence], by_id: dict[str, Evidence]) -> CheckResult:
    problems = []
    for s in sentences:
        if not s.evidence_ids:
            problems.append(f'no evidence cited: "{s.text}"')
        for i in s.evidence_ids:
            if i not in by_id:
                problems.append(f"{i} is not approved evidence for this post")
    return _result("V1 evidence", problems)


def numbers(text: str) -> set[str]:
    found = set()
    for match in re.findall(r"\d[\d,.]*", text):
        value = match.rstrip(".,").replace(",", "")
        if value:
            found.add(value)
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in NUMBER_WORDS:
            found.add(NUMBER_WORDS[word])
    return found


def _v2_numbers(sentences: list[Sentence], by_id: dict[str, Evidence], post_text: str) -> CheckResult:
    problems = []
    post_numbers = numbers(post_text)
    for s in sentences:
        allowed = numbers(_cited(s, by_id)) | post_numbers
        for n in sorted(numbers(s.text) - allowed):
            problems.append(f'"{n}" is not in the cited evidence or the post')
    return _result("V2 numbers", problems)


def _names_in(text: str) -> set[str]:
    """Links, @handles, and capitalised words. A sentence's first word counts only if it looks like a
    name on its own (OpenAI, B2B) or starts a run of capitalised words (Goldman Sachs)."""
    names = {m.group(0).rstrip(".,!?").lower() for m in URL_OR_HANDLE.finditer(text)}
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = re.findall(r"[\w'’-]+", sentence)
        for n, word in enumerate(words):
            core = re.sub(r"['’]s$", "", word)
            if not core[:1].isupper() or core.lower() in COMMON_CAPS:
                continue
            if n == 0:
                next_is_cap = len(words) > 1 and words[1][:1].isupper()
                if not (re.search(r"[A-Z0-9]", core[1:]) or next_is_cap):
                    continue
            names.add(core.lower())
    return names


def _v3_names(sentences, by_id, post_text: str, profile: VoiceProfile) -> CheckResult:
    known = (post_text + " " + profile.display_name).lower()
    problems = []
    for s in sentences:
        allowed = known + " " + _cited(s, by_id).lower()
        for name in sorted(_names_in(s.text)):
            if name not in allowed:
                problems.append(f'"{name}" is not in the cited evidence or the post')
    return _result("V3 names", problems)


def content_words(text: str) -> set[str]:
    words = set()
    for w in re.findall(r"[a-z0-9']+", text.lower()):
        if len(w) > 3 and w not in STOPWORDS:
            words.add(re.sub(r"(ing|ed|es|s)$", "", w) or w)
    return words


def _v4_first_person(sentences: list[Sentence], by_id: dict[str, Evidence]) -> CheckResult:
    problems = []
    for s in sentences:
        if not FIRST_PERSON.search(s.text):
            continue
        claims = " ".join(by_id[i].text for i in s.evidence_ids if i in by_id and by_id[i].use != "voice")
        words = content_words(s.text)
        support = len(words & content_words(claims)) / len(words) if words else 1.0
        if support < FIRST_PERSON_SUPPORT:
            problems.append(f'first-person claim not backed by its evidence ({support:.0%} overlap): "{s.text}"')
    return _result("V4 first person", problems)


def _v5_generic(text: str, post_text: str, evidence: tuple[Evidence, ...]) -> CheckResult:
    lowered = text.lower().replace("’", "'")
    problems = [f'stock phrase "{p}"' for p in STOCK_PHRASES if p in lowered]
    anchors = content_words(post_text) | {w for e in evidence for w in content_words(e.text)}
    if not content_words(text) & anchors:
        problems.append("nothing specific to the post or the evidence")
    return _result("V5 generic", problems)


def _v6_repeats(text: str, examples: list[str]) -> CheckResult:
    words = set(re.findall(r"[a-z0-9']+", text.lower()))
    problems = []
    for example in examples:
        other = set(re.findall(r"[a-z0-9']+", example.lower()))
        if words and other and len(words & other) / len(words | other) >= REPEAT_SIMILARITY:
            problems.append(f'too close to a recent comment: "{example}"')
    return _result("V6 repeats", problems)


def _v7_length(text: str) -> CheckResult:
    problems = [f"{len(text)} characters, limit {MAX_CHARS}"] if len(text) > MAX_CHARS else []
    return _result("V7 format", problems)


def _voice(text: str, sentences: list[Sentence], profile: VoiceProfile) -> list[CheckResult]:
    word_count = len(re.findall(r"\S+", text))
    results = []
    for rule in profile.rules:
        c = rule.check
        if c is None:
            continue
        problems = []
        if c.max_words is not None and word_count > c.max_words:
            problems.append(f"{word_count} words, rule says at most {c.max_words}")
        if c.min_words is not None and word_count < c.min_words:
            problems.append(f"{word_count} words, rule says at least {c.min_words}")
        if c.max_sentences is not None and len(sentences) > c.max_sentences:
            problems.append(f"{len(sentences)} sentences, rule says at most {c.max_sentences}")
        if c.max_emoji is not None and len(EMOJI.findall(text)) > c.max_emoji:
            problems.append(f"{len(EMOJI.findall(text))} emoji, rule says at most {c.max_emoji}")
        if c.lowercase and any(s.text[:1].isupper() for s in sentences):
            problems.append("starts with a capital; rule says lowercase")
        if c.no_hashtags and re.search(r"#\w", text):
            problems.append("has a hashtag")
        results.append(
            CheckResult(check=f"voice {rule.id}", passed=not problems, detail="; ".join(problems), blocking=False)
        )
    return results
