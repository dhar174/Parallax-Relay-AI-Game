# Parallax Relay: Milestone 2

**Three independent multimodal players, public negotiation, sealed actions.**

This builds on the supplied starter rather than replacing its game engine. It adds
an asynchronous orchestrator and direct REST adapters for OpenAI, Anthropic Claude,
and Google Gemini, plus a command-line launcher and recorded-match viewer.

**Validation status:** 72 offline tests pass, including intercepted HTTP integration
through all three adapters. Scripted players complete the room in seven turns.
**No credentialed provider call or real-model match has been run for this release.**
The included `example_run/` is explicitly a scripted fixture, not evidence of AI ability.

## 1. Run it without keys

Use Python **3.11 or later**. The verification environment was Python 3.13.5 on Linux.
Clone the repository and run from its root directory:

```bash
git clone https://github.com/dhar174/Parallax-Relay-AI-Game.git
cd Parallax-Relay-AI-Game
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or on WSL, Linux, or macOS:

```bash
source .venv/bin/activate
```

Then:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m parallax_relay.play --mock --out runs/mock-01
```

Open `runs/mock-01/index.html`. The ready-made `example_run/index.html` also works
without running Python. Keep its accompanying PNGs beside it. A run directory must
be new; existing directories are never overwritten. Omit `--out` for a unique
UTC-timestamped directory.

The mock mode runs the same observation, messaging, validation, orchestration and
recording path as live mode, but uses explicitly scripted agents and makes no
network calls. It does not read `.env` or require credentials.

## 2. Configure real players locally

The default mapping is SPECTRA -> OpenAI, PYRA -> Anthropic, FLUX -> Gemini.
Roles are not coupled to providers: edit `configs/three_models.toml` to rotate them.

