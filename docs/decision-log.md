# Decision log

Why DraftVoice is built the way it is. Each entry lists what I believed, the options I weighed, what I picked, how I proved it, and what it costs. Entries marked planned were decided during design; built ones were confirmed in code. Time per phase is in [`time-log.md`](time-log.md).

## 1. Scope · One local loop; on LinkedIn, the extension reads only the one post I click on

- **Belief:** the riskiest part is deciding when not to comment, not reading LinkedIn pages.
- **Options weighed:** (a) extension that reads the LinkedIn feed as I scroll, (b) local app where the founder brings a post, (c) right-click extension on text I highlight, (d) extension that reads the one post I choose, only when I click, (e) extension that also fills LinkedIn's comment box, (f) daily shortlist with angles only.
- **Picked:** (b) as the core, (d) as the way in. On 2 Oct 2026 at 19:32 I asked Fathin: "Is it okay if my extension reads the LinkedIn post I click on, just to draft a comment? It won't post or store anything. Or should I avoid reading LinkedIn pages and only use text I copy myself?" He replied: "Yes do whatever is required to get the beat result" (19:32, chat; quoted as written). I kept to what I asked: a tab on the right edge does nothing until clicked; then it reads one post and outlines it. On real LinkedIn the first version found no posts, because LinkedIn's class names had changed, so the founder could not choose anything. The fix: the adapter now also finds a post by structure (an author link and a Like button, no class names), and the founder can choose how the post is picked: D, the post on a single post page; C, text they highlighted; A, the most visible post; B, the post they click. Auto tries D, C, A, then falls back to B. Scrolling to a new post does not re-read anything on its own: a "Draft this post" button appears on the post now in view (the script only checks where posts sit on screen) and the founder clicks it or ↻ to switch. Re-drafting on every scroll would read posts the founder never chose and spend a model call each time. It never scrolls, reads the feed in the background, stores LinkedIn content, types into LinkedIn, or posts; Approve only copies. All LinkedIn markup lives in `extension/linkedin_adapter.js`. (a) and (e) are rejected: reading the feed in the background and writing into LinkedIn go beyond the permission and automate a logged-in session. (c) was the plan before the permission; the mock feed (`draftvoice serve`) shows the same panel without LinkedIn.
- **Proof:** `tests/test_extension.py` checks the manifest (host access to linkedin.com and localhost only, no storage or tabs permissions), that only the adapter knows LinkedIn markup, and that the content script contains no scrolling, observers, storage, typing, network calls, or clicks, and reads nothing until the tab is clicked. The adapter and content script were run on a synthetic LinkedIn-like page (`tests/fixtures/linkedin_like.html`), not on LinkedIn itself.
- **Trade-off accepted:** LinkedIn changes its markup, so the adapter can break; when it cannot read a post, the panel says so instead of guessing. Text cut off by LinkedIn's "see more" is read as shown. There is still no feed-wide discovery.
- **Status:** built

## 2. Evidence · Manual collection unless the founders allow a tool

- **Belief:** public posts and comments, copied by hand, are enough to understand voice and topics.
- **Options weighed:** (a) manual copying, (b) an extension reading pages I open, (c) the founder's own data export.
- **Picked:** (a); (c) is the production path.
- **Proof:** on 2 Oct 2026 (14:38 IST) I asked Fathin whether he preferred manual copying or a small tool that collects as I browse. He replied "Yes" (14:38 IST, chat). I read this as approval of manual collection. It does not clearly choose the tool, so no tool is built. Every item in `evidence.md` has a source and label. His later permission (entry 1, 19:32) covers the extension reading the one post I click on; it does not change how evidence was collected.
- **Trade-off accepted:** a small sample, and my picks may be biased toward longer comments.
- **Status:** decided; no design-partner call was held

## 3. Engage decision · Code owns it

