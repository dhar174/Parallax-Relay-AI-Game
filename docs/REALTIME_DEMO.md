# Real-time development demo

Cross a retractable bridge with SPECTRA, PYRA, and FLUX. PYRA cools the motor so
FLUX can power the bridge. The robots must jump onto the raised far bank, where
SPECTRA retrieves the shard. The checkpoint completes when all three robots are
grounded in the extraction zone.

## Start a local match

Use the virtual environment from the repository setup and run from the checkout
root. [Dependency setup](../CONTRIBUTING.md#environment)

```bash
python -m parallax_relay.realtime --offline reactive --spectate
```

Open the printed `http://127.0.0.1:<port>/` URL and select **Start match**.
The scene is labeled **Raised Span**. The reactive offline controller chooses
commands from each robot's sampled observations and public dialogue. This fixture
exercises the scheduler and puzzle. Real-time model cooperation requires separate
evaluation.

The **Relay team** cards show readiness during each discussion phase. The stage
shows positions and speech bubbles as the simulation runs. **Public dialogue**
and **Room events** show the discussion and physical consequences. Use **Choose
view** to inspect the optical, thermal, or circuit PNG sampled at the start of
the current window. Select **Spectator view** to watch the whole room. Open
**Released plans** to check the programs and their shared start tick.

The spectator runs on the local machine. Keep the launcher open to revisit the
match or reconnect the browser. Press Ctrl+C in the launcher to close the
viewer. Start a fresh launcher for each new match. The offline modes use no
provider credentials or calls.

The verified walkthrough includes Chromium captures of readiness, the jump,
extraction, and a failed manual crossing. [Screenshots and recording evidence](verification/2026-11-20-realtime-demo.md)

## Walk through a manual crossing

```bash
python -m parallax_relay.realtime --offline manual --spectate
```

Open the printed URL and select **Start match**. The local controller supplies
the public dialogue while you choose the robots' commands. In **Manual controls**,
build the sequence for each role in the listed order. Use **Add command** and
**Remove command** to match the table. For each RUN choose **Right**, enter
**Duration (ticks)**, and leave **Jump at tick** blank unless the table gives
an offset. Offset zero jumps on the first tick of that RUN. During commitment,
select **Seal SPECTRA plan**, **Seal PYRA plan**, and **Seal FLUX plan** in
any order. The window starts once all three plans are sealed. Update the rows
before sealing the next window.

Each window allows up to four commands, eight action points, and 120 ticks.
A RUN costs one point per 15 ticks rounded up, plus two points for a jump.
A WAIT is free. JUMP, VENT, REROUTE, and COLLECT each cost two points and take
one tick. The editor shows validation and points remaining.

| Window | SPECTRA | PYRA | FLUX |
|---|---|---|---|
| 1 | RUN 80 | VENT, RUN 32 | REROUTE, RUN 48 |
| 2 | RUN 36 with jump 0, WAIT 6, COLLECT | RUN 65 with jump 16 | RUN 52 with jump 0 |
| 3 | RUN 44 | RUN 47 | RUN 28 |

With the default frozen discussion clock, the windows start on ticks 1, 121, and
241. In the first window, VENT and REROUTE take effect before movement. In the
second, SPECTRA collects the shard on tick 163 and PYRA lands on the far bank on
tick 167. The exit unlocks when SPECTRA collects the shard. The team reaches the
checkpoint on tick 281.

To see a jump fail from the same starting position, start a fresh manual match
and change only PYRA's second-window jump from 16 to 0. PYRA hits the raised
face on tick 156 and lands on the deck on tick 159. The third window leaves
PYRA below the far bank while the other two wait at extraction. To recover in
window four, give SPECTRA and FLUX WAIT 1 and give PYRA RUN right for 80 ticks
with jump offset 0. PYRA jumps from the lip, lands on the far bank, and reaches
the checkpoint on tick 437.

## Watch the paced turn-based fixture

```bash
python -m parallax_relay.realtime --offline baseline --spectate
```

Open the printed URL and select **Start match**. The spectator shows the
turn-based fixture's public discussion and discrete tile updates. Use the
experiment workbench for turn-based configuration and replay imports. The
fixture demonstrates the event and display paths. [Workbench guide](WORKBENCH.md)

## Exercise the HTTP adapters locally

```bash
python -m parallax_relay.realtime --offline test --spectate
```

Open the printed URL and select **Start match** in the **Offline HTTP adapter
test** viewer. SPECTRA and PYRA use independent OpenAI adapters. FLUX uses the
Gemini adapter. A local MockTransport wraps the offline controller's replies in
provider response shapes. The run exercises the HTTP contract without provider
calls. The recording identifies this source as `offline_test_transport`.

Add `--latency historical --phase-timeout 20` to repeat the nine measured role
and phase delays from the November 15 turn-based smoke. This offline replay
uses historical timings to exercise the scheduler. Real-time provider latency
and the desired quick-play rhythm remain open playtest questions.

## Compare offline timing

Recorded examples in the manual walkthrough use the default freeze clock. To
compare it with continued gravity and contacts during discussion, add
`--clock continue` to an offline physics launch. Each role still uses one
sample per window and all plans start on a shared tick. Use
`--communication-rounds 1` to run broadcast and commit. The default of two adds
negotiation between them. Use `--window-ticks`, `--windows`, and
`--action-points` to vary the physics limits. Set `--phase-timeout` in seconds.

## Verify a physics recording

Use the output directory printed by the launcher in place of `PATH`. Individual
launches create a fresh directory under `runs/`. An optional `--out` takes
a fresh directory path. The verification command reruns the recorded input
schedule and compares state hashes across simulation ticks. Check the stop
reason and the completion state in the output. The directory contains privileged
role recordings and sampled images, so keep it local. [Record formats](PROVENANCE.md#real-time-development-records)

```bash
python -m parallax_relay.realtime --verify-record PATH
```

## Proposed paid demonstration

The offline profile check reports the effective roster, limits, estimated
reservation for the opening broadcast, remaining estimated headroom, and the
proposed launch command. It uses the local proposal and makes no provider calls.

```bash
python -m parallax_relay.realtime --profile dev-bridge-live-v1 --check
```

| Setting | Proposed value |
|---|---|
| SPECTRA and PYRA | Independent OpenAI `gpt-6-luna` contexts |
| FLUX | Gemini `gemini-3.5-flash-lite` |
| Windows | At most four, 120 ticks each, at 60 Hz |
| Provider attempts | At most 36, one per role in each of three phases per window |
| Time | 20 seconds per phase, 240 seconds total, with up to five seconds of cooperative cleanup |
| Token limits for accounting | 4,096 output tokens and an 8,192 image-token reserve per attempt |
| Spend estimate | $1.00 maximum local estimate. Provider billing can differ. |

The standard list rates checked on November 20 are $0.10 input and $0.50 output
per million tokens for Luna, and $0.30 input and $2.50 output per million for
Flash-Lite. Project access and acceptance of this exact game schema require the
authorized run. [OpenAI model and pricing](https://developers.openai.com/api/docs/models/gpt-6-luna.md)
· [Google standard pricing](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite)

The initial latency target is at least 90% of attempts within 15 seconds.
The historical-delay offline rehearsal met that threshold on 24 of 27 attempts
(88.9%). It took roughly 23–25 seconds of wall time per discussion and action
cycle. [Development-room timing trials](verification/2026-11-20-realtime-playtest.md)

Any provider invocation requires separate explicit approval for one paid run
with this roster and these bounds. Revalidate model availability and the dated
prices and check credentials locally before that invocation. The profile reserves
a full phase before dispatch and retains estimates where usage is unknown.
Further paid attempts require their own approval. [Engine plan and acceptance criteria](REALTIME_ENGINE_PLAN.md)
