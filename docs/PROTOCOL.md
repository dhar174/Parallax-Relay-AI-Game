# Player protocol and trust boundary

## Observations

`observe(world, role)` produces an immutable `Observation` with role, zero-based
turn, serialized HUD and own PNG bytes. Parsing `.hud` returns a fresh object.
Only this allowlisted projection enters model requests. Full `WorldState.snapshot()`
is privileged. A role does not receive another role's hidden facts or notes.

Own objective and public abilities are text. Shared geometry, robot positions,
resources and public events are allowed in the HUD. Exact motor heat is not exposed
through public text events; it appears only in the thermal sensor. Static action
instructions do not reveal item coordinates. Private data explicitly communicated
by a player becomes public by design.

Every current phase uses the same starting observation. Later phases add completed
public message batches, not newly computed world states. Own recent histories
contain prior own HUDs/actions and public chat/results, never other private HUDs.
A player can preserve visual findings in its own factual notes between turns.
Images from previous turns are not resent. `history_turns=0` disables history but
not the explicit latest private note.

## Reply shapes

Broadcast and negotiation:

```json
{"turn":0,"message":"I can see the motor is hot. I will vent before you reroute."}
```

Commitment:

```json
{"turn":0,"action":{"kind":"VENT","direction":0,"steps":0},"notes":"Venting this round. Confirm the bridge extends before moving."}
```

All keys are required. All objects reject extra keys, duplicate keys, wrong types
and stale turns. No Markdown fences or prose wrappers are accepted. Public message
maximum is 400 characters; notes maximum is 1000. Notes are brief facts, uncertainty
and intent, not a request for a chain of thought. An empty string is legal.

Action kinds: `MOVE`, `WAIT`, `VENT`, `REROUTE`, `COLLECT`, `UNLOCK`.
MOVE uses direction -1 or +1 and steps 1 or 2. Other actions require both fields
to be zero. The parser accepts integer values, but the engine treats noncanonical
non-MOVE parameters as an illegal action: no action effect, one turn consumed, and
an explicit `{role}: invalid {kind} parameters; treated as WAIT` event. No schema
repair/provider retry is granted; the submitted action remains in the record. The host
assigns role; a response cannot select another player. The schema permits integer
values so that gameplay-invalid moves are handled by the engine, not retried for
better strategy. Shape/type errors are transport-contract failures and may retry.

## Phase barriers

All role calls start concurrently with `asyncio.gather`. Publication waits for every
role to finish or exhaust its bounded retry path. Broadcast is visible to negotiation;
those messages are visible to commitment. Neither later arriving models nor retries
receive other same-phase outputs. Responses have no effect until the entire
commitment phase finishes. Then the host calls `resolve_turn` exactly once.

Default: broadcast -> negotiate -> commit -> resolve.
Fast: broadcast -> commit -> resolve.

Controls resolve before movement, including VENT before REROUTE. Movement precedes
collection/unlock, as in the starter. This is not a real-time physics system.

## Failure and budget behavior

Each request gets at most two attempts by default, one timeout per attempt, bounded
exponential delay and bounded provider Retry-After. Refusal is not retried. A JSON
repair request gives a fixed safe instruction without echoing raw malformed text.
Schema-valid illegal moves go to the engine without retry. Transient network/HTTP
failures retry, then silence/WAIT. Authentication, unsupported model/schema requests,
and exhausted quota are fatal. No automatic SDK/transport retry is hidden.

The failure streak counts failed **phases**, not rounds. Three consecutive failed
phases for one role abort by default. Any successful phase resets that role's streak.
Fatal setup/provider errors abort the unfinished round without resolving its actions.
Already completed public messages and attempt metadata remain in the partial logs.
Recording/progress failures stop the match and trigger bounded best-effort
finalization. The checkpoint is the last successfully resolved engine turn, including
its original submitted actions, even if its incremental write failed. Completed
phases and all started-call evidence are retained in memory and used to rebuild
JSONL at finalization. A failed write never causes another model call or transition.
Persistently unwritable storage or process termination can still leave partial output.

A phase reserves the full team's maximum attempts before starting. Unknown token
usage is recorded as unknown, not zero. A configured dollar guard uses user-supplied
prices plus conservative text/image/output reservations. It is not a billing guarantee
and should not be represented as a hard external spending cap.

## Outcomes and exit codes

`victory` and `defeat` are engine-terminal outcomes. `turn_limit` means a shorter
configured experiment stopped before the engine ended. Other stops include
`call_budget`, `spend_budget`, `provider_error`, `internal_error`, `unreliable_agent`
and `cancelled`. Local output/callback failures add `local_error`; engine completion
and scores still describe the actual world, so output failure after a win can have
`completed=true`. Nonterminal stops have `completed=false` and `scores=null`.

CLI codes:
0 for successful execution/config check or intentionally bounded run;
1 for engine defeat; 2 for configuration/local output/callback errors; 3 for provider/internal/
reliability abort; 4 for budget stop; 130 for keyboard interruption.

## Security scope

Public messages and images are untrusted content. They cannot grant tools or alter
host rules. APIs receive no shell/browser tools, no environment files, no API keys
in prompt bodies, and no full engine state. Credentials travel only in required
provider authentication headers. Logs retain sanitized status codes, not exception
text or raw provider bodies. Gemini's key is not placed in a URL query string.

This is application-layer data isolation, not an OS sandbox for arbitrary Python
agents. Third-party Python code running in the same process is trusted code and
could bypass in-process boundaries. Models invoked through the REST adapters only
receive the serialized request. Prompts cannot guarantee that models never lie,
misinterpret images, or follow misleading game text; the deterministic engine limits
what their outputs can do.

Replay JSON/HTML intentionally contains all player-private information for the human
spectator. Treat it as privileged. It is not suitable as a participant context source.

The legacy `parallax_relay.demo` command has an older replay format. Both CLIs
reject existing output paths and choose unique directories under `runs/` when no
`--out` is supplied. The demo returns exit 2 for output-path/local I/O errors. See
[Running](RUNNING.md) for operational details and [Architecture](ARCHITECTURE.md)
for ownership and extension boundaries.

## Programmatic failure contract

`run_match` raises `MatchExecutionError` after recovery for host execution failures.
It exposes `result`, `operation`, `original_error`, `secondary_errors` (operation/error
pairs), and `original_stop_reason`. Original error objects are for trusted diagnosis
only; printing them can disclose sensitive exception text. The wrapper's message,
repr, and normal formatted traceback suppress that text; persisted data uses only
safe stop/stage identifiers. Provider/budget stops still return normal results.
Cancellation still raises `CancelledError`, with partial `result` and
`secondary_errors` attached; cleanup errors cannot replace it.

`MatchResult.phases` defaults to an empty list for existing constructors. Summary
fields and schema version remain unchanged. `Recorder.finish` returns normally on
success and raises sanitized `RecordingFinalizationError` with ordered `failures`
pairs on failure. The driver makes at most two finalization passes and preserves
the original failure, even if recovery succeeds.
Fresh caller cancellation during client shutdown still propagates, retaining an
earlier host failure diagnostically rather than converting cancellation to exit 2.
