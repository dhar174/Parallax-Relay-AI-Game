# Browser review repair and checkpoint regressions — November 17, 2026

Tess Tickles independently reviewed PR #44's own base `52384c6` → head `1ead08c`
and reproduced a companion-startup race in its keyboard folder-import test.
Two untouched full runs on frozen integration `9b3b6b5` each passed 21/22 and
failed waiting for the file chooser. A focused rerun passed. Holding the real
local `/api/status` response showed why: its continuation rendered the workbench
again and replaced a button focused before initialization completed.

This follow-up is based on browser integration `490bf67`, which incorporates the
separately reviewed core repair `4b6f842`. It changes only browser tests/utilities,
the offline fixture generator and test documentation. Production sources, Python
requirements, npm pins, the six existing Python jobs and committed example files
are unchanged by this follow-up. No provider requests were made.

## Readiness repair and RED–GREEN evidence

All workbench browser navigation now waits for the observable initialized footer
(`REPO …`) after navigation, before keyboard interaction. The footer is updated
only after the module's initial status lookup and render. There are no sleeps,
raised timeouts, or production test hooks.

A permanent test delays the real companion's status response without replacing
its contents. While the response is held, it opens Evaluation and focuses the
folder-import button. The navigation helper must remain pending. Releasing the
response reproduces the old focus replacement; after the helper completes, the
test refocuses the current button, presses Enter and imports the actual committed
legacy directory using its file chooser.

The helper's former navigation-only behavior failed the pending-readiness
assertion with `true !== false` (exit 1). The readiness wait passes this regression
and the complete suite. The final RED reproduction used the current test with the
wait omitted in an external archive; tracked core files were never reverted.

## Checkpoint truth in actual Chromium

Two additional native driver fixtures establish controls:

| Fixture | Resolved turns | Calls | Completed phases | Stop |
| --- | ---: | ---: | ---: | --- |
| `broadcast-only` | 0 | 3 | 1 broadcast | `call_budget` under cap 7 |
| `later-commit-unresolved` | 1 | 18 | 6, including the second round's three commitments | `internal_error` from explicit synthetic resolution failure |

The latter fixture allows one real engine resolution, then injects failure only
when resolving the next completed COMMIT. Its final snapshot and PNG remain the
native turn-one checkpoint. The existing turn-zero completed-COMMIT fixture is
retained.

Three explicitly contradictory derivatives of that native fixture alter nested
post-resolution turn evidence, nested terminal evidence, or add a phase beyond
the final checkpoint. These are synthetic contradictory archives, not driver or
model results. The terminal derivative uses the native scripted victory snapshot
retimed to round one so it retains schema-valid room geometry while contradicting
the outer nonterminal checkpoint. No observation PNG is fabricated for later
synthetic phase evidence.

Each derivative is tested independently in both the generated `file://` viewer
and the companion-served workbench. Both must label the round `resolution unknown`,
retain its exact native calls/phases/commitments and final snapshot, and avoid
claiming its commitments were not applied. The consistent native COMMIT controls
must still show unfinished/unapplied commitments. The broadcast-only native stop
must remain unfinished while reporting no completed commitments.

RED used an external archive of pre-repair `1ead08c` with the new tests and fixture
generator. All six contradiction viewer checks failed on `Round 2 · unfinished`;
the workbench broadcast-only check failed on its false completed-commitments note.
The standalone broadcast-only control passed. Node reported **12 tests, 1 pass,
11 failures**, including the four failed parent tests; these are seven independent
failing viewer assertions, not eleven separate defects. The command exited 1.

An intermediate terminal derivative that only toggled `win` was correctly rejected
by the v3 room-geometry validator, before inspection. It was replaced with the
schema-valid terminal derivative above; the final full suite imports and inspects
it in Chromium rather than treating an import error as a passing unknown state.

Additional assertions check every role sensor's missing-image banner before the
final frame, workbench native retry-failure details, and both turn-zero/later
completed-COMMIT notes with their exact raw call/phase arrays.

## Fresh verification

Local environment: Node **24.22.1**, Python **3.12.14** from
`/workspace/scratch/parallax-assurance-locked/bin/python`, Playwright **1.62.1**,
managed Chromium **151.0.7922.34** (revision 1234), Linux x86_64/glibc 2.41,
Pillow **13.0.0**, Pydantic **2.14.3**, httpx **0.28.1**. Existing managed browser
packages were reused; this was not a fresh npm/browser provisioning check.

Commands ran from the browser integration checkout, except the stated RED archive:

```bash
PYTHON=/workspace/scratch/parallax-assurance-locked/bin/python node --test --test-name-pattern='workbench readiness' tools/browser/replay.test.mjs
PYTHON=/workspace/scratch/parallax-assurance-locked/bin/python node --test --test-name-pattern='contradictory checkpoint|broadcast-only native' tools/browser/replay.test.mjs
PYTHON=/workspace/scratch/parallax-assurance-locked/bin/python npm test --prefix tools/browser
PYTHON=/workspace/scratch/parallax-assurance-locked/bin/python node --test --test-concurrency=1 tests/test_workbench_web.mjs
/workspace/scratch/parallax-assurance-locked/bin/python -m unittest discover -s tests -v
/workspace/scratch/parallax-assurance-locked/bin/python -m pip check
/workspace/scratch/parallax-assurance-locked/bin/python -m compileall -q parallax_relay tests scripts site tools/browser/make_fixtures.py
/workspace/scratch/parallax-assurance-locked/bin/python scripts/check_mock_runs.py
/workspace/scratch/parallax-assurance-locked/bin/python scripts/check_rooms.py
node --check tools/browser/helpers.mjs
node --check tools/browser/diagnostics.mjs
node --check tools/browser/replay.test.mjs
node --check site/web/app.js
node --check site/web/contracts.mjs
git diff --quiet 490bf67 -- parallax_relay site/web configs scripts
git diff --check
```

- Final complete browser run: **37/37 passed**, zero failures, **16.245 seconds**.
  This is 29 top-level tests plus eight separately exercised viewer subtests.
- Application Node suite: **76/76 passed**, zero failures, **5.298 seconds**.
- Full Python suite: **364 tests passed**, **67.719 seconds**.
- Dependency consistency, syntax, compilation, scoped production-diff and
  whitespace checks passed. Normal/fast mock and nine room-certificate checks
  passed.
- Sample contrast remains **11.774837:1** for the standalone label and
  **15.893595:1** for the workbench final heading, at both viewport sizes.
- The runtime fingerprint is `34ae51a48ce45e32f6006df23cc1e98bbe91d03a7b6558d45dc669e650c4bfe7`;
  it includes the core repair and is unchanged by this browser follow-up.

Ignored evidence lives under `tools/browser/test-results/` with the
`2026-11-17-` prefix: `readiness-red.log`, `readiness-green.log`,
`checkpoint-red.log`, `checkpoint-fixture-rejected.log`, `browser-green.log`,
`node-green.log`, `python-green.log`, `mock-green.log` and `rooms-green.log`.
The final full browser run supersedes intermediate development runs.

These are local Chromium checks. The new Ubuntu CI job, other browser engines and
OSes, audible screen-reader output and comprehensive accessibility remain outside
this receipt. Browser interception remains narrower than OS-level network isolation.
No formal security scan or dependency-advisory clearance is claimed; the separately
gated assurance work and Playwright advisory applicability remain unresolved.
