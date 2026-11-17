# Browser review follow-up — 2026-11-16

This supplements the [initial browser evidence](2026-11-16-slice10-browser.md).
Independent review found four gaps in the test harness. The follow-up changes
only browser tests, their native fixture generator, test utilities and this report.
No production source, dependency pin, runtime requirement or historical fixture
was changed. No provider requests were made.

## Association checks and mutation evidence

Each selected standalone frame now parses the displayed `Round N` into its native
zero-based turn and compares the complete ordered call and phase JSON arrays with
native rows for that turn. This applies to ordinary, partial, retry and omitted-row
archives. Assertions do not infer the turn from the slider position.

The managed-Chromium regression probe changes only the browser's live `draw`
function, rotating each call and phase filter one round while leaving the native
rows intact. The old aggregate checks accept all 63 calls and 21 phases, including
every original JSON row. The new checks reject every misplaced call group and,
independently, every misplaced phase group. The initial RED probe left the strict
assertion uncaught: it exited 1 with `Native calls for displayed turn 0` after the
old checks had passed. The permanent test expects those rejections and reports
both the old false acceptance and the new rejection.

Every successful standalone final-image case, including actual legacy-v2 data and
omitted-row archives, now requires the fully resolved image URL to equal that
fixture's exact `final_spectator.png` URL, then decodes the PNG. A second in-memory
probe displays `turn_00_spectator.png?final_spectator.png`: the former suffix and
decode assertions accept this wrong pre-action image. The exact-URL assertion
rejects it. Its uncaught RED probe also exited 1 before conversion to a permanent
expected-rejection test. Missing-image cases retain their explicit unavailable
state checks; workbench images retain exact native data-URI equality.

Focused reproduction commands (permanent probes now pass by expecting rejection):

```bash
PYTHON=/workspace/scratch/parallax-replay/.venv/bin/python node --test --test-name-pattern='rotating call' tools/browser/replay.test.mjs
PYTHON=/workspace/scratch/parallax-replay/.venv/bin/python node --test --test-name-pattern='exact final PNG' tools/browser/replay.test.mjs
```

## Additional native lifecycle fixtures

| Fixture | Resolved turns | Calls | Completed phases | Recorded behavior |
|---|---:|---:|---:|---|
| `retry-shape` | 2 | 19 | 6 | SPECTRA's turn-0 broadcast has attempt 1 `invalid_json_schema`, then attempt 2 `ok`; the completed broadcast phase is `ok` |
| `commit-unresolved` | 0 | 9 | 3 | All three COMMIT replies completed before a synthetic `resolve_turn` failure; three sealed actions remain recorded and stop reason is `internal_error` |

The retry fixture uses an offline agent returning invalid JSON once, followed by
the normal valid reply, with zero retry delay. This exercises the actual driver's
retryable shape-error path, not a non-retryable refusal. Both attempt records must
appear in the correct round and phase, and the next round has no second attempt.

The completed-COMMIT fixture patches resolution only during fixture generation.
The browser asserts the exact native commitments, the explicit `not applied
(round unresolved)` label, zero engine-event entries and zero invented private
HUD/note entries. Partial-frame checks now condition action expectations on actual
completed COMMIT records instead of requiring every partial frame to be empty.
A separate small temporary-directory fixture check verified both native summaries,
the retry pair and the three recorded commitments.

## Fresh verification

```bash
PYTHON=/workspace/scratch/parallax-replay/.venv/bin/python npm test --prefix tools/browser
PYTHON=/workspace/scratch/parallax-replay/.venv/bin/python node --test --test-concurrency=1 tests/test_workbench_web.mjs
node --check tools/browser/diagnostics.mjs
node --check tools/browser/replay.test.mjs
/workspace/scratch/parallax-replay/.venv/bin/python -m compileall -q tools/browser/make_fixtures.py
git diff --quiet f0de513 -- parallax_relay site/web configs scripts
git diff --check
```

- **22/22 browser tests passed**, zero failures, 11.607 seconds.
- **74/74 Node application tests passed**, zero failures, 5.008 seconds.
- Native fixture checks, JavaScript syntax, fixture compilation and whitespace
  checks passed. The scoped production diff is empty.
- The production runtime fingerprint before and after this follow-up is unchanged:
  `779b0df1a8d2d56b44a51ab58cbeb8e33643d444c38d5f7d3802ec2535723b59`.

Generated logs are retained under ignored `tools/browser/test-results/` as
`review-grouping-red.log`, `review-png-red.log`, `review-green.log` and
`review-node.log`. The environment remains local managed Chromium 151.0.7922.34,
Playwright 1.62.1, Node 24 and locked Python 3.12. Browser request interception and
accessibility limits remain as documented in the initial evidence; this is not a
new Ubuntu-CI, OS-network-isolation or audible screen-reader claim. The assembled
branch still needs its own integration run before updating draft PR #44.
