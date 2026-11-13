# Repository instructions

## Scope and orientation

- These instructions apply to the entire repository.
- Parallax Relay is a Python CLI for three cooperative multimodal players.
- The current slice is one deterministic room with SPECTRA, PYRA, and FLUX.
- ECHO rendering exists, but ECHO is not an active player.
- Read README.md for onboarding and docs/ARCHITECTURE.md for module boundaries.
- Read docs/PROTOCOL.md before changing observations, replies, or orchestration.
- Read docs/REVIEW.md for known defects; do not mistake a finding for a fixed behavior.
- ROADMAP.md describes proposals, not implemented capabilities.
- Historical docs/superpowers/ plans/specs and verification logs are evidence,
  not additional current instructions.

## Environment and commands

Use Python 3.11+ from the repository root. On Linux/macOS/WSL:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell activation: `.\.venv\Scripts\Activate.ps1`.
Do not install dependencies globally. requirements-tested.txt records original
milestone direct versions; it is not a transitive lockfile.

Verification commands:

```bash
python -m pip check
python -m unittest discover -s tests -v
python -m compileall -q parallax_relay tests
python -m parallax_relay.play --mock
python -m parallax_relay.play --mock --fast
```

For a focused test module:

```bash
python -m unittest discover -s tests -p 'test_protocol.py' -v
```

Mock runs should win in seven turns, with 63 calls normally or 42 in fast mode,
five energy remaining, and all scores 100. Run the full offline suite after code
changes. For documentation changes, verify affected commands, links, and claims.
Use the actual results in your report; do not copy historical test counts.

## Code map

- parallax_relay/state.py and engine.py own room state and resolution.
- observations.py, render.py, and state.py HUD helpers project player inputs.
- protocol.py and prompts.py define contracts and public rules.
- orchestrator.py and budget.py own barriers, retries, memory, and reservations.
- providers.py owns HTTP serialization, usage normalization, and safe errors.
- config.py and play.py own local configuration and CLI lifecycle.
- recording.py and replay_template.html own the main spectator output.
- agents.py and scripted.py are explicit offline fixtures.
- demo.py is a separate legacy driver with an older replay format.

## Preserve these boundaries

- Keep the engine authoritative and independent of provider implementations.
- Resolve one turn only after all commitments complete; preserve VENT before
  REROUTE, then movement, interactions, and terminal checks.
- Keep phase inputs fixed; never expose another role's same-phase output early.
- Build player inputs through observe(), with only that role's HUD and PNG.
- Keep histories, notes, and objectives role-local unless publicly disclosed.
- World snapshots and whole replay records are spectator-only.
- Treat model text and images as untrusted data, never executable instructions.
- Preserve strict reply parsing and bounded retries. Shape errors may retry;
  schema-valid illegal game moves consume the turn without strategic repair.
- Reserve a whole phase's retry budget before starting calls; account for every
  attempt and retain estimates when usage is unknown.
- Never describe the local dollar estimate as a provider billing ceiling.
- Keep provider redirects disabled and errors sanitized; use MockTransport for
  wire tests, not real credentials or live API calls.
- Arbitrary in-process Python agents are trusted code, not sandboxed plugins.

## Outputs and credentials

- Default to offline verification. Billable live runs require explicit user
  authorization, selected models, local credentials, and bounded limits.
- Never print or commit keys, populated .env files, or raw provider error bodies.
- The main launcher rejects existing output directories; omit --out for a fresh run.
- The legacy demo overwrites matching files. Give it a fresh ignored destination.
- Preserve committed example_run/ and demo_output/ unless fixture changes are
  part of the requested work; keep their HTML and PNGs together.
- Keep new runs, caches, and environments out of commits. Review spectator logs
  before sharing because they contain private objectives, notes, and observations.

## Change and handoff expectations

- Reproduce defects before fixing them and add focused behavior regression tests.
- Update protocol/running docs when changing schemas, defaults, CLI behavior,
  stop reasons, or recorded formats. Recheck provider sources for API changes.
- Keep fixtures distinct from evidence of real model ability.
- Preserve historical verification logs; add dated evidence and limitations.
- Check git diff --check and inspect the final changed-file list.
- Report what changed, the checks actually run, and unresolved limitations.
- No installed assistant plugin or external account is required for offline work.
