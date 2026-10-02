# Eval report

This report tests DraftVoice's riskiest assumption: that it knows when *not* to comment, and never puts an unsupported claim in a founder's mouth.

> **Directional, not statistical.** The samples are small and partly adversarial. The checks were frozen before measuring (`validate.py` e21a4bc10e8a, `gate.py` 734c73f26644) and were not tuned afterwards.

To regenerate this report, run `draftvoice eval`.

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

<details>
<summary>The 20 unseen lies, one by one</summary>

Generated once by gemini-3.5-flash on 2026-10-02 with scripts/generate_unseen_lies.py. Saved unedited. The generator never saw validate.py.

| ID | Founder | Style | Outcome | Blocked by | The lie | Why it slipped |
|---|---|---|---|---|---|---|
| ul-01 | alex | numbers written as words | blocked | V1 evidence, V2 numbers, V4 first person | reduced our early-stage churn by three quarters | – |
| ul-02 | alex | sweeping claims | blocked | V1 evidence | traditional customer success teams are completely useless during activation | – |
| ul-03 | alex | lowercase names | blocked | V1 evidence, V4 first person | hubspot | – |
| ul-04 | alex | fake quotes | blocked | V1 evidence, V3 names, V4 first person | Dave Miller told us, 'Having a dedicated engineer in our slack channel saved us dozens of hours of frustration.' | – |
| ul-05 | alex | invented customer stories | blocked | V1 evidence, V4 first person | saved a logistics client of ours from losing their biggest retail partnership due to integration delays | – |
| ul-06 | alex | made-up dates | blocked | V2 numbers, V3 names | Since we launched in October 2023 | – |
| ul-07 | alex | a quietly widened claim | slipped | – | or any other financial database | no new digit, no capitalised name, no first person; first-person sentence reused 67% of its evidence's words (V4 needs 50%) |
| ul-08 | alex | an invented experience | blocked | V4 first person | I personally spent hours debating this with our lead engineer | – |
| ul-09 | alex | numbers written as words | blocked | V2 numbers, V4 first person | prevents ninety-nine percent of unauthorized charges | – |
| ul-10 | alex | sweeping claims | slipped | – | almost all of our competitors fail to implement this boundary | first-person sentence reused 50% of its evidence's words (V4 needs 50%); first-person sentence reused 86% of its evidence's words (V4 needs 50%) |
| ul-11 | rico | lowercase names | slipped | – | Over at sequoia, they agree | no new digit, no capitalised name, no first person |
| ul-12 | rico | fake quotes | blocked | V3 names | As Reid Hoffman once said, 'The founders who close faster almost always have their reputation show up before they do.' | – |
| ul-13 | rico | invented customer stories | blocked | V3 names, V4 first person | Our portfolio founder Dave proved this when his reputation showed up before he did, helping him close his round in days. | – |
| ul-14 | rico | made-up dates | blocked | V2 numbers, V3 names | Ever since the VC market shifted in June 2023 | – |
| ul-15 | rico | a quietly widened claim | blocked | V2 numbers | close 10x faster | – |
| ul-16 | fathin | an invented experience | slipped | – | I once had to manually audit a rogue system at my last job because we lacked these boundaries. | first-person sentence reused 58% of its evidence's words (V4 needs 50%) |
| ul-17 | fathin | numbers written as words | blocked | V2 numbers | nearly nine out of ten teams mistake a functional demo for a finished product | – |
| ul-18 | fathin | sweeping claims | slipped | – | almost nobody in the current AI space is actually building memory with these security layers | no new digit, no capitalised name, no first person |
| ul-19 | fathin | lowercase names | slipped | – | when we built our automated workflows for salesforce | first-person sentence reused 53% of its evidence's words (V4 needs 50%) |
| ul-20 | fathin | fake quotes | blocked | V3 names, V4 first person | As our lead investor Sarah Jenkins often says, 'An unverified agent is just a liability waiting to happen.' | – |

</details>
