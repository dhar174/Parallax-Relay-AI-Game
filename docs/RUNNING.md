# Running Parallax Relay

Install dependencies and activate the virtual environment using the
[README](../README.md). Run commands from the checkout root.
The default installation uses the hashed development lock plus the compatibility
ranges. See [Contributing](../CONTRIBUTING.md#environment) for applicability,
fresh-environment setup, and lock updates. The historical direct-version file is
not a complete lockfile.
The [support policy](../CONTRIBUTING.md#supported-environments-and-ci) distinguishes
the configured CI matrix from actual verification evidence. Run
`python scripts/check_mock_runs.py` to assert both scripted victories using
temporary output directories; it returns 1 on a failed CLI or unexpected result.

## Offline modes

```bash
python -m parallax_relay.play --mock
python -m parallax_relay.play --mock --fast
python -m parallax_relay.play --mock --max-turns 1
```

Mock mode uses scripted agents through the normal observation, messaging,
validation, orchestration, and recording path. It does not load `.env`, resolve
credentials, or contact a provider. It still loads and validates the TOML file and
applies its call/turn/retry limits. For these known zero-usage scripted agents, the
CLI clears only the effective `max_estimated_cost_usd` cap. A valid fully priced
configuration can therefore be reused for mock runs even with a tiny dollar cap.
The original configuration is not mutated; validation still requires complete
pricing when its requested cap is enabled. This override does not apply to live
runs or direct programmatic `run_match` calls.

Successful mock results report `estimated_cost_usd=0.0` with complete pricing and
`null` without complete pricing; null means no complete estimate is available,
not that the scripted fixture made paid requests. Prices and usage accounting are
retained. The manifest records effective `settings` and mock-only `requested_settings`
(after CLI overrides, before clearing the dollar cap).

Normal mode uses broadcast, negotiation, and commitment. Fast mode skips negotiation.
The one-turn example intentionally stops with `turn_limit`, `completed=false`, and
`scores=null`; it is not an engine defeat.

The original standalone demo bypasses the orchestrator and uses an older replay
format. Run it without arguments for a fresh directory:

```bash
python -m parallax_relay.demo
```

It creates `runs/demo_<UTC timestamp>_<six hex characters>/` and prints the replay
path. An explicit `--out runs/legacy-demo-01` is also supported. Existing destinations
(including empty directories or files) are rejected with exit 2; matching files are
never overwritten. Use a new path or omit `--out` on subsequent runs. Keep the
committed `demo_output/` as historical evidence.

## Configure providers

Copy the blank `.env.example` template to `.env` with your editor and populate:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY`, `OPENAI_MODEL` | OpenAI credential and bare model ID |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Anthropic credential and bare model ID |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini Developer API credential and bare model ID |

Obtain credentials from the providers' own account consoles. No special assistant
plugin or key-creation workflow is required by this repository. Keep credentials
local; do not paste them into prompts, source, issues, screenshots, or replay files.

Models must be accessible to your account and support both PNG input and the
adapter's structured-output contract. IDs must start with an ASCII letter or digit,
then contain only ASCII letters, digits, `.`, `_`, or `-`, up to 128 characters.
Do not use URLs, `models/` prefixes, or provider routing strings. There are no
default model IDs, custom endpoints, OpenRouter, Ollama, or Vertex AI adapters.
See [API references](API_SOURCES.md) for checked and unresolved contract assumptions.

The environment reader accepts UTF-8 (including a BOM), literal `NAME=value`,
optional matching quotes, whole-line comments, and an optional `export ` prefix.
It does not execute shell text, expand variables, support multiline values, or
interpret inline comments. Existing process variables win over file assignments;
within the file, the last assignment to a name wins. Use a file no larger than
65,536 bytes.

For `--check` and `--live`, an explicit `--env-file` is loaded; otherwise `.env` in
the working directory is loaded if present. Process variables can supply all values
without a file. Blank or missing required values fail local validation.

```bash
python -m parallax_relay.play --check --env-file .env
```

This checks local settings only. It prints role/provider/model assignments, not
keys, and makes no requests. It cannot establish authentication, billing access,
model capabilities, or service availability.

## TOML settings and CLI overrides

The default configuration is
[`configs/three_models.toml`](../configs/three_models.toml), resolved relative to the
source checkout. Use `--config path/to/file.toml` for another configuration. Save it
as UTF-8. Invalid encoding is reported safely as a configuration error (exit 2),
without echoing the file contents.

The default role assignments are SPECTRA → OpenAI, PYRA → Anthropic, FLUX → Gemini.
Each `[players.ROLE]` names a provider and the environment variables containing its
model ID and key. Assignments can be rotated; exactly these three roles are required.

| Match setting | Default | Accepted bounds |
|---|---:|---|
| `communication_rounds` | 2 | 1 or 2 |
| `max_turns` | 12 | 1–12 |
| `max_calls` | 216 | 1–10,000 |
| `max_attempts` | 2 | 1–3, including the initial attempt |
| `timeout_seconds` | 60 | Greater than 0, at most 600 |
| `max_output_tokens` | 2,048 | 256–16,384 per request |
| `history_turns` | 4 | 0–12 |
| `retry_delay_seconds` | 0.5 | 0–30, initial exponential delay |
| `max_consecutive_failures` | 3 | 1–20 failed phases per role |
| `image_token_reserve` | 8,192 | 1–1,000,000 |
| `max_estimated_cost_usd` | Unset | Positive, with pricing for every role |

The TOML is validated first. `--max-turns`, `--max-calls`, and `--fast` then override
its corresponding match settings; `--fast` sets one communication round. Other
settings require TOML edits. Unknown configuration fields are rejected.
`--quiet` suppresses the banner and phase progress, but still prints the result and
replay path. Select exactly one of `--mock`, `--check`, or `--live`.

Every retry counts as an attempt. Before a phase starts, the budget must accommodate
all three roles' maximum attempts. For example, with two attempts per role, five
remaining calls cannot start a phase even if all roles might succeed on their first
try. Unknown/partial usage retains the estimate and increments `unknown_usage_calls`.
A successful phase resets that role's failure streak; the streak counts phases,
not turns. Refusals do not retry; transient failures retry, then use silence or WAIT.

To enable a local dollar guard, set `match.max_estimated_cost_usd` and add positive
`input_per_million` and `output_per_million` prices under each
`[players.ROLE.pricing]`. Consult current provider pricing for the exact selected
models; this guide does not prescribe prices. The estimate uses conservative text
and image reservations, but does not model every cache tier or billing rule. It is
**not a provider-enforced spending ceiling**. Use provider-side controls as well.

## Live smoke test

Only run the following when you intend to make potentially billable requests:

```bash
python -m parallax_relay.play --live --env-file .env --max-turns 1 --max-calls 18
```

Normally this makes nine requests: three per phase. Eighteen allows one retry per
request under the default settings. It resolves at most one game turn. A healthy
bounded run ends with `turn_limit`, no terminal score, and `completed=false`.
Inspect `calls.jsonl` and `phases.jsonl` before attempting a full match:

```bash
python -m parallax_relay.play --live --env-file .env
```

No credentialed smoke test or full live match has been run as part of the repository
review. Offline tests cannot establish that a given model interprets the PNGs or
cooperates successfully.

## Outputs and replay

With no `--out`, the main launcher creates `runs/<UTC timestamp>_<suffix>/`.
`--out` accepts an explicit **new** directory; existing directories are rejected,
even if empty. Keep the files together when copying a replay.

| File | Contents |
|---|---|
| `manifest.json` | Schema version, mode, model assignments, effective settings, room, privacy notice; mock runs also include requested settings |
| `calls.jsonl` | Attempt statuses, latency, usage, sanitized HTTP metadata |
| `phases.jsonl` | Completed message batches and sealed commitments after each barrier |
| `replay.jsonl` | Fully resolved turns, observations, private notes, and world snapshots |
| `result.json` | Stop reason, outcome, terminal scores, and budget totals |
| `final_state.json` | Privileged final world snapshot |
| `turn_*.png`, `final_spectator.png` | Observation and spectator images |
| `index.html` | Offline viewer assembled at finalization |

All these files are spectator artifacts. They may include every role's private
information and model-generated content. Review them before sharing; do not feed
whole replay records to a participant. They do not provide complete experiment
provenance; see [R08](REVIEW.md#r08-run-manifests-lack-reproducibility-metadata).

Open `index.html` locally. The round slider and arrow buttons select resolved turns.
Images show the state **before** that round; events describe its result. Calls and
phases from an unfinished round may only be visible in JSONL, not in the viewer.
For a zero-turn run, the viewer uses the final spectator image and hides round
controls. There is no live dashboard or built-in resume command. Finalization automatically
attempts recovery for the active run only; it does not resume gameplay.

## Exit codes and troubleshooting

| Code | Meaning |
|---|---|
| 0 | Configuration check, victory, or intentionally bounded nonterminal run |
| 1 | Engine defeat |
| 2 | CLI/configuration/local output or callback error; also demo output-path/local I/O errors |
| 3 | Provider, internal-agent, or reliability abort |
| 4 | Call or estimated-cost budget stop |
| 130 | Keyboard interruption |

Use `result.json` when present to distinguish outcomes. A bounded run is not a loss.
`--max-turns` limits the experiment; the engine's room deadline and player HUD still
use 12 turns. No experiment-horizon override is currently sent to the players.

- **Output already exists:** choose another directory or omit `--out`.
- **Missing environment values:** populate the named variables; check inherited
  process variables if an edited `.env` value is being ignored.
- **`provider_error`:** inspect sanitized HTTP status and role. Check permissions,
  quota, model support, and current API contracts. Raw provider errors are not saved.
- **Repeated `incomplete` or validation failures:** check model capabilities and
  output-token requirements; raise limits deliberately rather than removing bounds.
- **`call_budget`/`spend_budget`:** account for whole-phase retry reservations. The
  CLI scripted mock disables only the dollar guard; its call budget still applies.
- **`local_error` / partial output:** the driver stopped at its last resolved turn
  and attempted up to two finalization passes, independently saving each artifact.
  Started calls, completed phases, and resolved turns rebuild the JSONL logs. The
  CLI prints a partial summary and only announces a replay if the current viewer
  was produced. Earlier setup errors, persistent write failures, process termination,
  or stalled storage can still prevent usable output. Preserve the directory for
  diagnosis; no standalone recovery/resume command is shipped.
- **Failure after victory:** `local_error` can coexist with `win=true` and terminal
  scores; the game finished, but recording failed. Exit 2 reports the output failure.
- **Provider cleanup incomplete:** shutdown failed or exceeded its five-second
  cooperative timeout. An earlier match failure remains primary; cleanup diagnostics
  never include raw exceptions.

For current defects and their proposed acceptance tests, see [Review](REVIEW.md).
