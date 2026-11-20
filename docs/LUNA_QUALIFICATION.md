# Retrospective all-Luna qualification

The explicit `exploratory-luna-under20-v1` profile uses three fresh independent
`openai/gpt-6-luna` agents. It adds protocol **4**, while preserving protocols
1–3, their defaults and hashes. Specifications and registrations remain schema
2; native records and provider request format remain version 3. The workbench
continues to configure/import individual matches; it does not launch campaigns.

This gate reuses a fixed, committed selection of ten completed all-Luna development
model cases and 45 completed controls. The supplement supplies five Split Span
model cases, one for each arm. The original mixed-provider pilot remains incomplete;
its stopped model trial and all costs remain in historical accounting. Successful
completion yields a **retrospective composite exploratory qualification**, not a
repaired original pilot or formal confirmation under the original research gate.
Completed defeats are eligible. There is no qualification win-rate threshold.

See the [November 18 qualification evidence](verification/2026-11-18-luna-qualification.md)
for the completed supplement and the status of held-out validation.

## Fixed design

| Stage | Rooms | Model / control cases | Maximum paid / total requests | Local estimate guard |
|---|---|---:|---:|---:|
| Qualification supplement | Split Span | 5 / 0 | 864 / 864 | $1.25 |
| Validation | Six held-out rooms | 30 / 90 | 5,184 / 20,736 | $7.50 |

Every stage uses all five arms, one repetition, one all-Luna assignment per room,
12 turns, 216 calls per match, two attempts, a 60-second attempt timeout, 4096
output tokens, four history turns, 0.5-second retry delay, three failed phases,
8192 image-token reserve, seed zero and one-second serial trial pacing. The
per-match guard is $0.25. Input/output rates are $0.125/$0.50 per million tokens.
The provider adapters, match driver, game engine, observations and reply rules are
unchanged. Aliases and provider backend revisions remain unattested.

The prior mixed pilot plus continuation local estimate is $1.044149250, including
$0.406677000 retained for unknown usage. Add the new $1.25 supplement guard,
the later $7.50 validation guard and a separate $0.25 prior-Q allowance for a
combined planning allowance of **$10.044149250**. These are local estimates and
guards, not reconciled invoices or a provider billing guarantee. Each new paid
stage needs its separate exact approval. No automatic rerun, cap increase or
provider substitution is permitted by preparation, registration or qualification.

## Evidence and source bridge

[`luna_qualification_selection_v1.json`](../configs/luna_qualification_selection_v1.json)
fixes the 55 exact cells, trial IDs, original registrations/reports/CSVs/ledgers,
native artifact digests and five missing cells. It contains digests and sanitized
identities, not private spectator dialogue or images. The selection was committed
before a supplement registration. Runtime evidence roots stay local.

The offline auditor checks each native record against **its own original frozen
registration** before comparing origins. It rejects duplicate JSON/JSONL keys,
inconsistent settings/provenance, missing or corrupt PNGs, changed file inventory,
unfinished role phases, contradictory stops, cleanup faults and unbalanced
reservations. The required native inventory includes all turn sensor/spectator
PNGs, the final spectator PNG and viewer. PNGs are decoded; HTML is not executed.
Controls alone may come from the incomplete mixed parent. Selected model cases
must come from completed eligible all-Luna origins. Recoverable bounded retries
are allowed when every role phase eventually succeeds. Unknown usage retains
conservative accounting; it is never counted as free.

Each protocol-4 ledger settlement and release must match the validated native
budget and registered exposure. A turn-limit result must reach all 12 turns.
Viewer bytes must match the immutable template and complete native payload.
Retry histories reject unknown and definitely fatal statuses; existing logs do
not distinguish fatal versus recoverable `response_failed` backend error codes.

