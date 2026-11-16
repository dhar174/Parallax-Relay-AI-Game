# Four-phase completion implementation plan

Approved in chat on November 16, 2026, including the agent naming amendment.

## Goal and execution contract

Deliver Slice 10 replay inspection, controlled evaluation preparation and authorized campaigns, source/dependency assurance, and accurate documentation/closure. Baseline: PR #41, `4e0851b2b1ebfeb2f23a8037b9b9c10169d97675`.

Use isolated worktrees and focused PRs. Never merge or deploy without separate authorization. Qualification Q, development pilot P, and confirmation C each require concrete, separately approved spending receipts before any live invocation. Implementation approval is not spending approval. Keep all model requests offline until that gate.

Use GPT-6.1 Terra Max for complex implementation/security and GPT-6.1 Sol High for browser coverage/evidence/docs. Give scoped agents feminine or neutral names, preferably task-related tongue-in-cheek adult innuendo: Paige Afterglow (replay), Wanda Probe (browser), Roxy Repeats (campaigns), Anita Leakcheck (privacy), Dee Pendenz (dependencies), Bea Explicit (docs). Fresh reviewers must be independent of their reviewed changes.

Read AGENTS.md and relevant architecture/protocol/provenance/workbench contracts. Reproduce behavior defects before fixing; observe RED then GREEN. Inspect command exit status/stdout/stderr; verify every changed file by readback and diff. Record actual checks and limitations, never copy historical counts as fresh evidence. Preserve historical fixtures and verification logs. Run full offline tests after code changes plus relevant Node/browser, compilation, mock and room checks.

## Phase 1: replay inspection and browser verification (#25/#26, parent #12)

Replay PR: add existing phases and final_state to newly generated embedded HTML, with no native schema bump or atomic artifact count change. Label resolved observations BEFORE actions, distinguish resolution results, show unfinished work only from recorded calls/phases, and expose an always-reachable final/last-resolved snapshot and image. Normalize zero-based call/phase turns versus one-based rounds. Include zero-turn/zero-call cases, all attempts/completed phases, commitments without resolution, independent engine/operational outcomes, and missing-data placeholders. Never invent missing HUDs/notes/actions/scores. Mirror final/partial inspection in workbench without changing accepted imports/exports. Keep standalone JS embedded, untrusted text inert, image references bounded, legacy readers/fixtures preserved.

Browser PR: isolated dev-only Playwright 1.62.1 package and lock using node:test; ignore node_modules and browser outputs; provision matching Chromium and record actual version. Add Ubuntu/Python 3.12/Node 24 browser CI job without replacing six Python jobs. Test file replay, static workbench imports and actual loopback mock companion; permit exact local origins, block service workers/WebSockets and fail external request attempts. Cover victory, one-turn limit, later partial/zero-turn/zero-call stops, cancellation/output failure, malicious text, missing images/optional fields, actual legacy import and current records. Verify navigation/range/keyboard/focus/names/state labels, 1280x800 and 390x844 layouts and contrast. Do not claim audible screen-reader checks from markup tests.

Gate: focused regressions, full Python/Node checks, mock wins, nine certificates, browser checks and declared hosted matrix. Publish actual dated evidence. Close issues only once accepted deliverables land.

## Phase 2: controlled evaluation (#9)

Run the 45-trial/648-call development diagnostic first. Live roster: two independent OpenAI gpt-6-luna entries and Gemini gemini-3.5-flash-lite, deduplicated into three assignments. Recheck official prices/capabilities and account limits. All five arms: full/reduced/disabled/withheld/no_images.

Live common settings: 12 turns, 216 calls, two attempts, timeout 60s, output 4096 tokens, history four turns, retry delay 0.5s, failure limit three, image reserve 8192, serial launches with one-second minimum interval and scheduler seed zero. Compute a documented conservative per-match guard M; do not reuse the one-turn $1 cap without justification. Freeze exact Git/environment/catalog/prompts/roster/prices/policies/common settings through pilot/confirmation in a dedicated clean checkout; keep outputs ignored and publish documents elsewhere.

Q: protocol-2 diagnostic, only split_span, policies=[], all arms, one repetition, three assignments, two turns/36 calls/two attempts: 15 model trials, at most 432 provider attempts. Prepare exact numeric guards, hashes, settings, source/environment, command and exposure receipt; obtain approval before running. Require observed valid coverage, complete lifecycle/cleanup and accounting. Preserve failures; fresh registration and approval for any correction/repeat.

P: three development rooms, five repetitions; 225 model + 105 baseline = 330 trials; maximum 38,880 model and 57,024 total calls. Numeric monetary admission 225*M, separately approved. Require complete artifacts, known outcomes, cohort_eligible, no unexplained anomalies and balanced reservations.

C: six held-out rooms, 30 repetitions; 2,700 model + 960 baseline = 3,660 trials; maximum 466,560 model and 632,448 total calls. Register only after an eligible completed pilot, link --pilot, obtain separate approval for 2,700*M exposure. Only registered confirmation runner grants held-out permits. Changed frozen inputs or a binding match guard require a new pilot; no post-pilot cap increase under the old link.

Local estimates are not invoice ceilings. Never delete markers, silently resume/replace trials, or substitute models. Retain incomplete cohorts and all denominators. Report pilot separately, per-room/team/assignment/condition outcomes, operational versus engine failures, usage/settlement/latency/attempt coverage, Wilson intervals and registered paired-block contrasts. Secondary contrasts exploratory; family/split totals descriptive. Keep raw spectator artifacts private. Q/P/C include time/storage/quota planning. Long runs need exact process/checkpoint/output paths and ten-minute heartbeats where supported, no duplicate workers.

Gate: complete eligible confirmation and reproducible sanitized report; negative or inconclusive findings are valid. Keep #9 open while incomplete or if later findings invalidate treatment/privacy/accounting.

## Phase 3: assurance (#23/#24, parent #11)

Freeze assessed revision. Standard source/privacy scan requires official resources and ready capability preflight; scan production runtime, role projection/provider/orchestration/campaign/permit/budget/provenance/replay/workbench/companion/output and CI/config boundaries. Exclude credentials/private runs/raw bodies. Validate findings before reporting. If required tooling is unavailable, publish blocker, keep #23/#11 open, and label manual checks supplemental.

Audit exact Python locks/bootstrap and independently resolved ranges; include all new npm dev/optional transitives, Node, Chromium/OS libraries, actions and tooling with explicit coverage. Query dated maintained advisory sources; inspect license metadata/texts and static/companion obligations; preserve MIT. Errors/unavailable data are not clearance. Isolate audit tools from runtime environments.

Confirmed findings: focused RED-GREEN regression, smallest compatible correction, full affected verification, repeat relevant audit against new revision. Reassess campaign validity for treatment/privacy/accounting defects. Separate source/privacy and dependency/license PRs. Close only on accepted evidence and actual satisfied criteria.

## Phase 4: documentation and closure (#2)

Correct stale one-room, pending controls/runner/rooms and provider-awaiting-merge summaries. Preserve dated history. Record actual new behavior, tests, research outcomes and audit gaps. Preserve Anthropic live-unverified and #15 not planned. Build R01-R10 evidence matrix with issue/PR, behavior, tested revision/environment, results and limits. Verify commands/links/anchors. Leave Site release, broader workbench and provider/modality expansion separate.

Close #12 only after replay/browser evidence, #9 after eligible research reporting, #11 after assurance gates, and #2 last. Unmerged PRs remain reviewable work rather than closed issues. Rebase ordinary branches without altering a running campaign's frozen checkout. Final handoff lists actual checks and blockers.
