# Execution ledger: docs/superpowers/plans/2026-11-12-milestone2.md
Baseline: supplied archive, six original tests passed on Python 3.13.5.
Workspace: isolated archive copy, local branch milestone-2. Original ZIP unchanged.
Preflight: protocol feeds adapters and orchestrator; recorder consumes orchestrator records.
Ruling: retain three-role one-lane scope. Two/four-player balancing is a later milestone.
Ruling: no credentialed live matches during build; HTTP contract tests and mock end-to-end
runs are evidence for infrastructure only, not LLM game-playing capability.

Ruling: use direct httpx REST adapters rather than optional SDKs. SDK packages could
not be installed in this network-restricted environment; existing httpx allows exact
request/response contract tests. Costs: endpoint payload mapping is maintained locally.

Task 1: complete. Privacy/schema tests: 24 passed, including original engine tests.
Task 2: complete. HTTP/config tests: 41 passed.
Task 3: complete. Orchestrator/budget tests: 60 passed.
Task 4: complete. CLI/recording tests: 70 passed before final review.
Final review: self-review (no subagent tool).
Final: fixed malformed UTF-8 environment error handling; regression RED -> GREEN.
Final: fixed empty-replay hidden controls; browser assertion RED -> GREEN.
Final: added three-adapter HTTP integration check with 429 retry and privacy assertions.
Final suite: 72 passed. Original demo and both orchestrator fixture modes succeeded.
Final: minor (deferred): crowded motor/console text in omniscient spectator image;
visual polish only, no simulation or private-sensor behavior change.
Ruling: browser QA uses temporary in-memory HTML and inline image substitutions because
container Chromium policy blocks file and localhost navigation. No policies altered.
Cost: direct file-navigation behavior remains unverified; local asset paths checked.
Ruling: package one consolidated implementation commit rather than four task commits;
intermediate test evidence is retained. Cost: less granular git bisect history.
