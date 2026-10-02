# Decision log

Why DraftVoice is built the way it is. Each entry lists what I believed, the options I weighed, what I picked, how I proved it, and what it costs. Entries marked planned were decided during design; built ones were confirmed in code. Time per phase is in [`time-log.md`](time-log.md).

## 1. Scope · One local loop, no extension

- **Belief:** the riskiest part is deciding when not to comment, not reading LinkedIn pages.
- **Options weighed:** (a) Chrome extension reading LinkedIn, (b) local app where the founder brings a post, (c) daily shortlist with angles only.
- **Picked:** (b), with (c) kept as an "angle only" output mode.
- **Proof:** TBD, demo runs the full loop with no LinkedIn access.
- **Trade-off accepted:** the founder has to copy a post in by hand.
- **Status:** planned

## 2. Evidence · Manual collection unless the founders allow a tool

- **Belief:** public posts and comments, copied by hand, are enough to understand voice and topics.
- **Options weighed:** (a) manual copying, (b) an extension reading pages I open, (c) the founder's own data export.
- **Picked:** (a) now; asked the founders about (b); (c) is the production path.
- **Proof:** TBD, founder reply quoted with date in `evidence.md`; every item has a source and label.
- **Trade-off accepted:** a small sample, and my picks may be biased toward longer comments.
- **Status:** waiting on founders

## 3. Engage decision · Code owns it

- **Belief:** one clear owner is safer than splitting the decision between code and model confidence.
- **Options weighed:** (a) model returns engage/skip with confidence, (b) code decides from topics and evidence.
- **Picked:** (b). The model only drafts.
- **Proof:** TBD, tests for off-topic, no-evidence, and injection posts.
- **Trade-off accepted:** may miss relevant posts that use unusual wording.
- **Status:** planned

## 4. Grounding · Assume the model lies

- **Belief:** a prompt can't guarantee honesty; code checks can be tested.
- **Options weighed:** (a) careful prompt only, (b) prompt plus code that re-checks each sentence against its cited evidence.
- **Picked:** (b), tested with a deliberately dishonest stub.
- **Proof:** TBD, eval report on fabrications caught and honest drafts wrongly blocked.
- **Trade-off accepted:** vague claims with no number, name, or "we" can still slip through. Stated in the eval report.
- **Status:** planned

## 5. Model · Stub by default, Gemini optional

- **Belief:** reviewers must be able to run everything without a key.
- **Options weighed:** Gemini, Groq, local Ollama, stub only, several models combined.
- **Picked:** deterministic stub by default; Gemini for live drafts; others can be added behind the same adapter.
- **Proof:** TBD, full test suite passes with no key and no network.
- **Trade-off accepted:** stub drafts are fixed text and say nothing about real voice quality.
- **Status:** planned

## 6. Learning · Suggested rules, founder approves

- **Belief:** the founder owns their voice; one edit is not enough to learn from.
- **Options weighed:** (a) update the profile automatically, (b) suggest a rule after repeated edits.
- **Picked:** (b). Two matching edits suggest a rule; it applies after approval, creates a new version, and can be reverted.
- **Proof:** TBD, tests for one edit, two edits, approval, and revert.
- **Trade-off accepted:** TBD
- **Status:** planned

## 7. AI use · Assistant reviews and scaffolds; I decide

- **Belief:** an AI assistant speeds up review and setup, but every output has to be checked against the brief and my own intent.
- **Options weighed:** (a) no AI, (b) AI writes the design, (c) AI reviews and scaffolds while the product and design decisions stay mine.
- **Picked:** (c). Claude (via Claude Code) reviewed my design against the six deliverables, compared how public submissions structure their docs, and set up the repository and logs.
- **Mistakes caught:**
  - It kept my v0 design in the repo with its own added notes, instead of my v1. I caught it; v1 was copied in unchanged and verified byte-for-byte.
  - It counted active time from the clock, including lunch. I corrected the time log.
- **Proof:** every AI change is reviewed before commit; claims in the docs point to a file, test, or command output.
- **Status:** ongoing
