# DraftVoice

Founder-controlled comment review for LinkedIn. Byro technical challenge: help a founder decide when a LinkedIn conversation is worth joining, and propose a useful comment in their voice, while the founder keeps control of every external action.

**The model proposes, the application validates, the founder decides.** When a post is irrelevant or no approved evidence supports a contribution, the system does nothing.

## Run

```bash
./setup.sh
```

Needs Python 3.11+. Creates `.venv`, installs DraftVoice, and runs the tests. No API key or network access to a model is needed.

Try one post (paste any post text; the founder is `rico` or `fathin`):

```bash
.venv/bin/draftvoice propose --founder rico --text "Does your LinkedIn profile matter before an investor meeting?"
```

DraftVoice either drafts a comment, with the evidence behind each sentence and the result of every check, or says why it does nothing. It never posts.

- `--drafter stub` (default) runs offline. `--drafter gemini` writes a live draft; put `GEMINI_API_KEY` in `.env` (see `.env.example`).
- `--drafter dishonest-number` (or `-name`, `-first_person`, `-unknown_evidence`, `-bad_json`) uses a stub that lies on purpose, to show the checks blocking it.
- `--post p-agents` uses a synthetic test post from `fixtures/posts.json` instead of pasted text.

## Status

Proof in progress.

- [Design (v1, before user research)](docs/design.md)
- [Decision log: assumptions, alternatives, AI use](docs/decision-log.md)
- [Time log: active time by phase](docs/time-log.md)

Next: design-partner sessions, then a thin runnable proof that tests the riskiest assumption.

## Boundaries

- No LinkedIn login, scraping, commenting or posting. Input is synthetic fixtures or user-confirmed text, and output ends at a copy or mock handoff.
- All test data is synthetic and labelled as such.
- No API keys are committed. The default demo and tests will run without any model credentials.
