# Parallax Relay

A cooperative puzzle game for three independent multimodal AI players. Each robot
sees a different sensor image, exchanges public messages, and commits one action
without seeing its teammates' current actions. A deterministic Python engine
resolves the turn.

**Status:** Milestone 2 is an offline-tested coordination prototype. It includes
OpenAI, Anthropic, and Gemini REST adapters, but no credentialed provider match has
been verified for this repository. The bundled victories use scripted players that
already know the solution; they are not evidence of model reasoning or cooperation.

## Try it without API keys

Use Python **3.12** for the usual development environment; the minimum is 3.11.
See [Contributing](CONTRIBUTING.md#environment) for dependency reproducibility and
tested-environment coverage. Run from the repository root:

```bash
git clone https://github.com/dhar174/Parallax-Relay-AI-Game.git
cd Parallax-Relay-AI-Game
python -m venv .venv
```

Activate the environment:

```bash
# Linux, macOS, or WSL
source .venv/bin/activate
```

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

Install dependencies, run the offline tests, and play the scripted fixture:

```bash
python -m pip install pip==26.3
python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.lock -r requirements.txt
python -m unittest discover -s tests -v
python -m parallax_relay.play --mock
```

Open the `index.html` path printed by the launcher. Each invocation creates a new
folder under `runs/`. A normal mock match wins in seven turns with 63 scripted
calls, five energy remaining, and a score of 100 for each role. No provider calls
are made. Add `--fast` for one communication pass and 42 scripted calls.
For an automated check of both modes with temporary outputs, run
`python scripts/check_mock_runs.py`. CI checks the
[focused Python/OS matrix](CONTRIBUTING.md#supported-environments-and-ci), with
locked dependencies and a separate compatibility-range job.

For a ready-made replay, download or clone the repository and open
[`example_run/index.html`](example_run/index.html) locally, keeping its PNGs beside
it. GitHub's file view displays source rather than running the viewer.

## How the game works

The current room, **The Split Span**, is a single horizontal lane. SPECTRA sees
optical details and a shard; PYRA sees motor heat; FLUX sees circuits and an energy
cell. Their abilities must be coordinated to extend a bridge and unlock the exit.
All three must escape within 12 turns, while each pursues a private objective.

Each turn follows this sequence:

1. Render each role's sensor image and private HUD.
2. Collect concurrent broadcasts, then publish the complete batch.
3. Collect and publish negotiation replies, unless `--fast` is enabled.
4. Collect sealed action commitments from all three roles.
5. Resolve controls, movement, interactions, and victory in the engine.

The replay is an offline spectator view containing all roles' private information.
It must not be used as a participant's context.

## Run real models

Read the [running guide](docs/RUNNING.md) before using live mode. Configure explicit
model IDs and credentials locally, then validate local settings:

```bash
python -m parallax_relay.play --check --env-file .env
```

`--check` makes no provider requests and cannot verify remote access or model
capabilities. `--live` explicitly enables potentially billable requests. Model IDs
and prices are not supplied by default. Current validation limits and open issues
are documented in the [review](docs/REVIEW.md).

## Current limits and direction

This release has one fixed room, three active roles, compatible objectives, and a
known scripted solution. It has no platformer physics, procedural rooms, playable
ECHO role, live dashboard, experiment runner, or validated benchmark results.

The [roadmap](ROADMAP.md) prioritizes reliable execution and reproducible evaluation
before expanding the cooperative puzzles. The [verification record](docs/VERIFICATION.md)
separates original milestone evidence from subsequent checks.

## Documentation

| Document | Use it for |
|---|---|
| [Running guide](docs/RUNNING.md) | Configuration, limits, troubleshooting, and replay files |
| [Architecture](docs/ARCHITECTURE.md) | Modules, data flow, and extension boundaries |
| [Protocol](docs/PROTOCOL.md) | Player inputs, reply contracts, phases, and outcomes |
| [Provider references](docs/API_SOURCES.md) | API assumptions and external sources |
| [Review](docs/REVIEW.md) | Prioritized defects, evidence, and improvement opportunities |
| [Roadmap](ROADMAP.md) | Future milestones and completion gates |
| [Contributing](CONTRIBUTING.md) | Development and verification workflow |
| [Agent instructions](AGENTS.md) | Repository-specific instructions for coding agents |
| [Changelog](CHANGELOG.md) | Delivered changes |

Source is in `parallax_relay/`, tests in `tests/`, and default configuration in
`configs/three_models.toml`. `example_run/` and `demo_output/` are committed scripted
fixtures. New runs and local environments are ignored by Git.

Licensed under the [MIT License](LICENSE).
