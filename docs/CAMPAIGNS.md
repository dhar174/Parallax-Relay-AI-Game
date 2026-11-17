# Registered evaluation campaigns

The scheduler supports historical protocol 1 and the split-aware protocol-2
extension in [evaluation](EVALUATION.md). Registration, execution and analysis
are separate CLI actions. The [nine curated rooms](ROOMS.md) add development/held-out
cohorts; no dashboard, provider fallback or paid experiment is implied.

For the approved roster's preparation-only candidate generator, conservative
numeric reservation worksheet and separate Q/P/C spending gates, see
[Phase-2 campaign preparation](CAMPAIGN_PREPARATION.md).

## Offline diagnostic quickstart

Activate the locked development environment. From the repository root:

```bash
python -m parallax_relay.campaign register \
  --spec configs/campaign_offline.json --out runs/my-campaign
python -m parallax_relay.campaign run --campaign runs/my-campaign --offline
python -m parallax_relay.campaign analyze \
  --campaign runs/my-campaign --out runs/my-campaign-report
```

Both destinations must be fresh. This preserved version-1 example registers 15 trials: scripted, WAIT
and uniform-v1 across all five arms, with two turns and one attempt per request.
It schedules 216 maximum attempts. It is a small diagnostic, not a pilot,
confirmatory cohort, model benchmark or proof of communication benefit.
Policies use their normal fresh role-local requests and the authoritative engine.
Without pricing, monetary fields remain null even though the built-in policies
return known zero token usage. Offline mode never reads credential files or
constructs HTTP agents. The workbench's companion remains single-match/mock-only.

The new `configs/campaign_rooms_offline.json` uses protocol 2: the same commands
with that specification register 45 development trials and 648 maximum attempts.
It is also a bounded diagnostic, not a pilot or confirmation.

## Specification and registration

New JSON specifications use version 2; unknown keys are rejected. Version-1
inputs adapt into new registration version 2 with protocol-1 Split Span semantics
and unchanged trial counts. Omitting a version selects version/protocol 2. Its fields are:

| Field | Contract/default |
|---|---|
| `schema_version`, `protocol_version` | New defaults `2`; schema 1 requires protocol 1 |
| `stage` | `diagnostic` (default), `pilot`, or `confirmatory` |
| `mode` | `offline` (default) or `live` |
| `policies` | Unique selection of `scripted`, `wait`, `uniform`; all three by default |
| `roster` | Live-only, exactly three entries; each has `provider`, bare `model`, `api_key_env`, complete `pricing` |
| `rooms` | Protocol 2: diagnostics use development subset (default all three), pilots all three development rooms, confirmation all six held-out rooms; protocol 1 only `["split_span"]` |
| `conditions` | Unique subset of the five arms; all five by default |
| `repetitions` | Diagnostic default 1; pilot exactly 5; confirmation exactly 30 |
| `match` | Existing match settings shared across arms; omit `condition` and leave `communication_rounds` at default 2; the schedule supplies both and `room_id` |
| `campaign_max_calls` | Required positive integer; conservative block admission counts every possible attempt |
| `campaign_max_estimated_cost_usd` | Required positive live estimate guard; omitted for unpriced offline policies |
| `scheduler_seed` | Nonnegative integer, default 0; controls order, not model randomness |
| `min_trial_interval_seconds` | Minimum between trial launches, default 0; trials always run serially |
| `rerun_of`, `rerun_reason` | Optional original trial UUID and `infrastructure_recheck`/`manual_recheck`; one offline diagnostic trial only |

Pilot/confirmation require all five arms and all three prescribed baseline teams.
For model teams, enumerate unique provider/model permutations across the three
roles. Repeated `(provider, model)` pairs deduplicate; repeated identities must use
the same pricing/account-variable configuration. Deterministic scripted/WAIT teams
run once per condition; uniform teams use the full repetition count without
model-label multiplication. Protocol-2 offline pilot/confirmation therefore contain
105/960 trials respectively. For three distinct model identities this gives 150
pilot and 900 confirmatory model trials per room, plus 35/160 baseline trials.
An offline diagnostic containing only deterministic teams rejects repetitions above
one instead of silently discarding them. Money/interval fields reject JSON booleans.

`register` does not resolve keys, construct HTTP agents or contact providers. It
freezes the validated specification, UUID allocation, block ordering, source,
Python/package/OS environment, input fingerprints, API contracts, prices, limits
and analysis version/seed. It writes a checksummed registration and verifies its
readback. Hashes establish consistency, not authenticity. Registration includes
static prompt/schema/per-room identity and the full catalog/certificate hashes and is spectator metadata, never player input.

