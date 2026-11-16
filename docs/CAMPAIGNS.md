# Registered evaluation campaigns

Slice 8 implements the scheduler and analysis specified by [evaluation protocol
v1](EVALUATION.md). Registration, execution and analysis are separate CLI actions.
No dashboard, new room, provider fallback or paid experiment is implied.

## Offline diagnostic quickstart

Activate the locked development environment. From the repository root:

```bash
python -m parallax_relay.campaign register \
  --spec configs/campaign_offline.json --out runs/my-campaign
python -m parallax_relay.campaign run --campaign runs/my-campaign --offline
python -m parallax_relay.campaign analyze \
  --campaign runs/my-campaign --out runs/my-campaign-report
```

Both destinations must be fresh. The example registers 15 trials: scripted, WAIT
and uniform-v1 across all five arms, with two turns and one attempt per request.
It schedules 216 maximum attempts. It is a small diagnostic, not a pilot,
confirmatory cohort, model benchmark or proof of communication benefit.
Policies use their normal fresh role-local requests and the authoritative engine.
Without pricing, monetary fields remain null even though the built-in policies
return known zero token usage. Offline mode never reads credential files or
constructs HTTP agents. The workbench's companion remains single-match/mock-only.

## Specification and registration

The JSON specification is version 1; unknown keys are rejected. Its fields are:

| Field | Contract/default |
|---|---|
| `schema_version`, `protocol_version` | `1` |
| `stage` | `diagnostic` (default), `pilot`, or `confirmatory` |
| `mode` | `offline` (default) or `live` |
| `policies` | Unique selection of `scripted`, `wait`, `uniform`; all three by default |
| `roster` | Live-only, exactly three entries; each has `provider`, bare `model`, `api_key_env`, complete `pricing` |
| `rooms` | Only `["split_span"]` is implemented |
| `conditions` | Unique subset of the five arms; all five by default |
| `repetitions` | Diagnostic default 1; pilot exactly 5; confirmation exactly 30 |
| `match` | Existing match settings shared across arms; omit `condition`; the schedule supplies condition/round count |
| `campaign_max_calls` | Required positive integer; conservative block admission counts every possible attempt |
| `campaign_max_estimated_cost_usd` | Required positive live estimate guard; omitted for unpriced offline policies |
| `scheduler_seed` | Nonnegative integer, default 0; controls order, not model randomness |
| `min_trial_interval_seconds` | Minimum between trial launches, default 0; trials always run serially |
| `rerun_of`, `rerun_reason` | Optional original trial UUID and `infrastructure_recheck`/`manual_recheck`; one offline diagnostic trial only |

Pilot/confirmation require all five arms and all three prescribed baseline teams.
For model teams, enumerate unique provider/model permutations across the three
roles. Repeated `(provider, model)` pairs deduplicate; repeated identities must use
the same pricing/account-variable configuration. Deterministic oracle/WAIT teams
run once per condition; uniform teams use the full repetition count without
model-label multiplication. For three distinct model identities this gives 150
pilot and 900 confirmatory model trials per room, plus 35/160 baseline trials.

`register` does not resolve keys, construct HTTP agents or contact providers. It
freezes the validated specification, UUID allocation, block ordering, source,
Python/package/OS environment, input fingerprints, API contracts, prices, limits
and analysis version/seed. It writes a checksummed registration and verifies its
readback. Hashes establish consistency, not authenticity. Registration includes
static prompt/schema/room identity and is spectator metadata, never player input.

Protocol cohorts require clean Git source and complete environment identity.
Diagnostics may use dirty/unavailable source, with explicit inference limitations.
Registered inputs must still match before a protocol campaign and each subsequent
trial launch. New cohorts, not edited registrations, represent changed inputs.

After a complete, eligible pilot, register confirmation using a new specification
with `stage="confirmatory"` and `--pilot runs/the-pilot`. Its registration links
the pilot hash and records changed frozen sections/settings. Changed rooms,
roster or baseline selection require a new pilot. Pilot results are never pooled
into confirmation; missing/failed trials cannot be replaced for favorable results.

## Execution, budgets and interruption

`run --offline` only accepts offline registrations. Future live execution requires
`run --live`, exact roster/condition eligibility evidence, local credentials and
separate explicit approval of the registered spending exposure. No live campaign
was conducted to deliver Slice 8. `--env-file` is live-only, uses literal loading,
and preserves process-variable precedence; credential values are never recorded.
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
Cancellation drains cooperative role tasks and attempts bounded client cleanup.

Exclusive creation of `.runner.lock` prevents concurrent workers. `started.json`
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
provider rankings, general image understanding or broad cooperation.

## Accounting additions

Each native call now records `reservation_quote_usd`, `settlement_basis`
(`complete_usage` or `retained_estimate`) and `settled_amount_usd` (null if unpriced).
Budget summaries separately expose known-usage-priced and retained-estimate totals,
partial token coverage, cached/reasoning counters and reserved/released call counts.
Inclusive reasoning tokens are not added again to output. Counter-origin states
remain reported distinctly from normalized zero defaults.

Turn records add spectator-only `action_outcomes` from engine resolution. These
diagnostics never enter requests/history or provide policies with a legality oracle.
Existing engine outcomes, reply schemas and historical recording readers remain
unchanged; new fields are additive within recording schema version 2.
