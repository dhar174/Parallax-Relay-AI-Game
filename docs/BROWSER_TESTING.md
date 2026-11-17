# Reproducible real-browser checks

The development-only harness in `tools/browser/` drives the generated standalone
viewer over `file://`, the built static workbench, its native directory/JSON
imports, and an actual temporary loopback companion running the real mock CLI.
It uses Node 24, the locked Python environment, Playwright exactly 1.62.1, and
Playwright's matching managed Chromium. No API keys or provider calls are needed.

From the checkout root, after installing the hashed Python dependencies:

```bash
npm ci --ignore-scripts --no-audit --no-fund --prefix tools/browser
PLAYWRIGHT_BROWSERS_PATH=0 npm run install-browser --prefix tools/browser
PYTHON="$PWD/.venv/bin/python" npm test --prefix tools/browser
```

On a fresh Linux host, Chromium may need OS libraries. Provision those with
`PLAYWRIGHT_BROWSERS_PATH=0 npx --no-install playwright install --with-deps chromium`
from `tools/browser/`. Windows users can set `PLAYWRIGHT_BROWSERS_PATH` to `0`
and `PYTHON` to their environment's Python path before the equivalent npm commands.
The tests always select the managed browser in the local package; they do not
assume system Chrome is installed. npm package downloads and browser provisioning
require the network. After provisioning, the checks use only local fixtures and
the companion.

The package lock fixes npm tarball integrities. Playwright, its managed browser,
and npm dependencies remain under ignored `node_modules/`; neither the Python
runtime requirements nor the portable workbench ZIP includes this test tooling.
The independent `browser` CI job provisions Ubuntu 24.04, Python 3.12, Node 24,
and managed Chromium. It preserves screenshots and measured contrast in a CI
artifact; the original six verification jobs retain their existing commands.

Fixtures are generated in a fresh system temporary directory and removed after
checks. They include a seven-turn scripted win, one-turn stop, call caps of 19,
10 and 1, cooperative cancellation, a local recording error, malicious model text,
missing PNGs, and actual historical schema-v2 files from `example_run/`, including
archives with omitted resolved replay rows. Counts are checked against native results; the call caps include phase reservation and
therefore do not equal attempts started.

Additional native stops include broadcast-only communication (call cap 7), a
shape-error retry, and completed commitments before resolution fails, both before
and after a resolved turn. Explicit contradictory derivatives disagree with the
checkpoint through a nested turn, nested terminal snapshot, or later phase record.
Both viewers must retain that evidence as resolution unknown, while consistent
unfinished commitments remain labelled unapplied. Communication-only stops must
not claim that commitments completed. The suite checks each missing sensor-image
banner before switching to the final checkpoint, and workbench retry diagnostics.

Companion navigation waits for the initial status lookup and UI render before
keyboard interaction. A regression delays the real local status response and
reproduces the focus replacement window; no sleep or longer timeout substitutes
for application readiness.

The browser context blocks service workers and WebSockets. Request interception
allows only exact temporary companion origins and fixture/build file paths, and
fails any attempted external request. This is browser interception, not OS-level
network isolation. Missing-image tests list their expected failed resource URLs
explicitly; every other console error, page exception or failed resource is an
error. The suite checks keyboard navigation, accessible names, focus styles,
live-region markup and DOM updates, viewport overflow, PNG decoding and a text
contrast sample at 1280×800 and 390×844. Audible screen-reader output, other
browser engines and operating systems are not established by these checks.

Screenshots and contrast measurements go to ignored
`tools/browser/test-results/`. Dated checked-in results and limitations belong in
`docs/verification/`; screenshots are generated evidence rather than fixture data.
