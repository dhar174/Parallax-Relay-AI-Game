# Live spectator speech bubbles — November 24, 2026

Verified [issue #57](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/57)
offline on Windows with Python 3.12.10, Node 24.22.3, Playwright 1.62.1, and
managed Chromium 151.0.7922.34. The narrow-screen regression first failed at
320 px because the old bubble hid SPECTRA’s message.

The regression exercises the actual loopback spectator with a controlled journal.
It verifies three concurrent messages at 320×780 and 390×844, including wrapping
an unbroken token and preserving Unicode and line breaks. It checks that the
grounded robots remain visible in the crowded layout, the longest messages reach
their final lines, text size and pause controls work, and a sensor-view round
trip restores the scroll position. The stage reader keeps the selected message
open when new dialogue arrives. Keyboard opening, Previous/Next, Escape, focus
restoration, reduced motion, panning, and inert model text are covered. A short
message fits on the 1280×800 desktop stage.

The browser run writes `speech-320.png` and `speech-reader-390.png` under
`tools/browser/test-results/realtime/`. These show the crowded stage and the
complete-message reader. The scroll clock uses an estimated speaking rate.
The browser evidence applies to Chromium at the tested viewport sizes.

| Check | Result |
| --- | --- |
| `npm test --prefix tools/browser` | 48 passed, including the two speech regressions |
| `python -m unittest discover -s tests -v` | 503 tests reported, OK with 6 skips |
| `python scripts/check_mock_runs.py` | Both modes won in seven turns, with 63 and 42 calls, five energy, and all scores 100 |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q parallax_relay tests scripts site` | Passed |
| `node --check` on the changed JavaScript and browser test | Passed |

The first Python run reported six errors after Windows dropped an empty injected
Git config value while restoring the environment. A standalone `git rev-parse`
probe reproduced the error after the same environment reset. The passing rerun
used `GIT_CONFIG_COUNT=0` in its test process. The six skips concern unavailable
filesystem links.

## Review follow-up

The crossing regression reverses the horizontal order of three scrolling
speakers at 320 px with two pixels of motion. On the initial PR head, SPECTRA and
FLUX swapped rows at 6 px and 98 px. With stacked rows assigned in role order,
all speakers kept their vertical positions and the bubbles stayed within the
stage. All three focused speech checks passed in Chromium.

The re-review found the regular layout could still swap rows. An additional
320 px regression with two scrolling messages and one short message reproduced
a 120 px swap near the top edge. Both placement paths now process speakers in
role order. The compact and regular crossings passed alongside both existing
speech checks in Chromium.