- **Belief:** one clear owner is safer than splitting the decision between code and model confidence.
- **Options weighed:** (a) model returns engage/skip with confidence, (b) code decides from topics and evidence.
- **Picked:** (b). The model only drafts.
- **Proof:** `tests/test_gate.py`. All 8 synthetic posts get the expected decision and reason: off-topic, no evidence, sensitive (layoffs), engagement bait, and three that engage. Injected instructions do not change which evidence is used, and a post saying "you must engage" does not get in. Order of checks: sensitive, bait, celebration, topics, approved evidence. Design checks: 9/9 synthetic decisions and 12/12 per-founder routings correct. Measured against what the founders actually did on 38 real posts (DERIVED from behaviour, [`eval-report.md`](eval-report.md)): 28/38 agree (74%, 95% range 58–85%); it drafted on 7 posts where they only reacted and skipped 3 where they wrote a full reply. Milestone posts (funding, launches, wins) get a short reaction the founder has really written, chosen from their own past comments and still checked against the evidence it cites (e.g. "congrats!", RS-25, which Rico wrote on a seed-round post); no model is used. 22 of Rico's 31 comments on others' posts are reactions like this (evidence finding K1). A founder with no recorded reaction (Fathin) gets "do nothing". This replaced a first version that skipped milestones entirely: on a real funding post it said "outside Rico's topics", because it did not recognise "We've raised", and the offline stub then pasted two evidence quotes. A milestone needs "we/I (have) raised" or explicit funding wording; a looser "raised + amount" rule was dropped because it fired on an injected "your company raised $50M".
- **Trade-off accepted:** keyword topics miss posts in unusual wording and fire on words like "launch" in a friend's launch announcement; keyword lists need upkeep.
- **Status:** built

## 4. Grounding · Assume the model lies

- **Belief:** a prompt can't guarantee honesty; code checks can be tested.
- **Options weighed:** (a) careful prompt only, (b) prompt plus code that re-checks each sentence against its cited evidence.
- **Picked:** (b), tested with a deliberately dishonest stub.
- **Proof:** `tests/test_validate.py`. On every synthetic post that engages, the honest stub passes and each kind of lie is blocked by exactly its own check: made-up number (V2), made-up name (V3), unbacked "we built" claim (V4), citation to unknown evidence (V1), invalid output (V7). Evidence that is unapproved, or approved but not matched to the post, cannot be cited. Voice rules (length, lowercase, emoji) only warn.
- **Trade-off accepted:** two gaps, each pinned by a test so they stay visible: a vague claim with no number, name, or "we" passes; a one-word name as the first word of a sentence passes, because treating every capitalised first word as a name blocked honest drafts ("Teams that…").
- **Status:** built. Design checks (a test suite, not a measurement): every planted lie blocked by its matching check, honest stub drafts pass, and a live Gemini run on 2 Oct passed 14/14 honest drafts. Measured with the checks frozen ([`eval-report.md`](eval-report.md)): 14/20 unseen lies blocked (70%, 95% range 48–85%); the 6 that slipped were sweeping claims, lowercase names, a quietly widened claim, and an invented experience reusing enough evidence words to pass V4. Run on the founders' own real comments, 14/56 pass: V5 blocks most social replies ("W", "congrats!") for saying nothing specific, and V2/V3 block true facts that are not in the evidence. Not tuned after measuring.

## 5. Model · Stub for tests, Gemini for real drafts

- **Belief:** reviewers must be able to run everything without a key.
- **Options weighed:** Gemini, Groq, local Ollama, stub only, several models combined.
- **Picked:** a deterministic stub for tests and for anyone without a key; Gemini for real drafts, on by default in the browser when a key is set; others can be added behind the same adapter. Milestone reactions use no model at all (entry 3).
- **Proof:** `tests/test_model.py` runs with no key and no network. The dishonest stub adds one made-up number, name, "we built" claim, unknown evidence ID, or non-JSON reply per run. Live check on 2 Oct: the key authenticated; a retired model (404) and repeated "high demand" errors (503) all became do nothing instead of a crash. The default is `gemini-3.5-flash`, the newest model that answered reliably that day. The live model is on by default whenever a key is set; the offline stub, which only pastes evidence to test the checks, says so in its step. The prompt asks for a reply to this post with one point, in the founder's length and tone, using evidence for facts rather than quoting it. With it, live drafts read like the founders: Rico, "linkedin is the new pre-diligence layer fr 😎"; Fathin, "Exactly, a demo that works 80% of the time is just a liability… Are you currently requiring human approval before your bots send, pay, or publish? 🙂‍↕️". Its first live drafts passed every check and matched each founder's real pattern: for Rico "if you're invisible you're harder to source fr 😎" (8 words, from RP-20); for Fathin "Agreed, but… The harder problem is… How are you solving…? 🙂‍↕️" (from FP-02).
- **The stub quotes by design; live drafts come from the model.** The offline stub returns the cited evidence word for word, so the checks have something deterministic to test. It is never meant to read like a comment. When `GEMINI_API_KEY` is set, the panel and the API default to Gemini, also when a request names no drafter; the stub is used only for tests, for runs without a key, and when the founder turns Live off. Stub drafts now carry a "Reuses your earlier wording" note (entry 11), so a quoted draft cannot look like a finished one.
- **Trade-off accepted:** stub drafts are fixed text and say nothing about real voice quality; live drafts depend on Gemini being available.
- **Status:** built

