# Under-$20 exploratory pilot and held-out validation

The explicit `exploratory-under20-v1` profile is implemented for review as a
bounded descriptive study. It preserves the formal
[protocol-2 evaluation](EVALUATION.md), including its five pilot and 30
confirmatory repetitions, and cannot close the original #9 research acceptance
gate. Offline implementation authorization does not authorize provider requests,
a paid calibration, either paid stage, a merge or deployment. Actual verification,
registration and spending approval require their own dated receipts; this guide
makes no runtime-success or readiness claim.

For this task, this profile supersedes the larger original
[Q/P/C preparation proposals](CAMPAIGN_PREPARATION.md). Historical proposals,
registrations and results remain intact. The existing qualification Q evidence and
45-trial diagnostic are separate evidence and are never pooled into this study.

## Fixed design and exposure

The specification explicitly sets `schema_version=2`, `protocol_version=3` and
profile-compatible fields. The registration envelope remains version 2 and native
record/request formats remain version 3. Protocol 3 allows only `pilot` and the
new `validation` stage. It rejects `diagnostic` and `confirmatory`; protocols 1/2
cannot select `validation`. Omitting a protocol still selects protocol 2.

Every room uses all five arms (`full`, `reduced`, `disabled`, `withheld`,
`no_images`), exactly one repetition and one prespecified model-to-role assignment.
The same assignment is used for every arm in a room. Each baseline team
(`scripted`, `wait`, `uniform`) runs once per room/arm with zero provider cost.
Baseline calls remain in total call ceilings.

| Stage | Rooms | Model trials | Baseline trials | Total trials | Total call ceiling | Maximum paid requests | Local campaign guard |
|---|---:|---:|---:|---:|---:|---:|---:|
| Pilot P | 3 development | 15 | 45 | 60 | 10,368 | 2,592 | $3.75 |
| Validation V | 6 held-out | 30 | 90 | 120 | 20,736 | 5,184 | $7.50 |
| Combined | 9 | 45 | 135 | 180 | 31,104 | 7,776 | $11.25 |

All arms and both stages share a **$0.25 per-match local estimate guard**. A full
five-arm model block reserves $1.25 before any of its trials starts; match phases
still reserve the entire team's retry allowance before calls. Total new campaign
guard exposure is $11.25, plus a separately retained $0.25 allowance for prior Q
($11.50 combined planning allowance). This is below the user's $20 combined
budget, including prior Q, with no permission to expand any money limit.
**Local estimates are not provider invoice guarantees.**

The $0.25 guard is deliberately tight and is not claimed to be nonbinding. It can
stop an arm before gameplay completes. A binding money or call guard makes the
pilot unsuitable for validation: stop and report feasibility with the original
limits, trials and markers retained. Do not increase a guard, silently repeat,
replace a model or continue paid work to complete the table.

## Models, assignments and frozen settings

Every model trial creates three fresh independent agents: two
`openai/gpt-6-luna` and one `gemini/gemini-3.5-flash-lite`. Credential bindings stay
`OPENAI_API_KEY` and `GEMINI_API_KEY`; no credentials enter preparation receipts.
The global room map is frozen across both stages:

| Room | Split | Gemini role |
|---|---|---|
| `split_span` | Development | FLUX |
| `dev_01` | Development | SPECTRA |
| `dev_02` | Development | PYRA |
| `ret_01` | Held-out | FLUX |
| `ret_02` | Held-out | SPECTRA |
| `ret_03` | Held-out | PYRA |
| `relay_01` | Held-out | FLUX |
| `relay_02` | Held-out | SPECTRA |
| `relay_03` | Held-out | PYRA |

Fill the remaining roles with the OpenAI entries in canonical
`SPECTRA`, `PYRA`, `FLUX` order. Gemini is balanced across roles within each split;
there is no within-room role rotation. Legacy unique-assignment enumeration and
protocol-1/2 schedules are unchanged.

The requested models, wire contracts, engine and observations are unchanged.
Fixed settings are 12 turns, 216 calls per match, two attempts per request,
60-second request timeout, 4096 output tokens, four history turns, 0.5-second retry
delay, three consecutive failures and an 8192 image-token reserve. Scheduler seed
is 0, matches run serially, and the minimum trial-launch interval is one second.
The scheduler supplies each arm's prescribed communication rounds and image/message
treatment. No provider seed or stable remote backend revision is asserted.

| Provider | Configured input USD/M | Configured output USD/M | Basis |
|---|---:|---:|---|
| OpenAI | $0.125 | $0.50 | Conservative all-input-cache-write safety scenario |
| Gemini | $0.30 | $2.50 | Recorded standard paid rates |

