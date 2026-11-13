# Repository review

Reviewed **2026-11-13**, against runtime baseline
[`719c7696c4bfe50934fc936bbccfb62812633164`](https://github.com/dhar174/Parallax-Relay-AI-Game/commit/719c7696c4bfe50934fc936bbccfb62812633164).
This is a documentation and source review with offline reproductions. Runtime code,
tests, dependencies, and committed fixtures were not changed.

## Method and coverage

Inspected every Python module in `parallax_relay/`, the main replay template, the
nine test modules, configuration and dependency files, current documentation,
historical milestone specifications/plans, and fixture manifests/results. Historical
red/green logs were treated as earlier evidence, not current test results. PNG
existence and validity were checked; visual readability was not re-evaluated.

Fresh checks used Linux, Python 3.12.14, Pillow 12.3.0, Pydantic 2.14.3, and httpx
0.28.1. All 72 existing tests passed. Default and fast mock matches won in seven
turns with 63 and 42 calls; the legacy demo also won. Compilation and `pip check`
passed. Additional disposable probes covered the issues and passing edge cases
below. [Verification](VERIFICATION.md) records the commands and limitations.

Official-source excerpts were checked through Context7 for provider contracts;
see [API sources](API_SOURCES.md). No real credentials, provider calls, billing
checks, package vulnerability scan, or cross-platform tests were used.

The planned Codex Security scan could not run: its required `scan-prologue.md`
resource could not be loaded through the skill provider, and no standard-scan host
tool was exposed. No ready preflight or scanner report was produced. The following
security observations are manual source review, not a completed Codex Security scan.
Browser-control and cloud-browser tools were also unavailable. Static HTML/data
checks do not establish rendered usability, mobile layout, or browser execution.

## Priorities and status

P1 blocks a defensible research/live-compatibility claim; P2 affects reliability or
reproducibility; P3 is lower-impact contract or usability work. Priority is not a
security severity score. No exploitable vulnerability was confirmed by this limited
review; that is not a security assurance.

| ID | Priority | Classification | Finding | Status |
|---|---|---|---|---|
| R01 | P2 | Confirmed defect | Non-UTF-8 TOML bypasses CLI error handling | Open |
| R02 | P2 | Confirmed defect | Dollar guard blocks no-cost mock runs | Open |
| R03 | P2 | Confirmed defect | Recording errors bypass finalization | Open |
| R04 | P3 | Documentation mismatch | Non-MOVE zero fields are requested but unenforced | Documented; contract decision open |
| R05 | P2 | Documentation mismatch | Legacy demo overwrites existing output | Documentation corrected; behavior unchanged |
| R06 | P1 | Unverified assumption | Offline wire tests do not establish live compatibility | Open validation gate |
| R07 | P1 | Future enhancement | Fixed room cannot establish general cooperative ability | Open research gate |
| R08 | P2 | Future enhancement | Run artifacts lack full experiment provenance | Open |
| R09 | P2 | Test gap | No CI or supported-environment matrix | Open |
| R10 | P3 | Test gap / future enhancement | Replay browser coverage and partial-run inspection | Open |

## R01: Non-UTF-8 TOML escapes CLI error handling

**Evidence:** `config.py:94–103` catches TOML parse errors, validation errors, and
OSError, but not UnicodeDecodeError from `tomllib.load`. `play.py:132–143` does not
catch it either. A one-byte invalid TOML file produces a traceback and exit 1,
rather than the documented handled configuration error (exit 2). Invalid UTF-8
`.env` is already tested and handled, so the two configuration paths differ.

Reproduce from the activated repository environment:

```python
import subprocess, sys, tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as tmp:
    config = Path(tmp) / 'bad.toml'
    config.write_bytes(b'\xff')
    proc = subprocess.run(
        [sys.executable, '-m', 'parallax_relay.play', '--mock', '--config', str(config)],
        capture_output=True, text=True)
    print(proc.returncode, 'UnicodeDecodeError' in proc.stderr)
# Baseline: 1 True
```

**Impact/remedy:** a local configuration mistake looks like a game defeat or crash.
Normalize decoding errors into a safe ConfigError without echoing source content.
**Acceptance:** subprocess regression exits 2 with a short UTF-8 explanation, no
traceback or secret sentinel, and no match directory.

## R02: Dollar estimate guard can block mock runs

**Evidence:** `play.py:95–96` forwards configured prices in mock mode, and
`budget.py:40–55` reserves estimated provider cost before scripted responses can
report zero usage. With every role priced at input 1/output 2 per million tokens
and `max_estimated_cost_usd=0.001`, the result is `spend_budget` with zero calls.

```python
import asyncio
from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.orchestrator import run_match
from parallax_relay.protocol import ROLES
async def probe():
    result = await run_match(
        {r: ScriptedAgent(r) for r in ROLES},
        MatchSettings(max_estimated_cost_usd=0.001),
        rates={r: Rates(input_per_million=1, output_per_million=2) for r in ROLES})
    print(result.stop_reason, result.budget['calls_started'])
asyncio.run(probe())
# Baseline: spend_budget 0
```

The CLI passes the same settings and prices when a valid priced TOML is selected.
**Impact/remedy:** an otherwise valid live configuration can break offline smoke
runs. Make the CLI's mock cost semantics explicitly zero-cost while retaining call
and turn limits; do not disable guards for arbitrary programmatic agents.
**Acceptance:** mock CLI with a fully priced, tiny-cap configuration wins with no
network traffic; live/synthetic paid-agent cost guards still stop before overspend.
Keep requested versus effective settings clear in the manifest if they differ.

## R03: Recording errors can bypass finalization

**Evidence:** `orchestrator.py:143–224` finalizes after its try block, which catches
only cancellation. Recorder and progress callback exceptions can escape first.
Injecting a recoverable OSError into `Recorder.phase` after three successful
broadcast calls leaves the manifest and three call records, but no `result.json`
or `index.html`. `play.py:138–140` catches local OSError but does not recover output.

```python
import asyncio, tempfile
from pathlib import Path
from parallax_relay.agents import ScriptedAgent
from parallax_relay.orchestrator import run_match
from parallax_relay.protocol import ROLES
from parallax_relay.recording import Recorder
async def probe():
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'run'
        recorder = Recorder(out, {'mode': 'mock'})
        def fail_phase(record):
            raise OSError('simulated write failure')
        recorder.phase = fail_phase
        try:
            await run_match({r: ScriptedAgent(r) for r in ROLES}, recorder=recorder)
        except OSError:
            pass
        print(len((out / 'calls.jsonl').read_text().splitlines()),
              (out / 'result.json').exists(), (out / 'index.html').exists())
asyncio.run(probe())
# Baseline: 3 False False
```

**Impact/remedy:** the broad promise of usable partial output does not hold for
local recording failures. Add best-effort finalization with a sanitized failure
outcome, preserving the last fully recorded/resolved state and original failure.
Do not promise recovery when storage remains unwritable or the process is killed.
**Acceptance:** fault injection at call/phase/turn/finalization boundaries verifies
retained evidence, consistent state, bounded cleanup, and documented exit behavior;
a secondary write error must not hide the original failure or expose raw secrets.

## R04: Non-MOVE zero fields are not enforced

**Evidence:** `protocol.py:99–106` accepts arbitrary integer direction/steps, and
`engine.py:42–56` ignores them for VENT. Passing a parsed VENT with direction 42 and
steps 99 lowers initial heat from 4 to 1, just like the canonical zeros. The prompt
and protocol previously stated that other actions use zeros without explaining the
enforcement gap. By contrast, invalid MOVE parameters are rejected by the engine.

**Impact/remedy:** different agents can submit noncanonical actions with identical
outcomes, complicating contract interpretation and evaluation. The protocol now
states current behavior. Prefer enforcing non-MOVE zeros as engine legality, so an
invalid action consumes a turn instead of receiving a strategic retry.
**Acceptance:** a regression distinguishes canonical VENT from nonzero-parameter
VENT; invalid actions have explicit events and no effect; protocol and schema
policy agree. No behavior was changed in this review.

## R05: Legacy demo overwrites output

**Evidence:** `demo.py:18–20` uses `mkdir(exist_ok=True)` and subsequent writes replace
files. Creating `result.json` containing `SENTINEL` in a temporary directory, then
calling `demo.run(directory)`, replaces it with the match result. The main recorder
uses `exist_ok=False` and has a passing no-overwrite test. The old README's broad
no-overwrite language and command targeting committed `demo_output/` obscured this.

**Impact/remedy:** a developer can overwrite fixtures or prior demo evidence.
README, contributor, running, and verification instructions now use fresh paths and
explain the distinction. For a future code change, make the legacy demo reject
existing output like the main launcher.
**Acceptance:** an existing destination and sentinel remain unchanged with a clear
error; a new directory still produces the seven-turn demo. Runtime remains open.

## R06: Live provider compatibility is unverified

**Evidence:** `tests/test_providers.py` supplies its own response envelopes and
asserts the request fields emitted by `providers.py`. The integration test intercepts
all HTTP and drives the known script. These are useful serialization/control tests,
but not evidence that a real account/model accepts the requests or understands PNGs.

The current references support OpenAI `text.format`, Anthropic's `2026-10-21`
version and `output_config.format`, and Gemini's `responseJsonSchema`. The Anthropic
header was investigated and was **not** confirmed wrong. Gemini documentation also
contains newer output-format/migration guidance; do not apply Interactions API
changes mechanically to the existing generateContent adapter.

**Impact/remedy:** retain a live-validation gate. Independently recheck selected
models, endpoints, supported schema subsets, refusal/truncation envelopes, cache
pricing, and usage semantics before a bounded credentialed run.
**Acceptance:** dated, sanitized smoke results for each claimed provider/model,
including request contract, usage, completion state, and known limitations. Only
run with explicit spending authorization. Until then, label support as implemented
adapters with offline coverage rather than verified model compatibility.

## R07: A fixed scripted room is insufficient research evidence

**Evidence:** `state.py:13–27,64–69` fixes geometry, initial conditions, and goals;
`scripted.py` contains the successful plan. The fixture does not need to interpret
its images or adapt to teammates. Compatible private goals and a fixed room allow
memorized success. `--fast` removes negotiation, not all communication. No repeated
trial, no-communication, observation-ablation, or role-rotation evaluator exists.

**Impact/remedy:** success alone cannot establish causal communication benefit,
vision quality, generalization, or provider ranking. Define baselines, ablations,
held-out room variants, repeated trials, and uncertainty before benchmark claims.
This is a planned research capability, not a malfunction of the current demo.
**Acceptance:** a documented evaluation protocol and reproducible results distinguish
conditions, report all trial outcomes and assignments, and test held-out variants.

## R08: Run manifests lack reproducibility metadata

**Evidence:** `play.py:81–82` records mode, assignments, settings, room, and schema
version. `recording.py:20–28` adds privacy metadata. The manifest has no source
revision, dependency environment, prompt/room/config hashes, explicit start/end
timestamps, or provider API-version record. A generated directory timestamp is not
a substitute, especially with custom `--out` paths.

**Impact/remedy:** saved outputs cannot reliably identify which implementation or
experiment produced them. Add versioned, non-secret provenance and a repeated-trial
runner; document model nondeterminism and provider revisions that cannot be pinned.
**Acceptance:** artifacts reconstruct effective configuration and code/environment
identity without credentials; a reader can aggregate trials and identify incompatible
schemas. Keep backward reading of existing schema-version-2 fixtures documented.

## R09: CI and supported-environment coverage are missing

**Evidence:** the baseline has no CI workflow or package manifest. Dependencies use
ranges; `requirements-tested.txt` pins only direct dependencies from the original
milestone. Fresh evidence covers Linux/Python 3.12; historical evidence covers
Linux/Python 3.13. Python 3.11, Windows, and macOS were not executed in this review.
The source syntax and tomllib dependency support the stated 3.11 minimum, but do
not substitute for running the tests there.

**Impact/remedy:** dependency drift and regressions require manual detection. Add an
offline CI matrix for the declared support policy, then establish a reproducible
development dependency set without confusing it with broad compatibility ranges.
**Acceptance:** CI needs no secrets, runs the full suite and mock checks, reports
its environment, and checks the minimum Python plus declared OS/version targets.
Include regressions for R01–R05 when those fixes are implemented.

## R10: Replay coverage and partial-run inspection need work

**Evidence:** `replay_template.html:32–47` selects only resolved records and filters
call diagnostics to those turns. If a later turn aborts, its calls/messages remain
in JSONL but have no selectable record. The empty-run branch returns before drawing
call diagnostics. There is no final-state selection for a successful nonempty run,
although the final PNG exists. The current docs now explain the before-action view.

Static checks confirmed fixture PNG references, valid PNGs, no external script
sources, text-based model-output rendering, and hidden-control handling in source.
Current browser execution, keyboard navigation, layout at narrow widths, and
contrast were not verified. Historical browser evidence is separately labeled.

**Impact/remedy:** users must inspect JSONL for unfinished rounds. Add a partial/final
state view and reproducible browser coverage before claiming a polished spectator
experience. Keep the main and legacy viewers' capabilities distinct.
**Acceptance:** browser checks cover previous/next/slider navigation, zero-turn and
partial-turn failures, final-state inspection, keyboard focus, escaped adversarial
text, missing images, and narrow-screen overflow. Existing runs remain readable.

## Passing edge cases and security observations

- Cancelling while all players sleep between retries produced `cancelled`, three
  logged attempts, and a final result. No cancellation defect was reproduced there.
- Settling partial usage `Usage(100, None)` retained the reserved quote, counted one
  unknown-usage call, and released all remaining reservations.
- A malformed Gemini nested envelope became retryable `invalid_provider_response`.
- Existing tests passed for phase barriers, role-local notes/history, hidden-state
  pixel isolation, duplicate keys/types, redirect rejection, safe errors, budget
  stops, replay script escaping, and provider-failure partial output.
- Source review found fixed provider endpoints and no model action surface beyond
  validated game commands. Prompts are not a security boundary; the engine and
  serialization paths enforce the relevant limits.
- Spectator outputs expose all goals/notes intentionally. Arbitrary in-process agents
  are trusted code. The public-event sanitizer is pattern-based, so new event types
  need explicit disclosure review and tests.

## Recommended sequence

First fix R01–R03 with narrow regressions, settle R04, and align legacy output
handling (R05). Add CI/environment coverage (R09) and validate real-provider behavior
(R06) before claiming reliable live execution. Add provenance (R08) before comparative
evaluation (R07). Improve replay coverage and presentation (R10) as a separately
scoped change. No runtime finding is claimed fixed by this documentation pass.
