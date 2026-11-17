# Qualification Q — awaiting separate spending approval

**No live execution is authorized by this document.** The user-approved completion
plan requires separate Q, pilot and confirmation approvals. The following is the
concrete Q proposal after offline verification, not authorization for later stages.

## Frozen proposal

- Source: `9b3b6b570c9cff4ed66f2e1fe4b36e0c7ba830f8`, clean execution worktree.
- Environment SHA-256: `2714166a1cb6eb93e6169d07be8354ccd7f6ca1ad319aa512297d1629903f19f`.
- Registration checksum: `975886442d883cbe4dce9b4e427e22e9249e4ef05e1e5b547d9491f3b6f75ccd`.
- Candidate receipt checksum: `286cdd43efdba46cd02a9df14708b5714d514ec1519b5013a3253edc3d6cb500`.
- Specification checksum: `a2dbb698abb2c4b1cb0616228a2df92d55ce436d669aa2f64bbb8cf2ef245575`.

The local native registration is
`/workspace/scratch/parallax-assurance-integration/runs/qualification-registration-9b3b6b5/registration.json`.
Its checksum and 15 scheduled trials were read back and verified. No started
marker or execution ledger exists. An earlier unrun registration at `2ac6df1`
is superseded after the Windows correction and retained unchanged.

Q selects two independent OpenAI **gpt-6-luna** entries and one Gemini
**gemini-3.5-flash-lite** entry, covering all three unique role assignments and
all five arms. It uses only development room split_span and no baseline teams:
**15 model matches**, each at most two turns, with **432 maximum total provider
attempts**. Per-match limits: 36 calls, two attempts, 60-second request timeout,
4,096 output tokens, four history turns, retry delay 0.5 seconds, failure limit
three, image reserve 8,192. Launches are serial with a one-second minimum interval
and scheduler seed zero.

## Cost interpretation

The registered local estimate guards are **$0.65 per match and $9.75 for Q**.
They use the larger of nominal and all-OpenAI-input-cache-write scenario guards,
with 10% margin rounded upward to a cent. This is conservative admission exposure,
not an expected charge or a provider invoice ceiling.

Configured standard input/output rates per million tokens remain OpenAI
$0.10/$0.50 and Gemini $0.30/$2.50. Official references were rechecked November 16.
OpenAI's documented default 30-minute cache writes can charge $0.125/M input;
the separately labeled scenario treats all OpenAI input at that rate. Actual cache
activity is unknown, and the existing adapter does not separately settle cache-write
charges. Nominal Q comparison is $9.15; the selected guard is the higher $9.75.
The [preparation PR](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/46)
contains the full worksheet, sources and limitations. No cache-control wire changes
or billing guarantees are introduced.

Pilot ($2,216.25 current admission exposure) and confirmation ($26,595.00) are
separate prospective stages and are **not** included in this approval request.
Their registrations, feasibility evidence and spending approvals remain later gates.

## Capacity and launch controls

The current metadata-only environment check reports existing OPENAI_API_KEY and
GEMINI_API_KEY bindings ready; no values were collected or published. Remote
account access, quota and free-tier eligibility remain unverified. Q is the bounded
compatibility test; rate/quota failures are recorded failures, not permission to
retry or substitute a model.

Measured free storage was 29,127,614,464 bytes; require at least 1 GiB immediately
before launch. The offline 45-trial, two-turn diagnostic used approximately 8.8 MB;
this is a planning observation, not a model-run storage upper bound. Provider
latency is unmeasured on this source. The conservative request-timeout component
is 8,676 seconds (about 2h25m), plus teardown and filesystem/system delays; it is
not a wall-clock guarantee or expected duration.

After approval, record the actual process identity, exact command, output/exit
receipt and checkpoint before monitoring. Planned log/exit receipt names are
`/workspace/scratch/qualification-9b3b6b5-live.log` and
`/workspace/scratch/qualification-9b3b6b5-live.exit`; the continuation checkpoint is
`/workspace/scratch/parallax-completion-checkpoint.md`. If execution is long and no
independent work remains, schedule ten-minute heartbeats in this chat, each making
one lightweight status check. Never duplicate a worker, delete markers, silently
resume, replace trials, raise caps or launch another paid cohort. Pause monitoring
when finished and inspect the exit code, ledger, all artifacts and coverage.

Proposed single invocation, using the existing configured credentials:

```bash
cd /workspace/scratch/parallax-assurance-integration
/workspace/scratch/parallax-assurance-locked/bin/python -m parallax_relay.campaign run \
  --campaign runs/qualification-registration-9b3b6b5 --live
```

Before launching, recheck the frozen source/environment/registration and available
disk. Keep this checkout unchanged. Afterward, require successful observed
role/phase coverage across all assignments/arms, valid replies, complete cleanup
and reconciled accounting. Preserve any failure; no automatic paid relaunch.
