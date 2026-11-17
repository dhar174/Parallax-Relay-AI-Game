# Under-$20 exploratory pilot and held-out validation

Approved for offline implementation on November 17, 2026. Neither paid stage is
authorized by this implementation approval. This plan supersedes the proposed
large study for the immediate next experiment; it does not redefine the original
protocol-2 confirmatory acceptance criteria.

## Phase 1 — Freeze a small, explicit study

Implement `exploratory-under20-v1` as protocol 3 while preserving the version-2
specification and registration envelope shapes. Preserve all protocol-1/2
serialization, scheduling and analysis behavior. Native records and provider
request formats stay at their existing version 3.

Use two independent OpenAI `gpt-6-luna` players and one Gemini
`gemini-3.5-flash-lite` player. Keep all five communication/image conditions and
all nine rooms. Run each arm once with one fixed assignment per room. Assign
Gemini to FLUX in `split_span`, `ret_01`, `relay_01`; SPECTRA in `dev_01`,
`ret_02`, `relay_02`; and PYRA in `dev_02`, `ret_03`, `relay_03`. Fill the other
roles with the OpenAI entries in canonical role order. This balances Gemini's
role across each split without claiming rotation within a room.

| Stage | Rooms | Model matches | Free baseline matches | Total trials | Paid request maximum | Local campaign guard |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pilot | 3 development | 15 | 45 | 60 | 2,592 | $3.75 |
| Validation | 6 held out | 30 | 90 | 120 | 5,184 | $7.50 |

Baselines are scripted, WAIT and seeded uniform, once per room/condition. The
total registered call limits, including free baseline calls, are 10,368 and
20,736. New stage guards sum to $11.25. Reserving $0.25 for prior Q gives $11.50
of local estimated exposure, below the user's $20 budget. Unused headroom is not
authorization to increase caps or repeat a run. Local estimates are not provider
invoice guarantees; the completed Q estimate of $0.1599778 is not an invoice.

Fix 12 turns, 216 calls per match, two attempts, 60-second timeout, 4,096 output
tokens, four turns of history, 0.5-second retry delay, three consecutive failures,
8,192 image-token reserve, $0.25 per match, seed zero, serial execution and at
least one second between launches. A five-arm model block reserves $1.25.
Use safety rates per million tokens: OpenAI input $0.125/output $0.50 and Gemini
input $0.30/output $2.50. Explain OpenAI's nominal $0.10 input separately from
the conservative all-input cache-write scenario. Reject modified profile fields,
types, prices, roster or limits rather than silently substituting defaults.

Deliver pure profile builders, exact schedule/model tests and compatibility
checks. Connie Dom (Terra 6.1 Max) owns only this model/profile scope.

## Phase 2 — Implement preparation, execution gates and reporting

Add explicit `--profile exploratory-under20-v1` preparation/check commands. Write
only `pilot.json`, `validation.json` and `receipt.json`; retain old default
preparation behavior. Freeze all nine room inputs, catalog, source, environment,
settings, pricing and analysis identities before the pilot. Strictly validate
duplicates, nonfinite values, types, hashes and readback. Preparation must not
resolve credentials, construct clients, register execution or contact providers.

Require an eligible completed same-profile pilot before registering validation.
Reject binding money/call guards, cleanup faults, incomplete or anomalous pilot
evidence, changed source/environment/catalog/inputs/settings/pricing, and
standalone held-out execution. Permit held-out trials only through their matching
registered validation campaign. Pilot feasibility replaces the separate paid
12-turn diagnostic; if its guard binds, stop with a feasibility report.

Before execution reads credentials or creates markers/clients require at least
5 GiB free storage. Before each subsequent trial stop new launches below 2 GiB,
release unused block reservations and preserve an incomplete ledger. Never label
an infrastructure stop as an engine defeat. Keep whole-phase retry reservations,
Decimal accounting, unknown-usage retention and all trial denominators.

Version-3 analysis is descriptive per room, with all failures, unknowns and
unlaunched trials retained. No Wilson intervals, bootstrap, significance,
population generalization or confirmatory eligibility. Do not pool historical Q
or diagnostic data. Existing protocol-1/2 statistics remain unchanged.

Tess Tickles (Sol 6.1 High) owns preparation and its tests. Faye Cial (Sol 6.1
High) owns scoped current documentation. Root owns integration, permissions,
resource guards, reports and end-to-end tests. Workers use isolated worktrees,
commit only their files, and make no provider requests, pushes or comments.

## Phase 3 — Verify and independently review

Use failing behavior regressions before fixes, then inspect actual exit codes,
logs, readback and diffs. Test exact 60/120 schedules; malformed/tampered specs,
registrations and receipts; old canonical serialization/counts; pilot transition
refusals; held-out permits; disk checks before side effects; balanced stops;
descriptive reports; and a real recording/orchestration path with priced fake
providers and no network.

Run the complete Python suite, Node and Chromium checks, both mock CLI modes,
room certificates, compilation, dependency consistency and whitespace checks.
Inspect actual hosted CI jobs/logs after publishing a reviewable PR. Dee P.
Thrust (Terra 6.1 Max) independently reviews the integrated change for correctness,
budget admission, compatibility, leakage and evidence claims. Fix material
findings and rerun relevant verification. This review is not a security-scan
attestation, and it does not close unrelated open security/research issues.

## Phase 4 — Freeze the exact candidate and prepare separate spending gates

Create a new clean frozen checkout at the final tested source and the unchanged
locked environment. Recheck official model rates without provider calls, prepare
and check the bundle, register **only the pilot**, then read back its registration
and schedule. Preserve the original work checkout and completed Q checkout.

Publish a sanitized receipt containing exact source/environment/input/spec hashes,
models, limits, output paths, launch/analyze commands, storage/time estimates,
quota and host-continuity unknowns, and invoice uncertainty. Keep native spectator
data private. Obtain a separate explicit $3.75 pilot approval for this registration
before any paid request. Only root launches one worker. Save checkpoints and use
a ten-minute current-chat heartbeat for long waits, without duplicate polling
workers or automatic reruns, resume, marker deletion, cap changes or substitution.

After the paid pilot, analyze complete evidence and stop for review. Only if
eligible and nonbinding may validation be registered against it; obtain a separate
$7.50 approval for that exact registration. User acceptance of disclosed quota
or host-continuity uncertainty does not expand financial limits. No merge or
deployment is authorized by this implementation plan.