## 6. Learning · Suggested rules, founder approves

- **Belief:** the founder owns their voice; one edit is not enough to learn from.
- **Options weighed:** (a) update the profile automatically, (b) suggest a rule after repeated edits.
- **Picked:** (b). Two matching edits suggest a rule; it applies after approval, creates a new version, and can be reverted.
- **Proof:** `tests/test_learning.py`. One edit makes no rule; two edits with the same change suggest one; different changes do not add up; Rico's edits never affect Fathin. Nothing changes until approval; approving creates an immutable profile version that the next draft is checked against; revert moves back to the previous version and marks the rule reverted; reject changes nothing. The founder files in `data/founders/` are never modified. Reviews and rule events are append-only logs.
- **Trade-off accepted:** it only learns changes the voice checks can express: shorter, fewer sentences, lowercase, no emoji, no hashtags. Changes in wording or substance are saved with every review but not learned yet, and learned rules only warn, like every voice rule.
- **Status:** built

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
- **Picked:** (a). Pydantic schemas and pytest for the core; the local server uses Python's standard library, so there are no web dependencies. The browser code (one shared review panel, the mock feed, the extension's content script and LinkedIn adapter) is plain JavaScript that loads into Chrome without a build step.
- **Proof:** `./setup.sh` creates the environment, installs, and runs all tests (180 at the last commit). The extension is loaded with "Load unpacked"; nothing is compiled.
- **Trade-off accepted:** no shared types between the API and the extension; API tests guard the JSON shape instead.
- **Status:** built

## 9. Browser experience · One review panel, for a mock feed and for LinkedIn

