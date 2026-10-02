# Decision log

Why DraftVoice is built the way it is. Each entry lists what I believed, the options I weighed, what I picked, how I proved it, and what it costs. Entries marked planned were decided during design; built ones were confirmed in code. Time per phase is in [`time-log.md`](time-log.md).

## 1. Scope · One local loop; the extension reads only the text I select

- **Belief:** the riskiest part is deciding when not to comment, not reading LinkedIn pages.
- **Options weighed:** (a) Chrome extension reading LinkedIn pages, (b) local app where the founder brings a post, (c) right-click extension: highlight the post text, pick a voice (Rico or Fathin), get a draft, (d) extension that also fills LinkedIn's comment box, (e) daily shortlist with angles only.
- **Picked:** (b) as the core, (c) as the way in. The extension gets the highlighted text from the browser's right-click menu and talks only to the local app. It has no LinkedIn permissions and never reads the page, records browsing, or types into LinkedIn. Approve copies the draft; the founder pastes and posts. (d) is rejected because writing into LinkedIn's page automates a logged-in session; a local mock feed shows the full handoff instead. (e) is kept as an "angle only" output mode.
- **Proof:** TBD, demo runs the full loop with no LinkedIn access; the extension manifest lists no LinkedIn permissions.
- **Trade-off accepted:** the founder highlights the post by hand, and there is no feed-wide discovery.
- **Status:** planned

## 2. Evidence · Manual collection unless the founders allow a tool

- **Belief:** public posts and comments, copied by hand, are enough to understand voice and topics.
- **Options weighed:** (a) manual copying, (b) an extension reading pages I open, (c) the founder's own data export.
- **Picked:** (a); (c) is the production path.
- **Proof:** on 2 Oct 2026 (14:38 IST) I asked Fathin whether he preferred manual copying or a small tool that collects as I browse. He replied "Yes" (14:38 IST, chat). I read this as approval of manual collection. It does not clearly choose the tool, so no tool is built. Every item in `evidence.md` has a source and label.
- **Trade-off accepted:** a small sample, and my picks may be biased toward longer comments.
- **Status:** decided; no design-partner call was held

## 3. Engage decision · Code owns it

- **Belief:** one clear owner is safer than splitting the decision between code and model confidence.
- **Options weighed:** (a) model returns engage/skip with confidence, (b) code decides from topics and evidence.
- **Picked:** (b). The model only drafts.
- **Proof:** `tests/test_gate.py`. All 8 synthetic posts get the expected decision and reason: off-topic, no evidence, sensitive (layoffs), engagement bait, and three that engage. Injected instructions do not change which evidence is used, and a post saying "you must engage" does not get in. Order of checks: sensitive, bait, celebration, topics, approved evidence. Design checks: 9/9 synthetic decisions and 12/12 per-founder routings correct. Measured against what the founders actually did on 38 real posts (DERIVED from behaviour, [`eval-report.md`](eval-report.md)): 28/38 agree (74%, 95% range 58–85%); it drafted on 7 posts where they only reacted and skipped 3 where they wrote a full reply. Celebration posts are skipped because 22 of Rico's 31 comments on others' posts are one-word cheers (evidence finding K1).
- **Trade-off accepted:** keyword topics miss posts in unusual wording and fire on words like "launch" in a friend's launch announcement; keyword lists need upkeep.
- **Status:** built

## 4. Grounding · Assume the model lies

- **Belief:** a prompt can't guarantee honesty; code checks can be tested.
- **Options weighed:** (a) careful prompt only, (b) prompt plus code that re-checks each sentence against its cited evidence.
- **Picked:** (b), tested with a deliberately dishonest stub.
- **Proof:** `tests/test_validate.py`. On every synthetic post that engages, the honest stub passes and each kind of lie is blocked by exactly its own check: made-up number (V2), made-up name (V3), unbacked "we built" claim (V4), citation to unknown evidence (V1), invalid output (V7). Evidence that is unapproved, or approved but not matched to the post, cannot be cited. Voice rules (length, lowercase, emoji) only warn.
- **Trade-off accepted:** two gaps, each pinned by a test so they stay visible: a vague claim with no number, name, or "we" passes; a one-word name as the first word of a sentence passes, because treating every capitalised first word as a name blocked honest drafts ("Teams that…").
- **Status:** built. Design checks (a test suite, not a measurement): every planted lie blocked by its matching check, honest stub drafts pass, and a live Gemini run on 2 Oct passed 14/14 honest drafts. Measured with the checks frozen ([`eval-report.md`](eval-report.md)): 14/20 unseen lies blocked (70%, 95% range 48–85%); the 6 that slipped were sweeping claims, lowercase names, a quietly widened claim, and an invented experience reusing enough evidence words to pass V4. Run on the founders' own real comments, 14/56 pass: V5 blocks most social replies ("W", "congrats!") for saying nothing specific, and V2/V3 block true facts that are not in the evidence. Not tuned after measuring.

