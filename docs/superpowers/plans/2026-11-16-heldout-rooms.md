# Issue #20: Versioned rooms implementation plan

Execution: superpowers:executing-plans, sequential native implementation, followed
by one independent whole-branch review. Spec: GitHub issue #20 and the approved
conversation design captured below. Base: main `9ba0306`.

## Approved design

Nine curated rooms; three development crossing rooms, three held-out retrieval/
return rooms, three held-out two-bridge relay rooms. One shared resolver, existing
three roles/six actions, compatible private goals and unchanged scoring weights.
All rooms have 6 initial energy, cells worth 2, and a 12-turn deadline. Retrieval
rooms require the shard for shared victory (recommended planning assumption that
the user authorized by proceeding). Legacy Split Span's victory stays unchanged.
No generator, conflicting goals, ECHO, physics, dashboard, deployment or paid runs.

| id | width | gaps | motors | exit | shard | cells | starts S/P/F | heat | coolant |
|---|---:|---|---|---:|---:|---|---|---|---:|
| split_span |13|5,6,7|4|12|9|10|2/3/4|4|2|
| dev_01 |13|5,6,7|4|12|8|9|2/3/4|2|2|
| dev_02 |13|5,6,7|4|12|10|9|1/3/4|5|1|
| ret_01 |9|3,4|2|0|8|1|2/1/2|4|1|
| ret_02 |9|4,5|3|0|8|2|1/2/3|2|1|
| ret_03 |11|5,6|4|1|10|3|3/3/4|5|1|
| relay_01 |9|3;6|2,5|8|7|2,5|1/1/2|4,4|2|
| relay_02 |10|3;7|2,6|9|8|2,6|0/1/2|2,5|2|
| relay_03 |11|4;8|3,7|10|9|3,7|1/2/3|5,4|2|

Privileged certificates must prove victory and every private goal, no damage or
illegal actions, nonnegative resources and at most 12 turns. They never enter
participant construction. The original fixed script remains a memorization control
and must fail all six held-out missions. Generation identity: curated, seed null.

## Global constraints / review focus

- Preserve original default mock 7-turn/63-or-42-call/5-energy/100-score behavior.
- Parameterize geometry/state without duplicate writable motor/bridge/cell fields.
- Participant HUD/PNG/system/history/notes exclude room metadata, solution hints,
  off-role secrets and hidden coordinates; public mission requirements are clear.
- Freeze historical settings/readers before extending current settings. Preserve
  existing committed examples and native import, never regenerate them.
- Deny held-out single matches and development/pilot bypasses before credentials,
  output and provider calls. Trusted host certificate APIs are not a Python sandbox.
- Keep whole-phase/block reservation, exact money, cancellation, one-shot locking,
  CSV portability and role-local histories. No model-performance claims.

### Task 1: Room catalog, state and authoritative resolver

Create `rooms.py` with immutable validated definitions and finite catalog; extend
initial_world(room_id='split_span'), canonical per-controller/bridge/cell state and
legacy Split Span access. Preserve action order, add required-shard win predicate,
resolve adjacent unambiguous controller and every crossed gap. Write failing room
tests first, then pass room and legacy engine tests. Commit verified task.

### Task 2: Projections and host certificates

Make HUD/system rules generic and render actual room geometry and role-only facts;
generic player PNG titles. Add nine hand-authored certificates and checker CLI.
Test sensor differentials/public events/private goals, nine wins and six legacy
script failures, then run full suite. Commit verified task.

### Task 3: Recording identity, compatibility and selection

New recording/result/provenance/request format 3; frozen legacy readers; validate
archived worlds against recorded definitions. Add room_id setting, --room and
metadata-only --list-rooms; UI development selector and v3 native import. Preserve
v2 imports and old CLI configuration. Test before implementation; full suite and
Node regressions before commit.

### Task 4: Campaign v2 and enforced splits

New registration/report/analysis 2, ledger envelope stays 1. Adapt v1 specs into
new registrations with protocol 1 Split Span semantics/counts. Historical v1
registrations remain analyzable; fresh registration required to execute current
code. Protocol 2 diagnostics: dev subset; pilot: all 3 dev rooms; confirmation:
all 6 held-out rooms, linked eligible dev pilot. Freeze catalog/membership/source/
environment/prompts/roster/pricing/policies/settings across transition except stage,
rooms/repetitions, campaign ceilings and scheduler seed. Registered runner grants
room execution permits; check identity before each launch. Family/split labels and
descriptive summaries, retain per-room statistics. Assert offline 105/960 schedule
counts statically and exercise bounded native runs. Commit verified task.

### Task 5: Integration, documentation and independent review

Run full Python, pip check, compilation, mock checks, workbench build/syntax/Node,
certificate checker, bounded CLI roundtrips and documentation link checks. Keep
actual evidence/counts. Update architecture/protocol/provenance/running/campaign/
roadmap/status docs. Independent whole-branch review and fix verified findings.
Create PR for #20 with the complete implementation; parent #9 remains open for
research claim gates. Inspect hosted six-job CI and attach the created PR.
