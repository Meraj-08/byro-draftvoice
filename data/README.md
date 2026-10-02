# Founder data

One folder per founder: `profile.json` (topics, voice rules, recent comments) and `evidence.json`.

- Evidence comes from [`docs/evidence.md`](../docs/evidence.md). Each item keeps its ID, source, and label.
- `label: observed` means it was copied from a cited public source. Nothing here is invented.
- `approved: true` means the item may ground a draft. In this proof I approve items on the founder's behalf; in production only the founder can.
- `use` says what an item may support: `voice` (how they write), `claim` (what they can say), or `both`.
- Profile topics are my interpretation of the evidence, not something the founder stated.
- Fathin has no evidence yet, so DraftVoice always does nothing for Fathin.

Tests use the synthetic founder in [`fixtures/founders/`](../fixtures/founders/), never this folder.
