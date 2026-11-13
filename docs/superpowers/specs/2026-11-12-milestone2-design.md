# Milestone 2: independent multimodal players

> Historical archive-build record (November 12, 2026). Delivery constraints and
> instructions below describe that completed milestone, not current repository
> policy. See [AGENTS.md](../../../AGENTS.md) and [ROADMAP.md](../../../ROADMAP.md).

This implements the continuation Charles requested after approving the Parallax Relay
starter and its three-model orchestrator. The supplied ZIP is the baseline; no repository,
account, external deployment, or user Library is changed.

## Goal and scope
Replace the hardcoded turn driver with independently callable OpenAI, Anthropic and
Google Gemini players. Preserve the three-role Split Span engine and its seven-turn
script as a control. Do not claim a full platformer, 2/4-player support, or a live model
victory without running one.

## Architecture and decisions
Keep simulation authoritative and provider-independent. Each round is observation,
concurrent broadcast, optional concurrent negotiation, sealed concurrent commitment,
then one engine transition. Phase barriers prevent a faster provider from reading
another player's same-phase response. Messages become visible only after a full phase.
Default: two communication rounds. Fast mode: one.

Use documented REST endpoints through httpx behind one small Agent protocol. Alternatives considered:
three official SDKs (less manual parsing but more dependency surfaces) and a general
multi-agent framework (more state machinery than this room needs). REST adapters allow
wire-level offline tests without optional SDK dependencies.
This is an implementation choice, not an additional user requirement.

Only allowlisted HUD fields, the player's own PNG, own objective, public chat/results,
and bounded role-local history/notes may enter a provider request. Full snapshots and
other players' private notes are spectator-only. Hide exact heat from text events;
remove static item coordinates from action descriptions. Private PNG tests ensure
heat/shard/cell changes affect only their authorized sensors.

Models return small JSON objects. The host controls identity, phase and turn. Schema
errors get one bounded repair attempt; legal JSON describing an illegal game move
reaches the engine and consumes the turn. Timeouts/transient provider faults retry
once then silence/WAIT. Authentication, unavailable models and unsupported API
parameters stop the run instead of repeatedly spending money on an impossible setup.

Calls and output tokens have explicit limits; no hidden transport retries are enabled so every
attempt is counted. An optional priced spending guard reserves estimated input and
maximum output costs before a phase. Unknown billing retains the reservation. This
is a local estimate, never a guarantee about external provider billing. No keys or
raw provider exceptions are logged. No paid calls are made during this build.

Keep an offline CLI and replay. Log sealed actions after the phase, real public
messages, usage and failures, private sensor PNGs, final state and stop reason. Replay
is privileged and not safe to feed back wholesale to a player. It remains a static
viewer, not the future live React interface. Append JSONL as work completes, do not
overwrite an existing run folder, and preserve partial runs on provider failures.

## Validation
Original engine tests remain green. New tests cover phase barriers, privacy under
changed hidden state, role-local memory, strict JSON and stale turns, illegal game
actions, retries/timeouts/fatal errors, budgets, CLI preflight and log redaction. Exercise
actual HTTP request serialization with intercepted HTTP and synthetic responses. A
scripted test agent must win through exactly the same orchestrator as a live agent.
Model-specific vision quality and real account access remain a separate live smoke test.