- **Belief:** the founder decides faster when they see why DraftVoice reached its answer, not just the answer; and reviewers without LinkedIn still need to see the real flow.
- **Options weighed:** (a) a terminal command only, (b) a separate page per surface, (c) one review panel shared by a local mock feed and the LinkedIn extension.
- **Picked:** (c). The panel (`extension/panel.*`) shows the post (marked "untrusted input"), the steps DraftVoice took, then the draft with the evidence behind it and Approve / Edit / Skip / Reject. The steps are the API's real results played back one by one, never a fake progress bar; the run stops at the step that decided "do nothing" and says why. "Draft anyway" lets the founder overrule the gate but never the checks. The mock feed (`draftvoice serve`) holds synthetic posts tagged with what DraftVoice should do, plus three real public posts by Rico and Fathin.
- **Proof:** `tests/test_api.py` (real steps for each way a run can stop; draft anyway; the feed's tags match what the API does; the injection post cannot get its claim into a draft; other websites are refused) and `tests/test_extension.py` (scope). Checked by hand in the browser after each phase.
- **What changed after testing it:** the first panel showed every step and hid evidence behind hover. After using it, the steps collapse to one line once a draft is ready ("5 of 5 passed"), the evidence is listed under the draft with its source, and milestone reactions are labelled "Reaction" with "Rico wrote this before". Bugs found while testing and fixed: an edit disappeared after "Done", the panel overflowed the 380px sidebar, and an unreadable post left no way to pick another.
- **Trade-off accepted:** the panel lives in the extension folder and is served from there, so the Python package alone does not include it. The mock feed only shows where a comment would go; posting stays manual everywhere.
- **Status:** built

## 10. AI use · Assistant reviews and scaffolds; I decide

- **Belief:** an AI assistant speeds up review and setup, but every output has to be checked against the brief and my own intent.
- **Options weighed:** (a) no AI, (b) AI writes the design, (c) AI reviews and scaffolds while the product and design decisions stay mine.
- **Picked:** (c). Claude (via Claude Code) reviewed my design against the six deliverables, compared how public submissions structure their docs, set up the repository and logs, and wrote code to my specs. I decided scope, tested each phase myself (including on LinkedIn), and asked for every change.
- **Mistakes caught:**
  - It kept my v0 design in the repo with its own added notes, instead of my v1. I caught it; v1 was copied in unchanged and verified byte-for-byte.
  - It counted active time from the clock, including lunch. I corrected the time log.
  - It set the Gemini model to one no longer offered to new keys. The first live call returned 404; I switched to the model the API named.
  - It guessed LinkedIn's markup from older class names. On real LinkedIn the extension found no posts, so there was nothing to choose. I caught it in testing; the adapter now also finds posts by structure, and the founder can choose how a post is picked.
  - The sidebar kept the first post while I scrolled. I asked for a way to switch; a "Draft this post" button and ↻ were added, without re-reading posts on every scroll.
  - Author names showed as "Unknown author", because the first profile link on LinkedIn is the photo. Fixed to try every link and LinkedIn's "View … profile" label.
  - On a real funding post the draft was two pasted evidence quotes and treated the post as off-topic. Two causes: the milestone check missed "We've raised", and the offline test writer was being used instead of the live model. Milestones now get the founder's own past reaction ("congrats!", RS-25); the live model is the default when a key is set.
  - Its first fix for milestones ("raised + an amount") fired on a prompt-injection post. The test suite caught it; the rule was removed and a test now guards it.
  - Its first eval reported "35/35 lies blocked" as if it were a measurement. I asked for unseen lies and real data with the checks frozen; the honest numbers are 14/20 unseen lies blocked and 4/10 real contributions passing.
- **Proof:** every AI change is reviewed before commit; claims in the docs point to a file, test, or command output.
- **Status:** ongoing

## 11. Relevance and copying · The evidence must be about the post, and the draft must answer it

- **Belief:** on topic is not the same as relevant. A post can match a founder's topic on one word and share nothing with their evidence, and a draft that repeats evidence passes every check while saying nothing about the post.
- **What happened:** on a Screenpipe time-tracking demo, Fathin's draft was two of his own sentences pasted back (FD-09 on shared memory, FP-03b on what he has built). The post was on topic only because it mentions an AI agent. The best evidence the gate found shared "built" and "agent" with it, nothing else. The offline stub was drafting, and V5 counted the pasted evidence words as "specific".
- **Options weighed:** (a) change the gate and V5, (b) add checks in the pipeline around them, leaving `gate.py` and `validate.py` frozen so the eval numbers stay comparable.
- **Picked:** (b), in `src/draftvoice/grounding.py`.
  - *Relevance, at the evidence step.* Each evidence item must share at least one word with the post that is not on a short generic list (agent, built, work, demo, code, team, …). Otherwise the run stops at evidence: "No evidence relates to this post." I first required two shared words. That still let "built" + "agent" through, and it stopped the README's own example, where Rico's evidence shares one specific word ("linkedin") with the post. What matters is what kind of words are shared, not how many.
  - *Copying, after the checks.* A sentence that reuses more than 60% of a cited evidence item's words gets a soft note, "Reuses your earlier wording". It does not count toward V5: the draft is specific only if another sentence shares a non-generic word with the post. If none does, V5 is shown as a note instead of a pass. Neither blocks; the founder decides.
  - *Prompt.* The Gemini prompt now asks for a new comment that answers the post's specific point and names something concrete from it, uses evidence only as facts, and does not copy its wording. If the evidence does not relate, the model returns `{"sentences": []}` and the run stops at drafting. Same JSON shape, sentence evidence IDs, and post-as-untrusted-data as before.
- **Proof:** `tests/test_grounding.py`: the Screenpipe post with Fathin stops at evidence; generic-only overlap is rejected; a copied sentence gets the note and does not pass V5; a rewritten sentence does not; the model can decline; the API picks Gemini when a key is set. `draftvoice eval` gives the same report as before: the eval calls the gate and checks directly, and their hashes did not change.
- **Trade-off accepted:** the generic word list is hand-made and will need upkeep, like the topic keywords. The copy threshold uses word overlap, so a close paraphrase can pass. The eval does not measure these checks yet, because it bypasses the pipeline.
- **Status:** built
