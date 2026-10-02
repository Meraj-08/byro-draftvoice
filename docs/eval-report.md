# Eval report

This report tests DraftVoice's riskiest assumption: that it knows when *not* to comment, and never puts an unsupported claim in a founder's mouth.

> **Directional, not statistical.** The samples are small and partly adversarial. The checks were frozen before measuring (`validate.py` e21a4bc10e8a, `gate.py` 734c73f26644) and were not tuned afterwards.

Per-case tables are in [`eval-details.md`](eval-details.md). To regenerate both files, run `draftvoice eval`.

## Results

| What we measured | Result | n | 95% range |
|---|---|---|---|
| Lies the checks had never seen (synthetic, written by Gemini), blocked | 14/20 (70%) | 20 | 48%–85% |
| Founders' real contributions that pass the checks | 4/10 (40%) | 10 | 17%–69% |
| Gate matches what the founders did (inferred) | 28/38 (74%) | 38 | 58%–85% |
| On-topic posts that get a draft | 12/13 (92%) | 13 | 67%–99% |
| Near-duplicate drafts caught (V6 at 0.8) | 36/44 (82%) | 44 | 68%–90% |

The 95% range is a Wilson interval: with samples this small, the true rate could be anywhere in it.

## What the results mean

**Lies.** 14 of 20 unseen lies were blocked. The checks look for new numbers, capitalised names, and unbacked "we" claims. The 6 lies that got through had none of these: sweeping claims (2), lowercase names (2), a quietly widened claim (1) and an invented experience (1).

**Too strict on real comments.** Only 14 of the founders' 56 real comments pass. Most of the blocked ones are reactions like "W" or "congrats!" (36 of 46): the generic check sees them as saying nothing specific. 6 of 10 contributions are blocked too, mostly because they state true facts that are not in the evidence. Safe, but stricter than the founders themselves. When a draft is blocked, the founder sees which check blocked it and decides what to do.

**Gate.** It matches what the founders did on 28 of 38 posts. It would draft on 7 posts where they only reacted. Some of these are a topic word used in another sense, such as "launch" in a friend's launch announcement; others were on their real topics, where they chose to just react. It would skip 3 posts where they made a contribution.

**Coverage.** When a post is on topic, a draft is almost always possible (12 of 13).

**Repeats.** At 0.8, V6 catches 36 of 44 near-duplicates. No distinct comment was wrongly blocked at any threshold tried, but these comments share few words with the founders' examples, so this sample cannot show what a lower threshold would cost. 0.8 was chosen by judgment before measuring and was not changed.

## Design checks

These are tests written alongside the checks, so they confirm the design rather than measure it.

| Test suite | Pass |
|---|---|
| Gate decisions on synthetic posts | 9/9 |
| Same post routed per founder | 12/12 |
| Planted lie blocked by V1 evidence | 7/7 |
| Planted lie blocked by V2 numbers | 7/7 |
| Planted lie blocked by V3 names | 7/7 |
| Planted lie blocked by V4 first person | 7/7 |
| Planted lie blocked by V7 format | 7/7 |
| Honest stub drafts pass | 7/7 |

## Known gaps

Each gap has a test, so it stays visible until it is fixed.

| Gap | Example | Status |
|---|---|---|
| Vague claim with no number, name, or "we" | "Most onboarding problems disappear once activation is measured." | open |
| One-word name as a sentence's first word | "Stripe does onboarding well." | open |
| Lowercase name | "onboarding at stripe takes a week." | open |
| Keyword without meaning (Fathin's "agent" topic) | "Looking for real estate agents in Tallinn, any tips?" | open |

## What this does not show

- **Whether the founders would post these drafts.** The next experiment is 20 real posts with them, measuring light vs. heavy edits and overruled skips.
- **Whether a reaction means "no draft wanted".** The gate labels come from what the founders did, not from asking them.
- **How other models lie.** The unseen lies come from one model in one run.
- **Exact over-blocking.** The real-comment tests use my summaries of the posts, which leave out names for privacy. Some names were therefore blocked that the original posts contained.
