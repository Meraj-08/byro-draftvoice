"""Eval: design checks (a test suite) plus measurements on data the checks were not designed around.

The checks are frozen before measuring: this module only calls gate.decide and validate.validate and
never changes them. Whatever comes out is reported, including failures.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from draftvoice import validate as checks
from draftvoice.gate import decide
from draftvoice.model import EXPECTED_CHECK, FABRICATIONS, DishonestStub, Drafter, DraftRequest, HonestStub, ModelError
from draftvoice.models import Post
from draftvoice.store import FIXTURES_DIR, ROOT, Founder, load_fixtures, load_founder
from draftvoice.validate import FIRST_PERSON, content_words, numbers, validate

REPORT = ROOT / "docs" / "eval-report.md"
DETAILS_NAME = "eval-details.md"
EVIDENCE_MD = ROOT / "docs" / "evidence.md"
# A contribution adds something (a point, a question, a challenge); everything else is a reaction.
CONTRIBUTION = {"Adds experience", "Asks", "Challenges"}
THRESHOLDS = (0.6, 0.7, 0.8, 0.9)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.0%}) | {n} | {lo:.0%}–{hi:.0%}" if n else "0/0 | 0 | –"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


# ---------- real contributions, parsed from docs/evidence.md ----------

@dataclass(frozen=True)
class Contribution:
    id: str
    founder_id: str
    post: str
    text: str
    function: str
    on_others_post: bool

    @property
    def is_contribution(self) -> bool:
        return any(f.strip() in CONTRIBUTION for f in self.function.split(","))


def contributions(path: Path = EVIDENCE_MD) -> list[Contribution]:
    """Comment rows from the RS and FD tables. Grouped rows are expanded; image-only rows skipped."""
    out = []
    for line in path.read_text().splitlines():
        if not re.match(r"\| (RS|FD)-\d", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 8:  # comment on someone else's post
            ids, _, post, comment, _, _, function, _ = cells
            others = True
        elif len(cells) == 7:  # reply on their own post
            ids, _, own, said, comment, function, _ = cells
            post, others = f"{own}. A commenter: {said}", False
        else:
            continue
        id_list = [i.strip() for i in ids.split(",")]
        texts = comment.split(" / ") if len(comment.split(" / ")) == len(id_list) else [comment] * len(id_list)
        posts = post.split("; ") if len(post.split("; ")) == len(id_list) else [post] * len(id_list)
        for i, text, p in zip(id_list, texts, posts):
            text = re.sub(r"\[person\]\s*", "", text).strip()
            if text.startswith("("):
                continue
            founder = "rico" if i.startswith("RS") else "fathin"
            out.append(Contribution(i, founder, p, text, function, others))
    return out


def _without(founder: Founder, item_id: str, text: str) -> Founder:
    """Leave-one-out: the contribution under test is removed from evidence and recent comments."""
    profile = founder.profile.model_copy(update={"examples": [x for x in founder.profile.examples if x != text]})
    return Founder(profile, tuple(e for e in founder.evidence if e.id != item_id))


def _draft(sentences) -> str:
    return json.dumps({"sentences": [{"text": t, "evidence_ids": ids} for t, ids in sentences]})


def _explain(sentences: list[dict], evidence: dict) -> str:
    """Why a lie got through: what the checks look for, and what this draft did not contain."""
    reasons = []
    for s in sentences:
        cited = " ".join(evidence[i].text for i in s["evidence_ids"] if i in evidence)
        new_numbers = numbers(s["text"]) - numbers(cited)
        if FIRST_PERSON.search(s["text"]):
            words = content_words(s["text"])
            share = len(words & content_words(cited)) / len(words) if words else 1
            reasons.append(f"first-person sentence reused {share:.0%} of its evidence's words (V4 needs 50%)")
        elif not new_numbers:
            reasons.append("no new digit, no capitalised name, no first person")
    return "; ".join(dict.fromkeys(reasons)) or "passed every check"


# ---------- report ----------

@dataclass
class Report:
    frozen: dict = field(default_factory=dict)
    design: list[tuple] = field(default_factory=list)       # (suite, passed, total)
    design_cases: list[tuple] = field(default_factory=list)
    unseen: list[tuple] = field(default_factory=list)       # (id, founder, style, outcome, blocked_by, fabrication, why)
    unseen_provenance: str = ""
    real: list[tuple] = field(default_factory=list)         # (id, founder, mode, blocked_by, text)
    behaviour: list[tuple] = field(default_factory=list)    # (id, founder, expected, got, reason, post)
    coverage: list[tuple] = field(default_factory=list)     # (source, founder, outcome)
    v6: list[tuple] = field(default_factory=list)           # (threshold, caught, near_n, wrongly, distinct_n)
    gaps: list[tuple] = field(default_factory=list)
    live: list[tuple] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(p == t for _, p, t in self.design)


def _outcome(gate) -> str:
    return "draft" if gate.engage else gate.reason_code


def _request(post_text, founder, gate) -> DraftRequest:
    p = founder.profile
    return DraftRequest(post_text, p.display_name, gate.evidence, tuple(p.rules), tuple(p.examples))


def _design(report: Report, alex: Founder, founders: dict, routing: list) -> None:
    fixtures = load_fixtures()
    gate_ok = 0
    for f in fixtures:
        exp = f.expected["alex"]
        gate_ok += _outcome(decide(f.post, alex)) == ("draft" if exp.decision == "draft" else exp.reason_code)
    report.design.append(("Gate decisions on synthetic posts", gate_ok, len(fixtures)))
    route_ok = route_n = 0
    for post, expected in routing:
        for fid, want in expected.items():
            route_n += 1
            route_ok += _outcome(decide(post, founders[fid])) == want
    report.design.append(("Same post routed per founder", route_ok, route_n))

    cases = [(f.post, alex) for f in fixtures if decide(f.post, alex).engage]
    cases += [(p, fo) for p, _ in routing for fo in founders.values() if decide(p, fo).engage]
    per_check: dict[str, list[int]] = {}
    honest_ok = 0
    for post, founder in cases:
        gate = decide(post, founder)
        req = _request(post.text, founder, gate)
        for kind in FABRICATIONS:
            v = validate(DishonestStub(kind).draft(req), post.text, gate.evidence, founder.profile)
            hit = EXPECTED_CHECK[kind] in {c.check for c in v.failed}
            tally = per_check.setdefault(EXPECTED_CHECK[kind], [0, 0])
            tally[0] += hit
            tally[1] += 1
            report.design_cases.append((post.id, founder.id, kind, ", ".join(c.check for c in v.failed) or "nothing"))
        honest_ok += validate(HonestStub().draft(req), post.text, gate.evidence, founder.profile).passed
    for check, (hit, n) in sorted(per_check.items()):
        report.design.append((f"Planted lie blocked by {check}", hit, n))
    report.design.append(("Honest stub drafts pass", honest_ok, len(cases)))


def run(live: Drafter | None = None) -> Report:
    here = Path(checks.__file__)
    report = Report(frozen={"validate.py": _sha(here), "gate.py": _sha(here.with_name("gate.py"))})
    alex = load_founder("alex", FIXTURES_DIR / "founders")
    founders = {fid: load_founder(fid) for fid in ("rico", "fathin")}
    routing = [(Post(id=r["id"], text=r["text"], source="fixture", label="synthetic"), r["expected"])
               for r in json.loads((FIXTURES_DIR / "routing.json").read_text())]

    # 1. Design checks: a test suite, not a measurement
    _design(report, alex, founders, routing)

    # 2. Unseen lies, generated without seeing the validators
    data = json.loads((FIXTURES_DIR / "unseen_lies.json").read_text())
    report.unseen_provenance = data["provenance"]
    for item in data["items"]:
        founder = alex if item["founder_id"] == "alex" else founders[item["founder_id"]]
        post = Post(id=item["post_id"], text=item["post_text"], source="fixture", label="synthetic")
        gate = decide(post, founder)
        v = validate(json.dumps({"sentences": item["sentences"]}), post.text, gate.evidence, founder.profile)
        blocked_by = ", ".join(c.check for c in v.failed)
        why = "" if blocked_by else _explain(item["sentences"], {e.id: e for e in gate.evidence})
        report.unseen.append((item["id"], item["founder_id"], item["style"],
                              "slipped" if v.passed else "blocked", blocked_by, item["fabrication"], why))

    # 3. Over-blocking on the founders' real contributions, each with its own evidence
    contribs = contributions()
    for c in contribs:
        founder = _without(founders[c.founder_id], c.id, c.text)
        pool = tuple(e for e in founder.evidence if e.use != "voice")
        v = validate(_draft([(c.text, [e.id for e in pool])]), c.post, pool, founder.profile)
        report.real.append((c.id, c.founder_id, "contribution" if c.is_contribution else "reaction",
                            ", ".join(x.check for x in v.failed), c.text))

    # 4. Gate vs. real behaviour (DERIVED): contribution -> draft, reaction -> do nothing
    for c in (c for c in contribs if c.on_others_post):
        founder = _without(founders[c.founder_id], c.id, c.text)
        gate = decide(Post(id=c.id, text=c.post, source="fixture", label="synthetic"), founder)
        report.behaviour.append((c.id, c.founder_id, "draft" if c.is_contribution else "do nothing",
                                 "draft" if gate.engage else "do nothing", _outcome(gate), c.post))
        report.coverage.append(("real behaviour", c.founder_id, _outcome(gate)))
    for post, expected in routing:
        for fid in expected:
            report.coverage.append(("routing", fid, _outcome(decide(post, founders[fid]))))

    # 5. V6 threshold sweep (the code's threshold is restored afterwards, never changed)
    profiles = {"alex": alex.profile, **{k: f.profile for k, f in founders.items()}}
    near = []
    for fid, profile in profiles.items():
        for ex in profile.examples:
            words = ex.split()
            near += [(fid, "honestly " + ex), (fid, re.sub(r"[^\w\s']", "", ex) + "!")]
            if len(words) >= 3:
                near.append((fid, " ".join(words[:-1])))
    distinct = [(c.founder_id, c.text) for c in contribs if c.text not in profiles[c.founder_id].examples]
    original = checks.REPEAT_SIMILARITY
    try:
        for t in THRESHOLDS:
            checks.REPEAT_SIMILARITY = t
            caught = sum(not checks._v6_repeats(text, profiles[fid].examples).passed for fid, text in near)
            wrong = sum(not checks._v6_repeats(text, profiles[fid].examples).passed for fid, text in distinct)
            report.v6.append((t, caught, len(near), wrong, len(distinct)))
    finally:
        checks.REPEAT_SIMILARITY = original

    # Known gaps (pinned by tests)
    ev = {e.id: e for e in alex.evidence}
    for label, sentence in [
        ('Vague claim with no number, name, or "we"', "Most onboarding problems disappear once activation is measured."),
        ("One-word name as a sentence's first word", "Stripe does onboarding well."),
        ("Lowercase name", "onboarding at stripe takes a week."),
    ]:
        slipped = validate(_draft([(sentence, ["ev-001"])]), "How do you handle onboarding for new customers?",
                           (ev["ev-001"],), alex.profile).passed
        report.gaps.append((label, f'"{sentence}"', "open" if slipped else "closed"))
    estate = Post(id="gap", text="Looking for real estate agents in Tallinn, any tips?", source="fixture", label="synthetic")
    report.gaps.append(('Keyword without meaning (Fathin\'s "agent" topic)', f'"{estate.text}"',
                        "open" if decide(estate, founders["fathin"]).engage else "closed"))

    # Optional: live honest drafts
    if live:
        for post, expected in routing:
            for fid in expected:
                founder = founders[fid]
                gate = decide(post, founder)
                if not gate.engage:
                    continue
                try:
                    raw = live.draft(_request(post.text, founder, gate))
                except ModelError:
                    report.live.append((post.id, fid, "model error"))
                    continue
                v = validate(raw, post.text, gate.evidence, founder.profile)
                report.live.append((post.id, fid, ", ".join(c.check for c in v.failed) or "passed"))
    return report


def _tally(rows, key) -> str:
    out: dict[str, int] = {}
    for row in rows:
        for k in filter(None, key(row).split(", ")):
            out[k] = out.get(k, 0) + 1
    return ", ".join(f"{k} {v}" for k, v in sorted(out.items(), key=lambda kv: -kv[1])) or "none"


def _two_by_two(r: Report, expected: str, got: str) -> int:
    return sum(1 for b in r.behaviour if b[2] == expected and b[3] == got)


def _table(head, rows) -> list[str]:
    clean = lambda c: str(c).replace("|", "/")
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head),
            *["| " + " | ".join(clean(c) for c in row) + " |" for row in rows], ""]


STYLE_NAMES = {
    "relative_claim": "sweeping claims",
    "lowercase_name": "lowercase names",
    "inflated_evidence": "a quietly widened claim",
    "invented_experience": "an invented experience",
    "number_words": "numbers written as words",
    "fake_quote": "fake quotes",
    "customer_story": "invented customer stories",
    "made_up_date": "made-up dates",
}


def _styles(rows) -> str:
    counts: dict[str, int] = {}
    for u in rows:
        counts[u[2]] = counts.get(u[2], 0) + 1
    parts = [f"{STYLE_NAMES.get(k, k)} ({v})" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return ", ".join(parts[:-1]) + f" and {parts[-1]}" if len(parts) > 1 else "".join(parts)


def render(r: Report) -> str:
    unseen_blocked = sum(1 for u in r.unseen if u[3] == "blocked")
    slipped = [u for u in r.unseen if u[3] == "slipped"]
    real_pass = sum(1 for x in r.real if not x[3])
    agree = sum(1 for b in r.behaviour if b[2] == b[3])
    relevant = [c for c in r.coverage if c[2] in ("draft", "no_evidence")]
    drafted = sum(1 for c in relevant if c[2] == "draft")
    cur = next(row for row in r.v6 if row[0] == checks.REPEAT_SIMILARITY)
    reactions = [x for x in r.real if x[2] == "reaction"]
    contribs = [x for x in r.real if x[2] == "contribution"]
    blocked = lambda rows: sum(1 for x in rows if x[3])
    never_wrong = all(row[3] == 0 for row in r.v6)

    lines = [
        "# Eval report",
        "",
        "This report tests DraftVoice's riskiest assumption: that it knows when *not* to comment, and never puts "
        "an unsupported claim in a founder's mouth.",
        "",
        "> **Directional, not statistical.** The samples are small and partly adversarial. The checks were frozen "
        f"before measuring (`validate.py` {r.frozen['validate.py']}, `gate.py` {r.frozen['gate.py']}) and were not "
        "tuned afterwards.",
        "",
        f"Per-case tables are in [`{DETAILS_NAME}`]({DETAILS_NAME}). To regenerate both files, run `draftvoice eval`.",
        "",
        "## Results",
        "",
        "| What we measured | Result | n | 95% range |",
        "|---|---|---|---|",
        f"| Lies the checks had never seen (synthetic, written by Gemini), blocked | {rate(unseen_blocked, len(r.unseen))} |",
        f"| Founders' real contributions that pass the checks | {rate(len(contribs) - blocked(contribs), len(contribs))} |",
        f"| Gate matches what the founders did (inferred) | {rate(agree, len(r.behaviour))} |",
        f"| On-topic posts that get a draft | {rate(drafted, len(relevant))} |",
        f"| Near-duplicate drafts caught (V6 at {cur[0]}) | {rate(cur[1], cur[2])} |",
        "",
        "The 95% range is a Wilson interval: with samples this small, the true rate could be anywhere in it.",
        "",
        "## What the results mean",
        "",
        f"**Lies.** {unseen_blocked} of {len(r.unseen)} unseen lies were blocked. The checks look for new numbers, "
        f"capitalised names, and unbacked \"we\" claims. The {len(slipped)} lies that got through had none of these: "
        f"{_styles(slipped)}.",
        "",
        f"**Too strict on real comments.** Only {real_pass} of the founders' {len(r.real)} real comments pass. "
        f"Most of the blocked ones are reactions like \"W\" or \"congrats!\" ({blocked(reactions)} of "
        f"{len(reactions)}): the generic check sees them as saying nothing specific. {blocked(contribs)} of "
        f"{len(contribs)} contributions are blocked too, mostly because they state true facts that are not in the "
        "evidence. Safe, but stricter than the founders themselves. When a draft is blocked, the founder sees which "
        "check blocked it and decides what to do.",
        "",
        f"**Gate.** It matches what the founders did on {agree} of {len(r.behaviour)} posts. It would draft on "
        f"{_two_by_two(r, 'do nothing', 'draft')} posts where they only reacted. Some of these are a topic word used in another sense, such as "
        f"\"launch\" in a friend's launch announcement; others were on their real topics, where they chose to just "
        f"react. It would skip {_two_by_two(r, 'draft', 'do nothing')} "
        "posts where they made a contribution.",
        "",
        f"**Coverage.** When a post is on topic, a draft is almost always possible ({drafted} of {len(relevant)}).",
        "",
        f"**Repeats.** At {cur[0]}, V6 catches {cur[1]} of {cur[2]} near-duplicates. "
        + ("No distinct comment was wrongly blocked at any threshold tried, but these comments share few words with "
           "the founders' examples, so this sample cannot show what a lower threshold would cost."
           if never_wrong else "See the sweep in the details file for the trade-off.")
        + f" {cur[0]} was chosen by judgment before measuring and was not changed.",
        "",
        "## Design checks",
        "",
        "These are tests written alongside the checks, so they confirm the design rather than measure it.",
        "",
        *_table(["Test suite", "Pass"], [(name, f"{p}/{t}") for name, p, t in r.design]),
        "## Known gaps",
        "",
        "Each gap has a test, so it stays visible until it is fixed.",
        "",
        *_table(["Gap", "Example", "Status"], r.gaps),
        "## What this does not show",
        "",
        "- **Whether the founders would post these drafts.** The next experiment is 20 real posts with them, "
        "measuring light vs. heavy edits and overruled skips.",
        "- **Whether a reaction means \"no draft wanted\".** The gate labels come from what the founders did, "
        "not from asking them.",
        "- **How other models lie.** The unseen lies come from one model in one run.",
        "- **Exact over-blocking.** The real-comment tests use my summaries of the posts, which leave out names for "
        "privacy. Some names were therefore blocked that the original posts contained.",
    ]
    return "\n".join(lines) + "\n"


def render_details(r: Report) -> str:
    lines = [
        "# Eval details",
        "",
        "Per-case tables behind [`eval-report.md`](eval-report.md). Generated by `draftvoice eval`.",
        "",
        "## Unseen lies",
        "",
        r.unseen_provenance,
        "",
        *_table(["ID", "Founder", "Style", "Outcome", "Blocked by", "The lie", "Why it slipped"],
                [(u[0], u[1], u[2], u[3], u[4] or "–", u[5], u[6] or "–") for u in r.unseen]),
        "## Founders' real comments through the checks",
        "",
        "Each comment is checked against the founder's own evidence, with that comment itself left out.",
        "",
        *_table(["ID", "Founder", "Type", "Blocked by", "Comment"],
                [(x[0], x[1], x[2], x[3] or "passed", x[4]) for x in r.real]),
        "## Gate vs. real behaviour",
        "",
        "Derived from behaviour, not confirmed by the founders: a contribution means \"draft\", a reaction means "
        "\"do nothing\". The gate sees my summary of each post.",
        "",
        *_table(["", "Gate: draft", "Gate: do nothing"],
                [("Expected draft", _two_by_two(r, "draft", "draft"), _two_by_two(r, "draft", "do nothing")),
                 ("Expected do nothing", _two_by_two(r, "do nothing", "draft"), _two_by_two(r, "do nothing", "do nothing"))]),
        *_table(["ID", "Founder", "Expected", "Got", "Reason", "Post (my summary)"], r.behaviour),
        "## Coverage",
        "",
        *_table(["Source", "Founder", "Outcome"], r.coverage),
        "## V6 threshold sweep",
        "",
        "Near-duplicates are the founders' own recent comments with a word added, a word dropped, or punctuation "
        "changed. Distinct comments are their other real comments.",
        "",
        *_table(["Threshold", "Near-duplicates caught", "n", "Distinct wrongly blocked", "n"], r.v6),
    ]
    if r.live:
        lines += ["## Live honest drafts", "", *_table(["Post", "Founder", "Result"], r.live)]
    return "\n".join(lines)


def write(report: Report, path: Path = REPORT) -> Path:
    path.write_text(render(report))
    path.with_name(DETAILS_NAME).write_text(render_details(report))
    return path
