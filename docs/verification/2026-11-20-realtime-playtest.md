# Real-time development playtest · November 20, 2026

The Raised Span fixture reached extraction in three windows for all nine
conditions. With short synthetic delays the full discussion/action cycle took
roughly four to six seconds. Repeating the November 15 delays extended a
full cycle to about 25 seconds under either clock. The continue clock let the
simulation advance about 22.6 seconds between sampling and release.

## Short synthetic delays

Each row is one fresh run of the offline HTTP fixture at 60 Hz, with a
four-window cap, a five-second phase timeout, and the freeze clock. Every
variant changes one setting from the first row. Two communication rounds means
broadcast, negotiate, then commit. One round means broadcast then commit.

| Setting changed | Attempts | Completion tick | Run wall time (s) | Cycle range (s) | Worst action pacing lag (ms) |
|---|---:|---:|---:|---:|---:|
| 120 ticks, 8 points, two rounds | 27 | 288 | 14.44 | 3.69–5.13 | 250 |
| 60 ticks | 27 | 169 | 12.47 | 3.78–4.08 | 164 |
| 180 ticks | 27 | 408 | 16.38 | 3.69–6.05 | 297 |
| 6 action points | 27 | 289 | 14.98 | 3.84–5.27 | 431 |
| 10 action points | 27 | 280 | 14.27 | 3.58–5.12 | 222 |
| One communication round | 18 | 288 | 11.67 | 2.83–4.22 | 314 |

All short-delay runs recorded zero fallbacks and timeouts. They recorded three
takeoffs, three landings, and zero side or underside contacts. The shorter
action window and one-round variant finished sooner in these samples. They
still needed three windows. One run per setting leaves the play feel and
timing variance open.

## Repeated historical delays

The fixture repeated the same nine measured role/phase delays in each window
through local MockTransport. Both 20-second conditions used 120 ticks, eight
points and two communication rounds. The five-second trial changed only the
freeze condition's phase timeout. [November 15 timing source](2026-11-15-slice7-live-retry-summary.json)

| Clock and cutoff | Accepted / attempted | Timeouts | Fallback slots | Final tick | Run wall (s) | Discussion range (s) | Cycle range (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Freeze, 20 s | 27 / 27 | 0 | 0 | 288 | 72.735 | 22.30–22.39 | 23.23–24.55 |
| Continue, 20 s | 27 / 27 | 0 | 0 | 4,354 | 74.485 | 22.80–22.97 | 23.69–25.17 |
| Freeze, 5 s | 21 / 27 | 6 | 6 | 288 | 38.953 | 11.05–11.17 | 11.92–13.25 |

| Clock at 20 s | Shared start ticks | Sample age before release (ticks) | Discussion / action | Worst host lag, action / discussion (ms) |
|---|---|---|---:|---:|
| Freeze | 1, 121, 241 | 0, 0, 0 | 12.9× | 213 / — |
| Continue | 1,357, 2,833, 4,307 | 1,356, 1,356, 1,354 | 12.9× | 259 / 337 |

All three slots in each historical window recorded the same start tick. The
20-second schedules matched the released programs at offset zero. Freeze had
zero ticks between sampling and release. All 4,066 such ticks under continue
used neutral programs. At five seconds, two broadcast slots timed out per
window and contributed no speech. Every commit was accepted, and the offline
controller still completed the puzzle. All three historical trials recorded three takeoffs, three landings, and
zero side or underside contacts. The separate
manual jump exercise changed PYRA’s offset alone and produced a far-bank contact
at tick 156 and a deck landing at 159, then recovered at tick 437.
[Manual walkthrough](../REALTIME_DEMO.md#walk-through-a-manual-crossing)

### Latency and barrier waiting at the 20-second cutoff

Cells give the minimum, median, and maximum wall-clock request latency in
seconds. Each row aggregates nine attempts within each mode.

| Group | Freeze | Continue |
|---|---|---|
| SPECTRA | 2.75 / 3.03 / 5.12 | 2.80 / 3.09 / 5.20 |
| PYRA | 2.42 / 2.81 / 3.83 | 2.45 / 2.92 / 3.89 |
| FLUX | 1.22 / 1.33 / 16.19 | 1.25 / 1.42 / 16.28 |
| Broadcast | 3.83 / 5.12 / 16.19 | 3.83 / 5.12 / 16.28 |
| Negotiate | 1.22 / 2.42 / 3.03 | 1.25 / 2.47 / 3.11 |
| Commit | 1.33 / 2.75 / 2.89 | 1.41 / 2.83 / 2.94 |

The median and maximum wait from a role’s disposition to phase close were
0.67 and 12.39 s for freeze, and 0.69 and 12.47 s for continue. From commit
readiness to the shared start, the median and maximum were 0.11 and 1.61 s for
freeze, and 0.38 and 1.92 s for continue.

In each 20-second condition, 24 of 27 attempts (88.9%) finished within 15 s. The
slowest historical broadcast exceeded 15 s in all three windows. The proposed
paid demonstration targets at least 90% within 15 s and two completed windows
or earlier genuine completion. These nine repeated delays describe scheduler
behavior under one observed turn-based pattern. They provide no measurement of
real-time provider latency or model cooperation. No paid calls were made.
[Proposed demonstration](../REALTIME_ENGINE_PLAN.md#one-proposed-live-invocation-for-later-authorization)

## Reproduce and inspect

Use the local virtual environment. Start a fresh run for each variant. The
short-delay row uses the first command. Change only the setting shown in the
table for each variant. The second command repeats the 20-second historical
freeze run. Set the clock to `continue` for its paired run or keep `freeze`
and lower the timeout to five seconds for the cutoff comparison.

```bash
python -m parallax_relay.realtime --offline test --windows 4 --window-ticks 120 --action-points 8 --communication-rounds 2 --clock freeze --latency demo --phase-timeout 5
python -m parallax_relay.realtime --offline test --windows 4 --window-ticks 120 --action-points 8 --communication-rounds 2 --clock freeze --latency historical --phase-timeout 20
python -m parallax_relay.realtime --verify-record PATH
```

The short-delay grid and five-second cutoff are stored under
`runs/verified-playtest-20261120T065822Z/` in the local worktree. The 20-second
records are `runs/verified-historical-freeze/` and
`runs/verified-historical-continue/`.
Each of the seven fresh launchers returned exit code 0. Each of the nine
physics recordings passed `--verify-record` with exit code 0, matching the
recorded final tick, completion state, and stop reason.

Discussion runs from broadcast open to shared release. Action runs from
release to checkpoint. The cycle ranges include the partial last action window.
Sample age counts the committed ticks after the sample and before release.
Pacing lag is the largest host tick lateness against its scheduled wall time.
Browser paint latency was outside this measurement. All runs used one Dell
Windows checkout and one development room. Each condition is a single local
sample and can reflect host scheduling and journal I/O. These aggregates omit the
contents of role requests, feeds, and private records.

## Received state to displayed robot positions

A separate reactive match in managed Chromium 151 at 1280 × 800 finished at
tick 288. For each distinct last pose in a poll response, the browser probe
measured from completed JSON decoding to the first animation frame where the
displayed tick and all three foot anchors matched the server within one CSS
pixel. All 58 samples matched on that first frame. Median delay was 2.5 ms,
95th percentile 5.9 ms and maximum 20.6 ms. The 37 samples with a position
change measured 2.7 ms, 5.9 ms and 17.5 ms respectively. The client coalesced
48 intermediate pose rows in those responses. Polling wait, network transit,
compositing and the physical display are outside this measurement.
