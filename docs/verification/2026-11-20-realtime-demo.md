# Raised Span offline verification

The implementation used for the final provider-adapter rehearsal is local commit
`0c852df76ce226eccd95054cc8c8f6c94c0950ab`, based on main at `c18cd10`
(PR #53). The recording reports that exact source revision and a clean worktree.
The v2 run ID is `32c570fa-c73c-4b5d-9530-cc7143156fa6`. Its public result,
private accounting and per-tick recording are available in the ignored local
directory `runs/verified-engine-0c852df`. [Interactive walkthrough](../REALTIME_DEMO.md)
· [Approved plan and action contract](../REALTIME_ENGINE_PLAN.md)

## Rehearsal

The native provider adapters received three different role projections. Two
OpenAI clients and one Gemini client used an offline HTTP transport with
synthetic responses. The private journal paired all 27 attempts with their
settlements. The first commit reached readiness at 0.250 s for SPECTRA, 0.563 s
for FLUX and 0.953 s for PYRA. Each readiness event was on tick zero. Every
robot began its program at tick 1, then at ticks 121 and 241 in subsequent
windows. All three were grounded at extraction at tick 288. Replay checked all
288 state hashes and returned the matching run UUID with bound identity.

The motor vent and reroute occurred on tick 1. In the second window FLUX, PYRA
and SPECTRA left the deck on ticks 126, 134 and 142. They landed on the far bank
on ticks 156, 164 and 172. The shard, cell and unlocked exit were recorded at
tick 181. The separate manual walkthrough reached extraction on tick 281.
Changing only PYRA's jump offset from 16 to 0 caused contact with the raised
face at tick 156 and a deck landing at 159. Recovery finished at tick 437.
[Commands for both manual outcomes](../REALTIME_DEMO.md#walk-through-a-manual-crossing)

## Spectator captures

All five images show the local Chromium spectator and public offline dialogue.
The desktop viewport is 1280 × 800 and the mobile viewport is 390 × 844.
Ticks and event cursors were read adjacent to capture. A moving scene may
advance between the rendered image and the receipt.

| Capture | Run UUID | Window / tick / event |
|---|---|---|
| [Two robots ready, PYRA pending](realtime-room-2026-11-20/discussion-ready.png) | `6ecd004a-e734-4fe3-9283-d35d191e689c` | 1 / 0 / 27 |
| [Three airborne robots](realtime-room-2026-11-20/jump.png) | `34c894fe-9550-46b2-89bf-a307d88b68c8` | 2 / 150 / 112 |
| [Powered bridge and completed extraction](realtime-room-2026-11-20/extraction.png) | `34c894fe-9550-46b2-89bf-a307d88b68c8` | 3 / 288 / 197 |
| [Manual early jump and contact log](realtime-room-2026-11-20/failed-contact.png) | `fc33dd57-1ff1-4821-8c4c-38e346887a5a` | 3 / 240 / 151 |
| [Mobile public discussion](realtime-room-2026-11-20/mobile.png) | `0fdbd1c6-235a-4955-8818-8b440c84fda4` | 1 / 0 / 14 |

The failed-contact capture is the browser regression's SPECTRA trial. RUN right
for 60 ticks with jump offset 0 meets the wall at tick 156 and lands on the
deck at 159. Starting from the same checkpoint with offset 24 reaches the far
bank. The PYRA trial in the walkthrough exercises a separate manual solution.

## Verification scope

The frame packer reproduced 42 registered frames, nine packed sheets, nine GIFs
and six contact sheets from the checked-in sources. Reviewers inspected all
three robots at 64 px and observed the takeoff, ascent, descent and landing
states in Chromium. SPECTRA's walk still reads stiffly in some frames. FLUX's
pincer detail can merge at small scale. Its idle art sits 0.75 CSS px above the
foot pivot in a 64 px cell. [Art sources, registration and previews](../../tools/realtime_spectator/art/README.md)

The timing trials used Raised Span only. The six held-out rooms contributed
no tuning data. The original PNG renderer serves role-specific horizontal
sensor schematics, with height and velocity supplied by the real-time text
HUD. The development HUD and game are a separate protocol. The established
turn-based evaluation retains its own build and contracts. [Timing trials](2026-11-20-realtime-playtest.md)

The independent supervisor tests used local child processes and intercepted
transports. They exercised a hard time limit, control-pipe loss, a worker
stuck in cleanup, and recovery of unsettled price quotes. The Ctrl+C path
used a simulated Python interrupt. Screen-reader audio and physical screen
latency were outside the Chromium checks. Project-specific provider access,
remote schema acceptance, real model play and actual billed usage require
the separate live-run authorization.

## Offline checks on Windows

The locked environment used Python 3.12.10. The browser harness used Node
24.22.3 and the matching managed Chromium. Each command below completed
with exit code zero.

| Command or check | Observed result |
|---|---|
| `python -m pip check` and `python -m compileall -q parallax_relay tests scripts site tools/realtime_spectator` | Dependencies consistent, compilation successful |
| `python -m unittest discover -s tests -v` | 495 tests in 258.577 seconds, OK with six skips for unavailable filesystem link creation on this Windows host |
| `python -m parallax_relay.play --mock` and `--mock --fast`, then `python scripts/check_mock_runs.py` | Both seven-turn victories, 63 and 42 calls, five energy, all scores 100 |
| `python scripts/check_rooms.py` | All nine original fixture certificates checked |
| `python site/build_workbench.py`, Node syntax checks and `node --test --test-concurrency=1 tests/test_workbench_web.mjs` | Built workbench and 77 passing Node tests |
| `npm test --prefix tools/browser` | 44 passing Chromium tests including seven real-time spectator tests |
| `python tools/realtime_spectator/pack_art.py --check` | Nine clips, 42 frames, nine GIFs and six contact sheets reproduced |
| `python -m parallax_relay.realtime --check --profile dev-bridge-live-v1` | Zero provider calls, opening reservation $0.0217970, $0.9782030 remaining estimated headroom |
| `python scripts/check_committed_diff.py` and `git diff --check origin/main...HEAD` | Committed source diff passed whitespace checks |

## Restart Match follow-up · November 20, 2026

The reactive demo finished at tick 288. Clicking **Restart Match** in the
browser returned to tick zero on the same URL with a new run ID. The preceding
recording still replayed to the completed checkpoint. A Chromium regression
restarted an ongoing manual match after the bridge was powered. Both open tabs
showed the bridge retracted at tick zero, with the public event lists empty and
the manual draft cleared. The new match opened fresh manual command slots
after Start. The interrupted recording replayed to tick 120 with a
`cancelled` outcome.

All 45 Chromium checks, 77 Node workbench checks and 12 focused loopback tests
passed. The loopback checks include concurrent restart requests, stale match IDs
and the live-mode guard. The final Python run completed 496 tests with six
Windows filesystem-link skips. All matches in these checks were offline.

## Authorized live model run · November 20, 2026

The single Raised Span run used independent `gpt-6-luna` contexts for SPECTRA
and PYRA, and `gemini-3.5-flash-lite` for FLUX. The four-window, 36-attempt,
240-second profile used a $1 local estimated spending limit. The live
spectator opened during the first window. The launcher exited zero with
`window_limit` at tick 480. Deterministic replay verified all 480 ticks with
bound run identity.

PYRA vented and FLUX powered the bridge on tick 1. SPECTRA collected the shard
and unlocked extraction on tick 148. SPECTRA and PYRA reached extraction.
FLUX finished on the deck below the raised bank, so the team checkpoint
remained incomplete. The three roles shared each of the four release ticks
(1, 121, 241 and 361).

| Role | Attempts | Accepted replies | Latency minimum / median / maximum |
|---|---:|---:|---:|
| SPECTRA | 12 | 12 | 1.812 / 3.156 / 9.890 s |
| PYRA | 12 | 12 | 2.016 / 3.071 / 13.344 s |
| FLUX | 12 | 11 | 0.734 / 1.102 / 1.657 s |

The validator rejected FLUX's fourth-window commitment as an invalid action
plan. All 36 attempts returned within 15 seconds. Median latency was
2.593 seconds and elapsed match time was 68.359 seconds. The budget settled
all 36 attempts, with reported input and output usage for each. The
$0.0297597 local estimate uses the profile rates and reported usage.

The recorded source revision was `f75b06d` with the Restart Match work
present as local modifications. This single run demonstrates live provider
integration and partial team progress on one development room. The published
evidence consists of aggregate counts, timings and outcomes. Full journals,
private role data and sensor images remain in the ignored local recording.