OpenAI's nominal input rate is $0.10/M. The profile deliberately configures the
$0.125/M safety rate, a total input rate rather than an extra surcharge, while
leaving output and Gemini prices unchanged. This differs from the old nominal-rate
worksheet/runtime configuration. The receipt distinguishes the safety basis from
any nominal comparison. No cache-read discount, free-tier, batch or flex saving is
assumed. Recheck the dated [public source record](../configs/campaign_preparation_sources.json)
and official references in [preparation](CAMPAIGN_PREPARATION.md#reservation-worksheet-and-prices)
before spending. The offline checker does not refresh remote documentation, verify
account access, or resolve cache/invoice uncertainty.

## Prepare, check and register offline

Use the intended clean checkout with its locked development interpreter. Output
paths below are public examples, not an actual approved execution receipt. Each
new output must be a fresh ignored destination; never reuse historical artifacts.
The `runs/` tree is ignored by the repository.

```bash
python scripts/prepare_campaign.py prepare \
  --profile exploratory-under20-v1 --out runs/under20-candidate
python scripts/prepare_campaign.py check \
  --profile exploratory-under20-v1 --bundle runs/under20-candidate --require-clean
python -m parallax_relay.campaign register \
  --spec runs/under20-candidate/pilot.json --out runs/under20-pilot
```

The profile bundle contains `pilot.json`, `validation.json` and `receipt.json`.
It does not create another qualification or formal confirmatory candidate. Without
`--profile`, preparation keeps its original behavior and hashes. Both profile
subcommands retain strict duplicate-key/type validation, canonical hashes, file
readback, source/environment checks and fresh-output rules. Preparation, checking
and registration do not resolve credentials, construct provider clients or make
provider requests.

The receipt identifies the profile, source and complete environment, catalog,
all-nine-room frozen input identities, specifications and price inputs by hash.
It records limits, trial/call counts, the conservative price basis and available
nominal comparison, and marks the larger proposal superseded for this task. It
explicitly grants no spending authorization. Hashes establish consistency, not
authenticity. Dirty previews cannot serve as final spending-review identities.

Freeze the exact final tested source and locked environment in a new clean runtime
checkout. Rebuild/check the bundle there with `--require-clean`, register only the
pilot, and verify registration readback and its spec/frozen hashes against the
receipt. Registration itself allocates trial identities without authorizing a
launch. Do not register validation before an eligible pilot exists.

## Separate paid-stage approval and monitoring

Before requesting pilot spending approval, assemble a separate sanitized approval
receipt for the exact $3.75 pilot exposure. It must contain the selected models,
all source/environment/input/spec/registration hashes, exact interpreter and
commands, fresh candidate/campaign/trial/report/progress paths, current disk-free
measurement, duration/storage projections and assumptions, and known local
estimate/invoice gaps. Include provider quota/access and host-lifetime facts that
are available. Explicitly disclosed quota or host-continuity unknowns may be
accepted by the user; they never authorize higher money limits. A passing checker
alone does not make the paid stage ready.

The runner requires at least **5 GiB free disk before live credential/client setup
or one-shot markers**, then checks before each next trial and stops new launches
below **2 GiB**. Record current free bytes, units, filesystem and measurement time
for the actual output location. Resource stops leave an incomplete ledger and are
infrastructure outcomes; they are not automatically game defeats. Storage checks
cannot guarantee host continuity or durable recovery from a killed process.

Only the separately approved exact registered pilot may then use the existing
campaign runner. This command is conditional on that approval:

```bash
python -m parallax_relay.campaign run --campaign runs/under20-pilot --live
```

If needed, add the approved literal `--env-file` path; process variables retain
precedence. One root-owned worker runs serially. Immediately record its actual PID,
start time, command/output locations and first checkpoint after launch; during
preparation the PID is `not_started`. If a long-running worker becomes idle,
provide a sanitized heartbeat at least every ten minutes with elapsed time,
observable trial/call/local-estimate progress, output status and stops/unknowns.
Never delete one-shot markers, automatically relaunch, raise caps or continue
paid work without the applicable approval. Retain partial evidence and report it.

Analyze the retained pilot without provider calls into a fresh destination:

```bash
python -m parallax_relay.campaign analyze \
  --campaign runs/under20-pilot --out runs/under20-pilot-report
```

Validation requires a complete eligible protocol-3 pilot with no binding money/call
guards or cleanup faults. Source, environment, all-nine-room catalog/input identities,
roster/prices, policies and common settings stay frozen. Any changed treatment or
input requires a new pilot. Only after that gate passes may validation be registered:

```bash
python -m parallax_relay.campaign register \
  --spec runs/under20-candidate/validation.json --pilot runs/under20-pilot \
  --out runs/under20-validation
```

Review the concrete validation registration and a separate $7.50 approval receipt
before any validation provider call. Pilot approval grants no validation approval.
Only a matching registered validation permits held-out execution; standalone
matches, diagnostics and pilots cannot launch those rooms. After separate approval,
use `campaign run --campaign runs/under20-validation --live`, followed by
`campaign analyze` with a fresh report path. Pilot and validation data stay separate.

## Analysis and claim limits

Frozen analysis metadata is version 3, profile `exploratory-under20-v1`, evidence
class `exploratory`, method `descriptive_per_room`, zero bootstrap resamples,
analysis seed 0, null percentile/PRNG, concurrency 1 and primary contrast
`["full", "disabled"]`. Reports always set `confirmatory_eligible=false`.

Retain per-room/per-arm model and baseline rows, planned/launched/unlaunched
counts, every failed trial, unknown outcomes and usage/cost coverage. Keep engine
outcomes separate from operational success and infrastructure stops. Describe the
observed rate and arm difference only when their launched outcomes are known;
otherwise report null with missingness bounds and explicit denominators. Describe the
observed full-minus-disabled difference per room without repeated-trial bootstrap,
significance, equivalence, within-room role-rotation or room-population inference.
One repetition per arm cannot support those claims. Report binding guards and
incomplete schedules as feasibility limitations, without selecting favorable pairs
or replacing failures. A complete study is still exploratory and cannot satisfy
the original formal confirmation acceptance under #9.

Use the preparation script above and the [campaign CLI](CAMPAIGNS.md) for
registration, execution and analysis. The [workbench](WORKBENCH.md) remains a single-match/mock/import surface;
a campaign UI is outside scope. Native schema/request format 3 remains unchanged.
Keep private spectator dialogue, HUDs, objectives and notes private; publish only
reviewed sanitized receipts.
