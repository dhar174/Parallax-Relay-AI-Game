# Curated room catalog

Issue #20 adds catalog v1: nine immutable, hand-authored rooms resolved by one
engine. These are compatible cooperative objectives, not competing-goal or
procedural-generation experiments. Generation metadata is `curated`, seed null.

| Room ID | Family | Split | Width | Bridges |
|---|---|---|---:|---:|
| `split_span` | crossing | development | 13 | 1 |
| `dev_01` | crossing | development | 13 | 1 |
| `dev_02` | crossing | development | 13 | 1 |
| `ret_01` | retrieval_return | held_out | 9 | 1 |
| `ret_02` | retrieval_return | held_out | 9 | 1 |
| `ret_03` | retrieval_return | held_out | 11 | 1 |
| `relay_01` | two_bridge_relay | held_out | 9 | 2 |
| `relay_02` | two_bridge_relay | held_out | 10 | 2 |
| `relay_03` | two_bridge_relay | held_out | 11 | 2 |

All rooms start with six energy, use two-energy cells and a twelve-turn deadline.
Crossing variants change hidden item positions, starting positions, heat and
coolant. Retrieval rooms put extraction on the starting bank: recover the shard
across the gap and return the whole team. Their public shared mission requires
the shard for victory. Relay rooms require two independently cooled/powered
bridges and resource decisions. Split Span keeps its original victory behavior.

## Engine and perception

`RoomDefinition` validates geometry, structural family, resources, starting bank
and disjoint controller interaction ranges. `initial_world(room_id='split_span')`
constructs canonical per-motor heat, powered-bridge and collected-cell state.
The resolver selects an adjacent controller and checks every crossed gap; cells
are collected once. Resolution order remains VENT, REROUTE, movement,
collection/unlock, terminal checks. Scoring weights and private goals are unchanged.
Single-bridge legacy accessors derive from canonical state rather than duplicating it.

The common HUD exposes positions, dimensions, deadline, resources, own goal and
public mission requirements. Exact heat belongs to PYRA's thermal PNG; shard
locations to SPECTRA's optical PNG; cells/circuit mappings to FLUX's PNG. Generic
player titles and rules omit catalog IDs, families, split labels and solutions.
World snapshots, full definitions and certificates are privileged host data.
Actual role PNGs are recorded even when `no_images` omits provider attachments.

## Local selection and verification

```bash
python -m parallax_relay.play --list-rooms
python -m parallax_relay.play --mock --room dev_01 --max-turns 1
python scripts/check_rooms.py
```

`--list-rooms` returns metadata only, without loading credentials. TOML
`match.room_id` defaults to `split_span`. CLI single matches and the workbench
allow development execution. Held-out rooms require a registered protocol-2
confirmation or matching protocol-3 exploratory validation through the
[campaign runner](CAMPAIGNS.md). Diagnostics/reruns cannot
select held-out rooms. Membership validation runs before credentials or output.

The host-only certificates in `room_certificates.py` are solvability proofs,
never participant policies. All nine win in 7–10 turns with five energy, all three
private goals, no damage and no illegal actions. The original fixed script fails
team victory on all six held-out rooms. This demonstrates different required
plans; it does not establish difficulty or model generalization.

Held-out means a prescribed development/confirmation workflow, not secrecy of this
public source catalog. Arbitrary in-process Python and pure resolver/certificate
APIs are trusted host code, not sandboxed participants. The runner's permit binds
execution to a validated registration, trial and unchanged catalog/input identity.
Unsigned files establish consistency, not authenticity.
