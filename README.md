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

See it in the browser:

```bash
.venv/bin/draftvoice serve        # then open http://127.0.0.1:8765
```

A mock feed of synthetic posts plus a few real public posts by Rico and Fathin (each tagged). Click the **DraftVoice** tab on the right edge: a sidebar opens, reads the post most visible on screen, and shows each step of the decision, then the draft with its evidence. Switch between Rico and Fathin, edit, and approve. Approving copies the comment; nothing is ever posted. "Not this post?" lets you click a different post. The server only listens on this machine and refuses requests from other websites.

Review a draft from the terminal instead. `propose` prints its id; DraftVoice never posts, it gives you the text to copy:

```bash
.venv/bin/draftvoice review pr-1a2b3c4d --accept          # or --edit "your version", --reject, --skip
.venv/bin/draftvoice rules                                # suggestions appear after the same edit twice
.venv/bin/draftvoice rules approve rule-0f44ae            # creates a new profile version
.venv/bin/draftvoice rules revert --founder rico          # back to the previous version
```

Reviews, rule suggestions, and profile versions are saved in `.draftvoice/` (not committed).

Check the proof:

```bash
.venv/bin/draftvoice eval
```

Writes [`docs/eval-report.md`](docs/eval-report.md): gate accuracy, posts routed to the right founder, lies blocked, honest drafts wrongly blocked, and known gaps. Add `--live` to also judge live Gemini drafts.

## Status

Proof in progress.

- [Design (v1, before user research)](docs/design.md)
- [Decision log: assumptions, alternatives, AI use](docs/decision-log.md)
- [Time log: active time by phase](docs/time-log.md)
- [Evidence: labelled comments and posts](docs/evidence.md)
- [Eval report](docs/eval-report.md)

Next: design-partner sessions, then a thin runnable proof that tests the riskiest assumption.

## Boundaries

- No LinkedIn login, scraping, commenting or posting. Input is synthetic fixtures or user-confirmed text, and output ends at a copy or mock handoff.
- All test data is synthetic and labelled as such.
- No API keys are committed. The default demo and tests will run without any model credentials.
