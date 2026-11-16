# Slice 10 Phase 1 browser verification — 2026-11-16

Wanda Probe added reproducible real-browser coverage in the isolated
`tools/browser/` development package. This evidence covers the generated
standalone viewer (`file://`), built static workbench imports, and a real
loopback mock companion. The scripts make no paid provider calls.

## Environment and provisioning

Local execution: Debian GNU/Linux 13 (trixie), Python 3.12.14 from the hashed
repository environment, Node v24.22.1, npm 11.9.0, Playwright 1.62.1 and its managed
Chromium 151.0.7922.34 (Playwright revision 1234). Managed Chromium and the headless
shell were provisioned locally under ignored package `node_modules/`, not selected
from a system browser installation. The independent CI job targets Ubuntu 24.04,
Python 3.12 and Node 24; CI execution is separate from this local evidence.

Provisioning performed from the checkout root:

```bash
npm install --ignore-scripts --no-audit --no-fund --prefix tools/browser
PLAYWRIGHT_BROWSERS_PATH=0 npm run install-browser --prefix tools/browser
npm ci --ignore-scripts --no-audit --no-fund --prefix tools/browser
```

The final `npm ci` completed from the lockfile. The already-downloaded managed
browser directory was temporarily retained and restored across that clean npm
install; no system Chrome was substituted. The lock pins exact npm versions and
tarball integrity values. Browser binaries and npm packages remain absent from
Python runtime requirements and the portable companion bundle.

## Native fixture truth

Every new lifecycle fixture is generated using the actual Python driver and
Recorder. Historical schema-v2 data comes directly from committed `example_run/`,
including its PNGs and final snapshot; it is not a v3 fixture with a changed label.
The malicious and missing-image cases are explicit derivatives of native output.

| Case | Configured call cap | Resolved turns | Attempts started | Completed phases | Stop reason |
|---|---:|---:|---:|---:|---|
| Scripted win | 216 | 7 | 63 | 21 | victory |
| One-turn limit | 216 | 1 | 9 | 3 | turn_limit |
| Later partial | 19 | 1 | 15 | 5 | call_budget |
| Zero-turn partial | 10 | 0 | 6 | 2 | call_budget |
| Zero-call stop | 1 | 0 | 0 | 0 | call_budget |
| Local recording error | 216 | 0 | 3 | 1 | local_error |
| Cooperative cancellation | 216 | 0 | 3 | 0 | cancelled |

The lower attempt counts under call caps follow the driver's existing whole-phase
retry reservation. The harness asserts these counts against native artifacts.

## RED baseline

On core commit `4e0851b2b1ebfeb2f23a8037b9b9c10169d97675`:

```bash
PYTHON=/workspace/scratch/parallax-replay/.venv/bin/python npm test --prefix tools/browser
```

The complete initial run exited 1: **15 tests, 2 passed, 13 failed**. Both viewport
checks passed. Lifecycle cases failed because the old viewer ended on the last
pre-action image or hid zero-turn controls, and the old workbench lacked final
snapshot sections. Keyboard coverage reproduced the absent live-region markup.
After tightening the frame-count assertion, a focused rerun exited 1 with the
expected mismatch: the seven-turn fixture's slider maximum was 6 instead of 7,
so no final checkpoint frame existed. Fixture creation, managed Chromium launch,
static asset serving and real companion execution all succeeded during RED.
The raw initial run is retained locally as
`tools/browser/test-results/red-baseline.log` (ignored generated evidence).

## GREEN integration

Pending core integration and the final browser verification run.

## Claims and limits

The request allowlist is enforced through browser interception: exact temporary
loopback companion origins, local fixture paths and built static assets only.
Any attempted external request or WebSocket fails the test; service workers are
blocked. The missing-image case explicitly lists only its expected failed PNG
URLs. Other console errors, page exceptions and failed resources are errors.
This is not an OS-level network sandbox.

The suite checks native final JSON and PNG decoding; every recorded call and phase
is inspectable exactly once; final/partial navigation does not invent resolved
engine events or actions; malicious model/manifest/phase text remains inert.
Keyboard checks cover Tab, arrows, Enter, Home and End, control names, boundary
disabling, focus visibility and live-region DOM updates. The viewport checks use
1280×800 and 390×844, assert no document overflow and measure the round-label
contrast against its actual solid background. Screenshots are generated under
`tools/browser/test-results/`. Audible screen-reader announcements, other browser
engines, and other operating systems are not established by this local run.
