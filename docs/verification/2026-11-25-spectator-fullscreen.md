# Spectator fullscreen and follow camera — November 25, 2026

Verified [issue #58](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/58)
with the real-time loopback spectator on Windows. A scripted reactive match
advanced through multiple windows while native fullscreen followed SPECTRA.
The match kept its run ID and later reached the team checkpoint.

| Check | Result |
| --- | --- |
| Managed Chromium 151.0.7922.34, Playwright 1.62.1, Node 24.22.3 | 53 browser checks passed. |
| Headed Chrome 158.0.8127.36 and Edge 158.0.4370.33 | Verified actual stage fullscreen, exit from the app, re-entry with the selected camera, and native Escape with focus returned to the launcher. |
| Python 3.12.10 offline unittest discovery | 503 tests reported, OK with 6 filesystem-link skips. The test process used `GIT_CONFIG_COUNT=0`. |
| Dependency, compile, and mock checks | `pip check` and `compileall` passed. Both mock modes won in seven turns with 63 and 42 calls, five energy, and all scores 100. |

The browser regressions verify the real `document.fullscreenElement`, all three
follow targets, frame containment at both banks, jump and respawn samples,
manual room-pan restoration, and incoming dialogue while the speech reader is
open. Separate emulated touch runs exercise denied and unavailable fullscreen
requests at 320 px and 390 px, portrait-to-landscape resizing, reduced motion,
Escape, and restoration of a scrolled dashboard. The portrait regression also
checks that simultaneous bubbles leave the followed robot visible. These are
Chromium touch emulations. Physical phone browsers and non-Chromium engines
are outside this verification record.

The test suite writes `fullscreen-whole-room.png`, `fullscreen-follow.png`, and
`game-only-320.png` under `tools/browser/test-results/realtime/`.

## PR #63 review follow-up

Five Chromium regressions reproduced the review findings on the original PR
head. They check the dashboard launcher and both presentation modes at 320 px
with simulated doubled root text, the followed robot's visibility at 568 × 320,
all three speech previews at 568 × 200, and stable speech positions across a
one-tick movement at 780 × 320. The updated presentation wraps the controls and
gives speech a separate bounded reading area. Ordinary dashboard overview keeps
the anchored speech bubbles.