Protocol cohorts require clean Git source and complete environment identity.
Diagnostics may use dirty/unavailable source, with explicit inference limitations.
Registered inputs must still match before every protocol-2 campaign (including
diagnostics) and each subsequent trial launch. Protocol-1 diagnostics retain
their explicit drift/ineligibility reporting. New cohorts, not edited registrations, represent changed inputs.

After a complete, eligible pilot, register confirmation using a new specification
with `stage="confirmatory"` and `--pilot runs/the-pilot`. Its registration links
the pilot hash. Protocol 2 freezes source, environment, catalog/membership, prompts,
roster/prices, policies and match settings across the transition. Only stage,
room split, repetition count, campaign ceilings and scheduler seed may change.
Changed treatment/input settings require a new development pilot. Protocol 1
retains its same-room transition and reports changed frozen sections/settings. Pilot results are never pooled
into confirmation; missing/failed trials cannot be replaced for favorable results.

## Execution, budgets and interruption

`run --offline` only accepts offline registrations. Future live execution requires
`run --live`, exact roster/condition eligibility evidence, local credentials and
separate explicit approval of the registered spending exposure. No live campaign
was conducted to deliver Slice 8. `--env-file` is live-only, uses literal loading,
and preserves process-variable precedence; credential values are never recorded.
Selected keys are trimmed and checked before acquiring the runner lock or writing
one-shot markers. Missing/invalid keys leave the registration reusable.
Requested model aliases do not attest remote backend revisions or image ability.

The runner reserves a complete next block before starting any of its trials.
Call exposure is the sum of each arm's theoretical maximum, bounded by per-match
call caps. Dollar admission reserves the entire configured common per-match
estimate cap for each model trial. This deliberately avoids pretending future
request byte sizes are known. Choose a pilot-supported nonbinding match cap and
freeze it for confirmation. Match phase reservations still cover the whole team's
retry allowance. Unknown usage retains its quote; partial counts remain separate.

After each trial, settle actual started calls/local estimates and release unused
capacity. Missing execution receipts retain conservative exposure. Recorded
settlements are never clamped to caps: an overrun stops new launches. Setup,
provider/reliability, local/internal and unexpected per-match budget errors also
stop new launches. Unlaunched entries remain in the schedule with a timestamped
campaign-stop reason. These local estimates cannot enforce provider invoice caps.

Before setup begins, the runner durably appends a launch event. It then creates
fresh agents, state, histories, notes and a native Recorder under `trials/<UUID>/`.
The ledger captures setup failures even if no manifest can be written. Runner
duration includes finalization and client teardown; match lifecycle duration
remains separate. Cleanup failure after engine victory is an operational failure.
Cancellation drains cooperative role tasks and attempts bounded client cleanup;
cleanup failure remains recorded separately and does not relabel cancellation.

Atomic creation of the `.runner.lock` directory prevents concurrent workers and
rejects existing file/directory/symlink entries, including broken symlinks on
Windows. Marker checks run inside the owned lock; initialization failures release
that lock. Existing legacy lock files still block admission. `started.json`
and the ledger prevent automatic reruns even after a crash. There is no v1 resume
command. Analyze the existing directory; use new IDs/registration and explicit
rerun linkage for an operational recheck. Never delete a marker to resume a cohort.
Disk failures can leave a stale lock or partial ledger; report those limitations
and retain artifacts. Atomic replacement/fsync is not a cross-file transaction or
a guarantee against hardware failure or uncooperative Python/OS operations.

CLI exits: 0 for registration/report creation or a completely executed schedule;
4 for an interrupted/budget/infrastructure-stopped campaign; 2 for invalid
configuration/local operation errors; 130 for keyboard interruption. A complete
schedule can contain engine defeats or intentional turn-limit stops.

## Reports and inference

`analyze` performs no provider calls or trial execution. It writes fresh
`report.json`, `trials.csv`, `cells.csv` and `attempts.csv`, verifying readback.
New reports and analysis use version 2; ledger envelopes remain version 1.
Historical registration version 1 remains analyzable; current execution requires
fresh registration, without reinterpreting old trial IDs or adding trials.
Each file is written through a temporary file and atomic replacement; the four
files are not a transaction. String CSV cells with formula prefixes are quoted
with a leading apostrophe; JSON retains original values. Empty CSVs retain headers.
CSV fields are always enclosed in double quotes, including carriage returns, for
consistent readback on early Python 3.11 patch releases. Formula detection skips
all Unicode whitespace before checking the prefix.
Reports link registration and per-trial artifacts; model dialogue, HUDs, private
notes and image contents remain in native spectator files rather than CSV rows.
Review all spectator metadata before sharing. Reports keep:

- Planned/launched/unlaunched/artifact counts; engine win/defeat/nonterminal/unknown
  separately from execution stop reasons; original versus recording/runner stops.
- Known operational failures, genuinely unknown outcomes and explicit bounds.
  Setup failure is known zero success, even without a manifest. A saved engine win
  without a completed runner receipt leaves operational success unknown.
- Per-cell Wilson intervals, equal-assignment arm summaries, cross-tabs, attempts,
  retries/fallbacks, structured engine-illegal actions, latency, conditional scores,
  usage coverage and local known-price versus retained-estimate costs.

Operational success requires engine victory and a successful final execution and
cleanup. All launched trials stay in the denominator. Unpriced/unknown costs stay
null for full-denominator per-trial/per-success rates; known partial totals include
coverage counts. Missing artifacts do not erase a durable setup-failure receipt.

Confirmatory contrasts require the full eligible cohort, complete artifacts,
known outcomes and the registered analysis source. Analysis uses 10,000 paired
block bootstrap samples, seed 0, equal assignment weights and Type-7 percentiles.
Incomplete/ineligible cohorts receive descriptive rates/bounds without a
complete-pair substitute. Secondary contrasts are exploratory. Degenerate intervals
are labeled and do not establish equivalence. Deterministic controls are not
independent repeated samples. No fixed-room result establishes held-out ability,
provider rankings, general image understanding or broad cooperation. Reports
label every room/family/split and include descriptive family/split summaries.
Contrasts and intervals remain per-room; no pooled task-population interval is
computed from the finite curated room catalog.
Validation cross-checks ended lifecycles, scheduled mode/policy, run UUIDs, stop
reasons, engine state/energy/turns, replay sequences, phase ranges and call/usage/
cost conservation. Malformed ledgers, duplicate lifecycle events and unmatched
launch/finish receipts prevent complete-cohort inference.
Scheduled model trials require priced totals and per-attempt quotes; provided
cost components must share the total's nullability. A null runner result cannot
borrow operational success from a saved native result: the discrepancy is flagged,
while explicit operational failures and known engine outcomes remain distinguishable.

## Accounting additions

Each native call now records `reservation_quote_usd`, `settlement_basis`
(`complete_usage` or `retained_estimate`) and `settled_amount_usd` (null if unpriced).
Budget summaries separately expose known-usage-priced and retained-estimate totals,
partial token coverage, cached/reasoning counters and reserved/released call counts.
Inclusive reasoning tokens are not added again to output. Counter-origin states
remain reported distinctly from normalized zero defaults.
Numeric dollar fields have additive `<field>_decimal` strings for exact local
estimate persistence. New records reconcile those values with Decimal arithmetic;
historical numeric-only ledgers disclose their bounded serialization uncertainty.
Stop-total rounding has its own `legacy_settlement_rounding_uncertainty_usd`,
including the final receipt's serialization precision.
Partial per-role pricing keeps the overall total null, exposes `priced_roles`,
`unpriced_roles` and `priced_role_estimated_usd`, and retains priced call amounts.
Reports with no priced trials keep every cost aggregate null, including the known
partial total; explicit priced zero remains zero.

Turn records add spectator-only `action_outcomes` from engine resolution. These
diagnostics never enter requests/history or provide policies with a legality oracle.
Existing engine outcomes, reply schemas and historical recording readers remain
unchanged; new fields are additive within recording schema version 2.

## Held-out execution permits

Only the registered protocol-2 confirmation runner grants a room execution
permit. It binds the validated registration, trial, catalog and current frozen
inputs before output/provider construction, and `run_match` checks it again.
Single-match runs, diagnostics, pilots and operational reruns cannot select
held-out rooms. Pure engine/certificate APIs are trusted host utilities; the
permit is a workflow guard, not a sandbox for arbitrary Python.


Each trial launch collects one fresh frozen-input snapshot. The trusted runner
passes that checked snapshot into permit creation; the permit detaches it and
rechecks immutable registration/trial/catalog bindings at `run_match` entry.
Direct `execute_trial`/permit-factory callers collect the fresh snapshot there.
These are per-launch host receipts, not a cache to reuse across launches. Permit
creation failures return sanitized `setup_failure` receipts before trial output or
provider setup, so the campaign settles the attempted trial and releases its block.