A clean-source bridge pins both complete Git trees, their modes/object identities,
the exact changed-path set and its canonical transition digest. It defaults to
denial outside the qualification/profile/campaign/preparation/tests/docs changes.
Match execution helpers, their existing imports/global bindings and all unchanged
engine/provider/settings/observation/recording modules are protected. A fresh
reviewer must inspect the whole specific bridge diff before spending. The target
source, environment and all nine room inputs then stay frozen through validation.
At the measured seven seconds per 55-case audit, two full checks per held-out case
would add roughly 28 minutes across 120 cases, before provider/game time. This
is an indicative local measurement, not a duration guarantee; retain both checks.

This operates on a **trusted locked host**. Git/package fingerprints establish
local consistency; they do not attest installed binary bytes, ignored import
overlays, arbitrary same-process agents, provider wire delivery or remote models.
Observed `PYTHONPATH`/`PYTHONHOME` overrides prevent bridge creation/checking.
Credentials and native spectator content must remain private.

## Offline commands

Use fresh ignored destinations and the intended locked Python interpreter. These
commands make no provider requests and grant no spending authorization:

```bash
python scripts/prepare_campaign.py prepare \
  --profile exploratory-luna-under20-v1 --out runs/luna-candidate
python scripts/prepare_campaign.py check \
  --profile exploratory-luna-under20-v1 --bundle runs/luna-candidate --require-clean
python -m parallax_relay.qualification audit --evidence-root /local/preserved/runs
python -m parallax_relay.qualification bridge --out runs/luna-source-bridge.json
python -m parallax_relay.campaign register \
  --spec runs/luna-candidate/qualification.json --out runs/luna-supplement \
  --qualification-selection configs/luna_qualification_selection_v1.json \
  --evidence-root /local/preserved/runs --source-bridge runs/luna-source-bridge.json
```

The supplement registration has `pilot=null` and hash-bound `qualification`
metadata tagged `selection`. Only protocol 4 accepts these new CLI authorization
flags. Existing `--pilot` behavior remains available for its original protocols;
the three binding flags are mutually exclusive. Rehashed replacements cannot
substitute cases: the checker also compares the selection with the one committed
in the exact target source and revalidates original/native evidence.

Before any supplement request, assemble and obtain approval for its concrete
$1.25 / 864-request receipt: exact source/environment/spec/registration/bridge/
selection identities, interpreter, command, output/progress/exit paths, disk,
time/storage assumptions, monitoring, unknown quota/host continuity and invoice
limitations. The runner checks at least 5 GiB free before environment copying,
credential files, clients or markers; it stops new trials below 2 GiB. Run one
worker only. Save actual PID/start identity and actual exit evidence. When only
waiting remains, use one quiet lightweight check per ten-minute heartbeat; never
restart a worker or next stage automatically.

After a separately approved successful supplement, these offline commands create
and check the qualification receipt, then register validation:

```bash
python -m parallax_relay.campaign analyze \
  --campaign runs/luna-supplement --out runs/luna-supplement-report
python -m parallax_relay.qualification build \
  --supplement runs/luna-supplement --out runs/luna-qualified.json
python -m parallax_relay.qualification check --receipt runs/luna-qualified.json
python -m parallax_relay.campaign register \
  --spec runs/luna-candidate/validation.json --out runs/luna-validation \
  --qualification runs/luna-qualified.json
```

Qualification requires all five new cases, 15 composite model cases and 45
controls with only consistent victory/defeat/turn-limit stops. A binding guard,
infrastructure failure, anomaly or incompatible evidence blocks the gate.
The receipt is regenerated from the native evidence when checked; a self-hash
or `qualified=true` flag alone cannot unlock validation. Validation registration,
execution preflight and direct `RoomExecutionPermit.validate` recheck it. This
is a registered-runner gate, not a sandbox for trusted Python code.

Stop for a separate **$7.50 validation spending approval** after registration.
Qualification approval never authorizes validation. Retain every attempted case,
old failure and unknown cost. Protocol-4 reports use descriptive analysis version
4, always `confirmatory_eligible=false`, with no exposed confidence intervals or
bootstrap. Unknown rates/differences remain null with missingness bounds. No
model ranking, significance, equivalence or population generalization follows.
