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

Protocol-v1 evaluation also supports disabled (commit only), withheld (all phases,
but no public message text/metadata in any player request or later history), and
no_images (full phases, own HUD without provider image attachments). All arms use
the same versioned factual condition notice. Actual role PNGs remain spectator
artifacts even without provider attachments. Request format is now version 3;
reply schemas and engine legality are unchanged. See [evaluation](EVALUATION.md).

Controls resolve before movement, including VENT before REROUTE. Movement precedes
collection/unlock, as in the starter. This is not a real-time physics system.

## Failure and budget behavior

Each request gets at most two attempts by default, one timeout per attempt, bounded
exponential delay and bounded provider Retry-After. Refusal is not retried. A JSON
repair request gives a fixed safe instruction without echoing raw malformed text.
Schema-valid illegal moves go to the engine without retry. Transient network/HTTP
failures retry, then silence/WAIT. Authentication, unsupported model/schema requests,
and recognized exhausted-quota errors are fatal. Other 429 errors retain bounded
retries; the adapter cannot establish that every provider quota error is transient.
No automatic SDK/transport retry is hidden.

OpenAI failed/error envelopes raise sanitized `response_failed`; only documented
`server_error`/`rate_limit_exceeded` response codes retry. Content filtering is a
refusal; unfinished messages remain incomplete, and commentary/reasoning are not
final JSON replies. Anthropic thinking usage is metadata within the inclusive output
total. Invalid additive cache/thought counters leave the affected total unknown,
retaining its budget estimate. See the [dated contract audit](API_SOURCES.md#independent-contract-audit--november-14-2026)
for source references and the distinction between provider contracts and local policy.

Explicit failure classification precedes malformed usage; optional null output
collections do not hide refusals. All providers return empty text on refusal, and
Gemini prompt blocking takes precedence over candidate output. Wrong-type response
containers, corrupt compressed successful responses and excessive JSON nesting are
sanitized retryable shape failures. Oversized successful bodies remain fatal;
bounded error-body reads preserve the known HTTP status policy. Nonfinite or
unsupported retry delays fall back to the driver's existing exponential backoff.

The failure streak counts failed **phases**, not rounds. Three consecutive failed
phases for one role abort by default. Any successful phase resets that role's streak.
Fatal setup/provider errors abort the unfinished round without resolving its actions.
Already completed public messages and attempt metadata remain in the partial logs.
The spectator viewer associates zero-based call and phase turns with one-based
resolved round numbers. It exposes an unfinished round only when call or phase
evidence exists, and labels completed commitments as unapplied until resolution.
The separately accessible final snapshot is the last resolved checkpoint, including
the initial world when no turn resolved; it does not imply a fabricated round.
Recording/progress failures stop the match and trigger bounded best-effort
finalization. The checkpoint is the last successfully resolved engine turn, including
its original submitted actions, even if its incremental write failed. Completed
phases and all started-call evidence are retained in memory and used to rebuild
JSONL at finalization. Incremental and rebuilt JSONL use UTF-8 with LF line endings
on every supported platform. A failed write never causes another model call or transition.
Persistently unwritable storage or process termination can still leave partial output.

A phase reserves the full team's maximum attempts before starting. Unknown token
usage is recorded as unknown, not zero. A configured dollar guard uses user-supplied
prices plus conservative text/image/output reservations. It is not a billing guarantee
and should not be represented as a hard external spending cap.

Call usage may contain optional `source_usage` counter-origin metadata. HTTP
adapters record only allowlisted counter paths with an omitted/null/count/invalid
state and a valid count or null. This never changes normalized accounting or copies
raw invalid values. Existing `Usage(input, output, cached, reasoning)` constructors
remain valid, with source metadata defaulting to null. Supplied counter maps are detached and
immutable (including nested counters); usage/replies remain hashable and the
existing dataclass-to-JSON recording shape is preserved. Existing schema-v2 records
without the field remain readable. See [API sources](API_SOURCES.md#slice-7-selected-profile--november-15-2026).

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
fields remain compatible; new summaries use schema version 3. `Recorder.finish` returns normally on
success and raises sanitized `RecordingFinalizationError` with ordered `failures`
pairs on failure. The driver makes at most two finalization passes and preserves
the original failure, even if recovery succeeds.
Primary and secondary finalization operations use the same `finish:<artifact>`
labels; a generic custom `finish` failure is labeled `finish:finish`.
The built-in recorder also binds version-3 provenance to actual driver inputs;
custom recorders need no new methods. Its manifest is now the eighth independent
final artifact. Execution end time/original stop reason freeze before finalization,
while writable metadata/viewers refresh the final stop reason on recovery. See
[Run provenance](PROVENANCE.md) for hook failures, compatibility, and unknown fields.
Fresh caller cancellation during client shutdown still propagates, retaining an
earlier host failure diagnostically rather than converting cancellation to exit 2.

## Campaign accounting additions

Calls add reservation quotes, complete-usage versus retained-estimate settlement
basis and settled local USD (null if unpriced). Budget summaries retain the legacy
estimate and separately expose both components, token coverage and reserved/released
calls. Turn records add `action_outcomes` classifications from engine resolution;
these are spectator metadata and never enter participant observations/history.
New outer manifest/result records use schema version 3; existing custom recorder methods remain unchanged.
See [campaigns](CAMPAIGNS.md) for whole-block reservation and two-axis reporting.

## Catalog-aware observations

Player rules describe generic lane geometry and independent motor/bridge controls.
The HUD states the room dimensions, deadline and shared mission, including required
shard recovery for retrieval/return missions. Room IDs, split/family metadata, hidden
coordinates and host certificates never enter participant requests. Only the owning
sensor image exposes heat, shard or cell/circuit facts. See [room contracts](ROOMS.md).
