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
Follow its [model-selection requirements](API_SOURCES.md#selecting-a-compatible-model)
for endpoint/schema/PNG compatibility, context/image limits, reasoning headroom and
output bounds. A separate named smoke profile is described below; ordinary model defaults remain unset. The 2,048-token
default does not guarantee a complete reply for every model; limits never increase
automatically, and `--check` cannot establish remote capability or account access.
Malformed/compressed provider output uses bounded retries and conservative unknown
usage accounting. Unsupported or nonfinite `Retry-After` values use the configured
backoff. Anthropic null cache counters intentionally retain estimates; see the
[usage caveat](API_SOURCES.md#usage-and-unknowns) before interpreting costs.

The environment reader accepts UTF-8 (including a BOM), literal `NAME=value`,
optional matching quotes, whole-line comments, and an optional `export ` prefix.
It does not execute shell text, expand variables, support multiline values, or
interpret inline comments. Existing process variables win over file assignments;
within the file, the last assignment to a name wins. Use a file no larger than
65,536 bytes.

HTTP proxy/certificate settings (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`,
`NO_PROXY`, `SSL_CERT_FILE`, `SSL_CERT_DIR`) must come from the process environment.
Putting them in `.env` rejects the entire file with exit 2 before applying any
assignments or creating output, even when a process value already exists. Owned
HTTP clients still honor process-level settings; caller-supplied clients retain
their caller's policy. Custom credential/model variable names remain supported.
Treat `.env` as trusted local configuration; this restriction is not a general
sandbox for arbitrary environment variables.

For `--check` and `--live`, an explicit `--env-file` is loaded; otherwise `.env` in
the working directory is loaded if present. Process variables can supply all values
without a file. Blank or missing required values fail local validation.

```bash
python -m parallax_relay.play --check --env-file .env
```

This checks local settings only. It prints role/provider/model assignments, not
keys, and makes no requests. It cannot establish authentication, billing access,
model capabilities, or service availability.

## Named one-turn live smoke

[`configs/live_smoke.json`](../configs/live_smoke.json) is a public, frozen run
sheet, not standing permission to spend. It selects SPECTRA and PYRA as separate
`gpt-6-luna` OpenAI agents and FLUX as `gemini-3.5-flash-lite`. PYRA keeps its
character, abilities, thermal view and private objective. Its execution mapping
selects OpenAI, `PYRA_MODEL` and `OPENAI_API_KEY` instead of the default Anthropic
provider and variables.
Both OpenAI agents use `OPENAI_API_KEY`, with separate `OPENAI_MODEL` and
`PYRA_MODEL` selections pinned by the helper. FLUX uses `GEMINI_MODEL` and `GEMINI_API_KEY`.
No Anthropic key is required. The maintainer chose to retire mandatory Anthropic
validation #15 through the [scope decision](VERIFICATION.md#provider-acceptance-and-scope-decision--november-15-2026);
its adapter remains implemented/offline-tested/live-unverified.

The profile retains normal broadcast, negotiation and commitment, limits execution
to one turn, permits at most 18 total attempts (two per request), bounds output at
4,096 tokens per request and timeouts at 60 seconds, and uses a $1 **local estimate**
guard. Nine calls are expected without retries. Prices are standard short-prompt
rates checked November 15, 2026: OpenAI $0.10/$0.50 and Gemini $0.30/$2.50 per
million input/output tokens. Recheck the linked sources, account access, and rates
before any separately authorized invocation. Free-tier eligibility is unverified;
prices do not establish actual invoices, cache tiers or billing ceilings.

```bash
python scripts/live_smoke.py --check
# Only after explicit authorization for this roster and these bounds:
python scripts/live_smoke.py --live
# No network; use the output directory reported by the live invocation:
python scripts/live_smoke.py --verify runs/<fresh-run>
```

The helper inherits process credentials, optionally filling missing values from
ignored `.env.smoke` or an explicit `--env-file`. Process values win. Credential files may contain only the selected API-key
variables; unrelated assignments are rejected. Python startup overrides are removed
from the child environment, while process proxy/certificate settings are retained. It pins all
model selections in a child environment, passes the real CLI a validated temporary
TOML and an explicit empty env file, and never loads the ordinary `.env` implicitly.
It does not write credentials. `--check` requires the selected local credential
variables (or dummy placeholders for offline validation), exits 2 when they are
missing, makes no provider requests and creates no recorded run; it cannot establish authentication or model support. An optional
`--config relay-workbench.toml` must normalize to the frozen profile exactly.
The workbench's named preset exports this configuration; edits invalidate its
approval and require renewed review. The original default configuration is unchanged.

`--live` invokes the actual CLI once and records its exit code/profile digest in
`smoke_launch.json` when the run directory exists. The subprocess has a 600-second
outer timeout; existing per-attempt and cooperative cleanup bounds still apply.
Errors/timeouts do not cause another invocation. On timeout the helper reports the
selected partial-output directory, an unknown CLI exit code and `timed_out=true`;
if the directory exists, it attempts an atomic launcher receipt. A failed receipt
write is reported and acceptance stays unverified. After **any** started provider
attempt, another live invocation needs new authorization. A timeout or missing
artifact is unverified, never a reason to retry automatically. Outputs stay ignored
and private; child stdout/stderr are not echoed by the helper.

The helper preserves a nonzero CLI exit status. If CLI exit is zero but offline
artifact verification fails, it returns 1; local preparation/launcher errors and timeouts return
2. `--verify` rejects execution-only `--config`, `--env-file` and `--out` flags. `--verify` returns 0 only when the receipt, provenance settings/prices/models,
three successful phases, complete/cross-checked replay and world records, bounded
attempts, usage counters, decoded role/spectator PNGs, the embedded viewer, and consistent
one-turn incomplete state agree. Healthy output is `turn_limit`, `completed=false`,
no victory/defeat and null scores. Failed attempts may precede a valid bounded retry;
fallback outputs cannot establish acceptance. Per-role verdicts are distinct from
overall acceptance, and both OpenAI roles must pass to claim this roster's OpenAI
smoke succeeded. Files and hashes are not signatures or proof of authenticity.

Keep full spectator artifacts local. Publish only a reviewed sanitized summary,
including exact execution source/dependency/model/API evidence and unknown usage.
One round does not establish image understanding, strategy or cooperation. See the
[verification record](VERIFICATION.md) for actual results and limitations.

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

`--experiment-id UUID` and `--trial-id UUID` optionally group recorded runs. They
are metadata, not campaign scheduling, deduplication, random seeds, or resume
controls. Invalid values exit 2 before output is created without echoing them.
`--check` creates no run. See [Run provenance](PROVENANCE.md#cli-and-programmatic-use).

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

A separately authorized one-turn retry completed the selected two-OpenAI/one-Gemini
roster successfully. See the [dated evidence](VERIFICATION.md#provider-acceptance-and-scope-decision--november-15-2026)
for the exact models, source, usage and limits; the earlier failed attempt remains
historical evidence. No full live match is verified. Neither a successful smoke
nor offline tests establish general image understanding or cooperation.

## Provider and model combinations

For each of SPECTRA, PYRA and FLUX, choose `openai`, `anthropic` or `gemini` in its
player settings and supply the named local model/key variables and explicit rates.
Providers and models may repeat across roles; each agent keeps separate role-local
context. Character abilities, observations and objectives do not depend on vendor.
The fixed named-smoke helper still accepts only its frozen profile.

This configuration freedom does not mean every model is compatible. Today's adapters
send the role PNG and HUD and require the existing structured text reply contract;
model selection must satisfy both, including output/reasoning bounds. A successful
run verifies only its recorded combination and conditions. Anthropic models and
other untested combinations remain live-unverified, not proven unsupported.
Additional APIs, local deployments, text-only, audio/video and non-chat models need
future explicit bridges and capability validation under [#37](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/37).
No implicit input removal, model/API fallback or new paid request is authorized.

## Outputs and replay

With no `--out`, the main launcher creates `runs/<UTC timestamp>_<suffix>/`.
`--out` accepts an explicit **new** directory; existing directories are rejected,
even if empty. Keep the files together when copying a replay.

| File | Contents |
|---|---|
| `manifest.json` | Schema 2; mode, assignments, settings, room, privacy notice, plus independently versioned provenance; mock runs retain requested settings |
| `calls.jsonl` | Attempt statuses, latency, usage, sanitized HTTP metadata |
| `phases.jsonl` | Completed message batches and sealed commitments after each barrier |
| `replay.jsonl` | Fully resolved turns, observations, private notes, and world snapshots |
| `result.json` | Stop reason, outcome, terminal scores, and budget totals |
| `final_state.json` | Privileged final world snapshot |
| `turn_*.png`, `final_spectator.png` | Observation and spectator images |
| `index.html` | Offline viewer assembled at finalization |

All these files are spectator artifacts. They may include every role's private
information and model-generated content. Review them before sharing; do not feed
whole replay records to a participant. [Run provenance](PROVENANCE.md) records
effective settings/prices, source/environment availability, prompt/schema/room
identities, UUIDs and execution timing. Unknown provider revisions/default sampling
and dirty or unavailable source still limit reconstruction. Historical fixtures
remain readable without provenance; missing identity is unknown.

For comparative work, follow the prospective [evaluation protocol](EVALUATION.md).
Current UUID flags label single runs; they do not implement its future campaign
ledger, budget scheduler, baseline policies or missing ablation controls.

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
- **Local file/setup failure:** check parent directories and permissions. A regular
  file used as an output parent (including a file named `runs`) is a setup failure,
  not an existing destination. Broken symlinks at the destination are rejected
  without following them. Both launchers report safe exit 2 diagnostics.
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
  manifest is one of eight independently replaced final artifacts; failed storage
  can leave it stale even if another summary or viewer was saved. Execution end
  timing precedes finalization and remains stable across its recovery pass. The
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

## Evaluation conditions and offline controls

`--condition full|reduced|disabled|withheld|no_images` selects a protocol-v1 arm.
Legacy communication rounds 2/1 still select full/reduced; 0 means disabled.
An explicit condition normalizes an omitted round count and rejects a conflicting
explicit count. CLI `--condition` overrides the configuration; `--fast` is the
reduced arm and rejects a conflicting named condition. Ordinary defaults stay full.

```bash
python -m parallax_relay.play --mock --policy wait --condition disabled
python -m parallax_relay.play --mock --policy uniform --condition no_images \
  --trial-id b81b3e0a-61cc-45fd-83c6-f871291c98af
```

`--policy` is mock-only; default scripted is the known solvability oracle. WAIT
and uniform-v1 use empty messages/private notes and the normal engine consequences.
Uniform requires a trial UUID. It samples canonical role action kinds without
hidden-state legality filtering; an illegal game action consumes the normal turn.

Disabled skips communication calls. Withheld runs and records communication but
removes all public messages, including own public scratchpad and metadata, from
current and later player inputs. Own commitment notes remain local. No-images
omits provider image parts and image cost reserves while recording the unchanged
role PNGs for spectators. All arms include the same factual condition-notice template.
These interventions establish host behavior, not evidence of intelligence or a
communication benefit. See [evaluation protocol](EVALUATION.md).
