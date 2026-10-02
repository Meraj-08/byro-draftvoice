# DraftVoice

Founder-controlled comment review for LinkedIn. Byro technical challenge: help a founder decide when a LinkedIn conversation is worth joining, and propose a useful comment in their voice, while the founder keeps control of every external action.

**The model proposes, the application validates, the founder decides.** When a post is irrelevant or no approved evidence supports a contribution, the system does nothing.

## Run

```bash
./setup.sh
```

Needs Python 3.11+. Creates `.venv`, installs DraftVoice, and runs the tests. No API key or network access to a model is needed.

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