Copy `.env.example` to `.env` with your editor. It contains these six variable names:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
OPENAI_MODEL
ANTHROPIC_MODEL
GEMINI_MODEL
```

Enter your credentials and chosen model IDs **only on your own machine**. For the
OpenAI credential, use the secure OpenAI Platform setup flow supplied alongside the
project when needed. Existing local credentials can be reused. Do not paste keys
into chat, source files, screenshots, or replay files.

Select a model available to your account that supports **both PNG image inputs
and the provider's JSON-schema structured output mode**. No default model IDs or
prices are guessed. IDs are bare names, not `models/...`, URLs, or `provider/model`
routing strings. OpenRouter, Ollama, other providers, hosted enterprise gateways,
and custom base URLs are not implemented in this milestone.

The small `.env` reader accepts literal `NAME=value`, optional surrounding quotes,
and whole-line comments. It does not execute shell text, interpolate variables, or
support multiline values or inline comments. Existing process environment values
win over the file. The file must be UTF-8. `.env` is git-ignored.

Check the local configuration without contacting a provider:

```bash
python -m parallax_relay.play --check --env-file .env
```

A successful check confirms local settings only. It does not verify keys, remote
access, model capabilities, or billing availability.

## 3. Start with a one-round live smoke test

```bash
python -m parallax_relay.play --live --env-file .env --max-turns 1 --max-calls 18 --out runs/live-smoke-01
```

This explicitly enables billable API calls. Normally the round uses nine requests:
three broadcasts, three negotiation messages, then three commitments. Eighteen
allows the default one retry per request. At most one game round is resolved.
A healthy bounded smoke run ends with `stop_reason: "turn_limit"`, `completed: false`,
and no final score. That is **not a defeat** and is not meant to finish the room.

Inspect `calls.jsonl` for request statuses and `phases.jsonl` for the messages and
commitments. Then run a full game:

```bash
python -m parallax_relay.play --live --env-file .env --out runs/live-01
```

For one communication pass instead of two:

```bash
python -m parallax_relay.play --live --env-file .env --fast --out runs/live-fast-01
```

If responses repeatedly end `incomplete`, review the selected model's output
requirements and increase `max_output_tokens` within the configuration limit.
Unsupported models or schemas, authentication errors, and quota exhaustion stop
the run rather than silently switching models or output modes.

## What a turn does

1. Render each player's own sensor PNG and allowlisted HUD. Give it its own private
   objective, recent local history and optional saved factual notes.
2. Request all three broadcasts concurrently, then publish them together.
3. Optionally request all three negotiation replies concurrently, then publish them.
4. Request all three action commitments concurrently. No player sees another's
   committed action until every commitment has completed.
5. Validate outputs, apply exactly one deterministic engine transition, save the
   spectator record, and advance the turn.

A faster provider gets no same-phase information advantage. Each request is
self-contained; server-side conversations are not used. Notes are short factual
memory, not hidden reasoning transcripts. Messages from teammates remain untrusted
game data. There are no shell, browsing, filesystem, or external action tools.

## Boundaries and safeguards

| Setting | Default |
|---|---:|
| Active robots | 3 |
| Game limit | 12 rounds |
| Communication passes per round | 2 |
| Total request attempts | 216 maximum |
| Attempts per request | 2, including initial attempt |
| Timeout per attempt | 60 seconds |
| Output-token limit per request | 2,048 |
| Public message length | 400 characters |
| Private notes | 1,000 characters |
| Recent role-local history | 4 turns |
| Consecutive failed phases for one player | Stop after 3 |

Every retry counts against the request limit. A whole phase reserves enough budget
for all players and their retry allowances before anybody starts. This means a
phase can stop with some unused request capacity rather than unfairly starting only
part of the team.

Malformed output and retryable failures get bounded retries, then a silent message
or `WAIT`. A valid JSON command that violates game rules consumes the turn; it is
not repaired into a better move. Fatal provider errors abort before resolving the
incomplete round. Cancellation preserves completed and partial logs when possible.

**A dollar cap is optional and disabled by default.** Set
`match.max_estimated_cost_usd` and explicit per-model input/output pricing for all
three players to enable a local estimate guard. The TOML shows the required shape.
Unknown usage retains its reserved estimate rather than counting as free.
Estimates are **not a provider-enforced billing ceiling**: token estimation, image
accounting, cached tokens, prices and already in-flight requests can differ from
actual billing. Configure provider-side controls separately as appropriate.

## Replay and logs

| File | Contents |
|---|---|
| `index.html` | Offline viewer, sensor panels, chat, actions, outcomes, diagnostics |
| `manifest.json` | Mode, model assignments, settings, privacy notice |
| `calls.jsonl` | Attempt status, latency, normalized usage; no raw errors or keys |
| `phases.jsonl` | Published chat and actions after their phase barriers |
| `replay.jsonl` | Fully resolved turns, observations, private notes and state snapshots |
| `result.json` | Stop reason, score when terminal, request/token accounting |
| `final_state.json` | Privileged final engine state |
| `turn_*.png`, `final_spectator.png` | Role-specific observations and spectator images |

**These are privileged spectator files.** They include every player's objectives,
notes and observations. Never feed them wholesale to a participant. Raw malformed
model text and raw HTTP error bodies are intentionally not persisted. Model text
is escaped and rendered with `textContent` in the viewer.

## The current room and its limits

The Split Span remains one horizontal lane with three roles. PYRA cools the motor,
FLUX powers the bridge and exit and can recover a cell, and SPECTRA can recover a
shard. All robots must escape together. Each has a private personal objective.
The known script satisfies all three objectives in seven turns with five energy left.

This is a **coordination infrastructure slice**, not yet a difficult strategy game or
validated benchmark. Goals are compatible in this room; more mutually competing
routes and scarce-resource tradeoffs still need level design. There is no automatic
reheating, gravity, jumping, 2/4-player scaling, playable ECHO, procedural generation,
private side channels, persistent relationships, or live web dashboard. The browser
page is a post-match replay, not a live control panel. The original demo remains:

```bash
python -m parallax_relay.demo --out demo_output
```

The engine is deterministic given actions. Real model outputs and concurrent call
completion times need not be deterministic.

## Project map

```text
parallax_relay/
  state.py, engine.py, render.py   Original simulation and sensor rendering
  observations.py                 Only authorized player observation builder
  protocol.py                     Immutable inputs and strict JSON reply contracts
  prompts.py                      Public rules and untrusted-input boundaries
  config.py                       Model/env mappings and runtime limits
  providers.py                    OpenAI, Anthropic, Gemini REST adapters
  budget.py                       Request reservations and optional cost estimates
  orchestrator.py                  Concurrent phase barriers and local memory
  recording.py                    Incremental logs and safe replay generation
  replay_template.html            Offline viewer
  play.py                         Mock/live/check CLI
  agents.py, scripted.py          Explicit offline fixture
  demo.py                         Original standalone demo
configs/three_models.toml          Three-player configuration
.env.example                      Local environment template, no keys
example_run/                      Ready-to-open scripted match
demo_output/                      Original standalone demo recording
tests/                            Offline unit and integration tests
docs/                             Protocol, API references and milestone records
requirements.txt                  Supported dependency ranges
requirements-tested.txt           Versions used for original milestone verification
LICENSE                           MIT license
```

See `docs/PROTOCOL.md`, `docs/API_SOURCES.md` and `docs/VERIFICATION.md` for exact
contracts, official API references and validation limitations. This release was
self-reviewed, not reviewed by an independent agent.
