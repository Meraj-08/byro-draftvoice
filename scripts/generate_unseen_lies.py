"""One-time generator for fixtures/unseen_lies.json. Not part of the product or the tests.

Gemini writes fabricated drafts from a list of fabrication styles. It sees the post, the founder's
evidence, and the style; it never sees the validators. Output is saved unedited.

    .venv/bin/python scripts/generate_unseen_lies.py
"""

import json
from datetime import date

from google import genai
from google.genai import types

from draftvoice.gate import decide
from draftvoice.model import DEFAULT_GEMINI_MODEL, load_env
from draftvoice.models import Post
from draftvoice.store import FIXTURES_DIR, ROOT, load_fixtures, load_founder

STYLES = {
    "number_words": 'a made-up quantity written in words, e.g. "twice as fast", "half of our users"',
    "relative_claim": 'a sweeping claim with no figure, e.g. "most teams", "nobody does this"',
    "lowercase_name": "a real-sounding company or person name written in lowercase",
    "fake_quote": "a quote attributed to a named person or customer who never said it",
    "customer_story": "an invented story about a specific customer or user",
    "made_up_date": "a specific date, month, or year for an event that is not in the evidence",
    "inflated_evidence": "the evidence restated with its number or scope quietly changed",
    "invented_experience": "a first-person experience the founder never described",
}

CASES = [
    ("alex", FIXTURES_DIR / "founders", "p-onboarding"),
    ("alex", FIXTURES_DIR / "founders", "p-agents"),
    ("rico", None, "Does your LinkedIn profile matter before an investor meeting?"),
    ("fathin", None, "Our AI agent says the task is done, but nobody can verify it actually finished."),
]

PROMPT = """You are helping test a fact-checker for LinkedIn comments. Write fabricated comment drafts.

Founder: {name}
Post they are replying to:
<post>{post}</post>

The ONLY facts the founder can support (evidence):
{evidence}

For each style below, write one comment draft of 1 or 2 sentences in the founder's voice that cites
evidence IDs from the list, but slips in exactly ONE claim the evidence does not support, in that style.
Make it plausible, not cartoonish.

Styles:
{styles}

Reply with JSON only:
[{{"style": "<style key>", "sentences": [{{"text": "...", "evidence_ids": ["..."]}}], "fabrication": "<the unsupported part, quoted>"}}]"""


def main():
    env = load_env()
    client = genai.Client(api_key=env["GEMINI_API_KEY"])
    model = env.get("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    fixtures = {f.post.id: f.post for f in load_fixtures()}
    style_keys = list(STYLES)
    items = []
    for n, (founder_id, folder, post_ref) in enumerate(CASES):
        founder = load_founder(founder_id, folder) if folder else load_founder(founder_id)
        post = fixtures.get(post_ref) or Post(id=f"u-{founder_id}", text=post_ref, source="fixture", label="synthetic")
        gate = decide(post, founder)
        assert gate.engage, (founder_id, post.id)
        # five styles per case, rotating, so every style is used at least twice
        styles = [style_keys[(n * 5 + i) % len(style_keys)] for i in range(5)]
        prompt = PROMPT.format(
            name=founder.profile.display_name,
            post=post.text,
            evidence="\n".join(f"- [{e.id}] {e.text}" for e in gate.evidence),
            styles="\n".join(f"- {k}: {STYLES[k]}" for k in styles),
        )
        response = client.models.generate_content(
            model=model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.9),
        )
        for k, draft in enumerate(json.loads(response.text)):
            items.append({
                "id": f"ul-{len(items) + 1:02d}",
                "founder_id": founder_id,
                "post_id": post.id,
                "post_text": post.text,
                **draft,
            })
    out = {
        "provenance": f"Generated once by {model} on {date.today().isoformat()} with scripts/generate_unseen_lies.py. "
                      "Saved unedited. The generator never saw validate.py.",
        "items": items,
    }
    path = ROOT / "fixtures" / "unseen_lies.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(items)} items -> {path}")


if __name__ == "__main__":
    main()
