# Founder data

One folder per founder: `profile.json` (topics, voice rules, recent comments) and `evidence.json`.

- Evidence comes from [`docs/evidence.md`](../docs/evidence.md). Each item keeps its ID, source, and label.
- `label: observed` means it was copied from a cited public source. Nothing here is invented.
- `approved: true` means the item may ground a draft. In this proof I approve items on the founder's behalf; in production only the founder can.
- `use` says what an item may support: `voice` (how they write), `claim` (what they can say), or `both`.
- Profile topics and voice rules are my interpretation of the evidence (see findings K1–K4 in `docs/evidence.md`), not something the founder stated.
- `approved: false` is also used for evidence that has expired (e.g. FD-13, a deadline that has passed).

Tests use the synthetic founder in [`fixtures/founders/`](../fixtures/founders/), never this folder.