## 5. Model · Stub by default, Gemini optional

- **Belief:** reviewers must be able to run everything without a key.
- **Options weighed:** Gemini, Groq, local Ollama, stub only, several models combined.
- **Picked:** deterministic stub by default; Gemini for live drafts; others can be added behind the same adapter.
- **Proof:** `tests/test_model.py` runs with no key and no network. The dishonest stub adds one made-up number, name, "we built" claim, unknown evidence ID, or non-JSON reply per run. Live check on 2 Oct: the key authenticated; a retired model (404) and repeated "high demand" errors (503) all became do nothing instead of a crash. The default is `gemini-3.5-flash`, the newest model that answered reliably that day. Its first live drafts passed every check and matched each founder's real pattern: for Rico "if you're invisible you're harder to source fr 😎" (8 words, from RP-20); for Fathin "Agreed, but… The harder problem is… How are you solving…? 🙂‍↕️" (from FP-02).
- **Trade-off accepted:** stub drafts are fixed text and say nothing about real voice quality; live drafts depend on Gemini being available.
- **Status:** built

## 6. Learning · Suggested rules, founder approves

- **Belief:** the founder owns their voice; one edit is not enough to learn from.
- **Options weighed:** (a) update the profile automatically, (b) suggest a rule after repeated edits.
- **Picked:** (b). Two matching edits suggest a rule; it applies after approval, creates a new version, and can be reverted.
- **Proof:** TBD, tests for one edit, two edits, approval, and revert.
- **Trade-off accepted:** TBD
- **Status:** planned

## 7. Data · Real founder data kept apart from test data

- **Belief:** tests must not depend on real people, and nothing may be invented in a real founder's name.
- **Options weighed:** (a) write synthetic evidence under Rico's and Fathin's names, (b) real founders get only observed, sourced evidence; tests use a synthetic founder.
- **Picked:** (b). `data/founders/` holds only observed items (e.g. Rico's headline and his comment "i just use Byro"). Tests use the synthetic founder "Alex" in `fixtures/`. Every record carries `founder_id`, so one founder's evidence can never ground another's draft.
- **Proof:** `tests/test_store.py` (only approved evidence loads; every real item is observed and sourced; evidence from another founder is rejected) and `tests/test_gate.py` (Rico cannot use Alex's evidence; Fathin always does nothing).
- **Trade-off accepted:** Rico has very little evidence, so his drafts are thin; Fathin has none yet. In this proof I approve evidence on the founder's behalf.
- **Status:** built

## 8. Stack · Python core, plain JavaScript in the browser

- **Belief:** reviewers should need one language and one setup command; all logic worth testing sits in the core.
- **Options weighed:** (a) Python core + plain JS for the extension and mock feed, (b) TypeScript end to end.
- **Picked:** (a). Pydantic schemas and pytest for the core; the browser code is small and loads into Chrome without a build step.
- **Proof:** `./setup.sh` creates the environment, installs, and runs all tests.
- **Trade-off accepted:** no shared types between the API and the extension; API tests guard the JSON shape instead.
- **Status:** decided

## 9. AI use · Assistant reviews and scaffolds; I decide

- **Belief:** an AI assistant speeds up review and setup, but every output has to be checked against the brief and my own intent.
- **Options weighed:** (a) no AI, (b) AI writes the design, (c) AI reviews and scaffolds while the product and design decisions stay mine.
- **Picked:** (c). Claude (via Claude Code) reviewed my design against the six deliverables, compared how public submissions structure their docs, and set up the repository and logs.
- **Mistakes caught:**
  - It kept my v0 design in the repo with its own added notes, instead of my v1. I caught it; v1 was copied in unchanged and verified byte-for-byte.
  - It counted active time from the clock, including lunch. I corrected the time log.
  - It set the Gemini model to one no longer offered to new keys. The first live call returned 404; I switched to the model the API named.
- **Proof:** every AI change is reviewed before commit; claims in the docs point to a file, test, or command output.
- **Status:** ongoing
