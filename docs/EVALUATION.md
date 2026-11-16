# Cooperative-game evaluation protocol

Protocol version **1**, November 14, 2026. This is a prospective specification for
#17, not benchmark results or authorization to spend money. It defines requirements
for controls (#18), the campaign runner/analysis (#19), and held-out rooms (#20).
Slice 8 controls implement all five arms, WAIT and uniform-v1 alongside the scripted
oracle; see the running guide for their CLI and provenance contracts. This protocol itself supplies no campaign results or new rooms. Parent research gate #9 stays open;
live claims also require bounded provider/model compatibility evidence under #8.

## Question and comparison scope

The primary question is whether full communication improves operational success
over disabled communication for a fixed room set, roster, limits, and adapter
contracts. This contrast includes both information exchange and extra response
opportunities. It cannot isolate the effect of teammate information alone.

| Arm | Communication/input treatment | Prespecified comparison and interpretation |
|---|---|---|
| `full` | Broadcast, negotiation, commit; role PNG plus own HUD | Reference condition |
| `reduced` | Broadcast, commit; same role PNG/HUD | Full minus reduced: benefit of the additional negotiation phase, with different call opportunity |
| `disabled` | Commit only; same role PNG/HUD | **Primary:** full minus disabled, combined communication/protocol benefit |
| `withheld` | Same phases and limits as full, but all message outputs withheld from subsequent requests | Full minus withheld: access to the published messages at matched phase/call opportunity |
| `no_images` | Full communication; omit all role PNG attachments, preserve each role's own HUD | Full minus no-images: incremental value of images conditional on the existing text/HUD |

The three secondary contrasts are exploratory. Matched opportunities do not mean
equal actual calls, tokens, latency, or hidden computation: retries and early stops
can differ. Withheld messages include a role's own earlier public messages, so this
contrast also removes that public scratchpad. It is not a pure estimate of teammate
information. Image removal does not establish general visual understanding or
control for every semantic difference in the input. No comparison establishes
provider ranking, broad cooperative ability, or out-of-distribution generalization.
Results for a fixed room apply to that room/protocol and stated campaign window.

## Information boundaries and implementation gates

Every trial starts from fresh agents, histories, notes, and room state. Preserve
sealed commitments and complete phase barriers. Participants receive only their own
projected observation, permitted messages, private notes, and bounded local history.
Never supply full snapshots, spectator artifacts, other roles' HUDs/PNGs/notes, or
hidden-state legality information to a policy. Publication into a privileged log
does not authorize publication into player inputs.

For `disabled`, skip broadcast and negotiation entirely. For `withheld`, still
execute/validate/account for their responses, but give every subsequent request an
empty public-message collection. Do not leak message text through history, notes,
repair prompts, summaries, response lengths, status flags, or other side channels.
Histories must retain no public messages from preceding turns either. Own commit
notes remain role-local and can only derive from inputs actually allowed in that
trial. Retry repairs describe only that role's output validation. Full and withheld
use identical phase schedules and per-request limits; no extra deliberation loop is
added. For `no_images`, remove image attachments for every role, preserving the same
own-HUD projection and schemas; do not substitute descriptions/OCR or expose a
hidden-state text representation. Other arms retain their role-specific images.

`AgentRequest.include_image` defaults to true. The no-images arm sets it false
on every request/retry; all three adapters omit image parts and budget quotes omit
`image_token_reserve`. Valid role PNGs remain in observations and spectator records.
Empty image bytes are never used as a substitute for explicit attachment control.

The driver filters withheld public messages and metadata at request and history
construction, including later turns. Effective settings and provenance v2 support
all five arms; the frozen provenance-v1 reader retains historical full/reduced
records. Inputs never substitute spectator state or a replacement scratchpad.

Use a minimal, versioned public condition notice so prompts do not falsely promise
messages or images that are absent. Freeze/hash each prompt variant; disclose this
framing difference as a limitation. Use the same notice template in all arms,
stating only the phase schedule, message availability and image availability.
Do not add effort instructions, replacement scratchpads or additional thinking
prompts for withheld inputs. The full/withheld contrast includes removal of the
role's public scratchpad and any effort change induced by that factual notice.
No provider tools or cross-trial memory are allowed. The intercepted HTTP tests
verify actual serialized requests for every arm, including later turns, retries,
histories, notes and exhausted fallbacks. Provenance v2 records each actual arm;
future controls must retain that distinction. Running `--fast` alone is never a
no-communication experiment.

## Baselines

Keep the existing scripted solution as a solvability/infrastructure oracle. It
knows `PLAN` and does not interpret images; its victory is not model evidence. A
future room needs a verified oracle or comparable solvability certificate.

Two simple policies are implemented under #18 for use before comparative campaigns:

- **WAIT:** empty broadcast/negotiation messages; `WAIT` on every commitment and
  empty private notes. This is a deterministic floor, not a competent agent.
- **Seeded uniform:** empty messages/notes and one uniformly sampled canonical
  action per commitment from the ordered role list below. Each role has its own
  deterministic draws keyed by turn, independent of reply timing and other roles.

The common ordered list is `WAIT`, `MOVE(-1,1)`, `MOVE(-1,2)`, `MOVE(+1,1)`,
`MOVE(+1,2)`. Append `COLLECT` for SPECTRA; `VENT` for PYRA; `REROUTE`, `COLLECT`,
`UNLOCK` for FLUX, in that order. All non-MOVE direction/steps are zero. These are
role-appropriate action kinds, not a hidden-state legality filter: out-of-range
movement, missing items, unavailable resources, or invalid locations receive the
normal engine consequences. Policies never retry a schema-valid illegal move or
consult the world to improve a draw.

For uniform-policy version 1, derive each commitment's integer seed from the first eight
bytes, big-endian, of SHA-256 over UTF-8 canonical JSON
`["uniform-v1", "<canonical trial UUID>", "<ROLE>", <zero-based integer turn>]`, using the canonicalization in
[Run provenance](PROVENANCE.md). Use a local `random.Random(seed)` and `randrange`
over the fixed ordered list exactly once for that key; record the derivation,
per-turn seeds, policy version and Python version. Reconstructing or retrying a
commitment must return the same action for its key; it must not advance a mutable
cross-turn stream. Communication phases consume no draws. This is a local policy
seed, not a provider seed. Explicit offline context records policy identity;
provenance never infers a policy from arbitrary agents.

Run deterministic controls once per distinct room/condition/policy configuration,
deduplicating meaningless provider-role labels. Repeated identical executions are
verification repeats, not independent experimental samples. Uniform teams use the
same 5-pilot/30-confirmatory repetition rule **per room/condition/policy configuration**,
with distinct trial UUIDs. Across five arms this is 25 pilot and 150 confirmatory
uniform-team trials per room, without multiplying by model-roster permutations.
Baseline trials are additional to the model-roster
counts below and must be listed in the registered campaign budget.

## Trial identity, assignment, and repetitions

A trial is one fresh attempted match for a declared room, ordered model-to-role
assignment, condition and repetition. Its scheduler allocates a unique trial UUID
before setup. An experiment UUID groups the frozen campaign; every Recorder has
its own run UUID. IDs label observations, not seeds or proof of independence. The
current CLI UUID flags do not implement scheduling or deduplication.

The #19 ledger records allocation, launch, setup failures, cancellations,
artifacts and missing-artifact status even if failure precedes Recorder creation.
A rerun gets new trial/run IDs and an explicit link/reason to the original trial;
it never overwrites or silently substitutes for it in the confirmatory analysis.
Report operational reruns separately. No outcome-dependent retries at trial level.

Enumerate every unique permutation of the roster across SPECTRA/PYRA/FLUX, with
equal repetitions in each assignment. Deduplicate identical assignments when model
identities repeat, using the `(provider, requested model ID)` tuple as identity.
The same model-ID string from different providers is distinct. Different models
from one provider remain distinct roster entries. Freeze requested models, known
revisions, provider contracts and sampling support; record unknown remote revisions
and omitted/provider-default sampling explicitly. Provider seeds, when unsupported,
stay unknown. Call identical aliases across a campaign the same requested model,
not proof of a stable remote backend; disclose drift/outages and campaign dates.

Use **5 pilot and 30 confirmatory trials per unique assignment/condition/room**.
For three distinct models and five arms this is:

| Stage | Assignments | Repetitions | Conditions | Trials per room/roster |
|---|---:|---:|---:|---:|
| Pilot | 6 | 5 | 5 | 150 |
| Confirmatory | 6 | 30 | 5 | 900 |

A block is `(room, assignment, repetition)` containing all five arms. Randomize
arm order within each block and interleave assignments using a recorded scheduler
seed; freeze ordering/concurrency/rate limits before launch. Pairing is by block,
not shared provider randomness. Use distinct fresh trials and contexts throughout.
Block scheduling reduces temporal confounding but cannot eliminate provider drift.

Pilot results diagnose feasibility and budget/controls; retain them all, report
them separately, and exclude them from confirmatory estimates. Freeze the protocol,
analysis, source, prompts, dependencies, settings, roster/prices and room membership
after the pilot and before confirmation. Record changes and begin a newly registered
cohort if these inputs change. No optional stopping for significance, cherry-picked
role assignments, silent model replacement, or selection of only winning runs.
Thirty repeats is the selected fixed design, not a demonstrated power guarantee.

## Rooms and claim gates

The Split Span is a public development room with a known solution. Current results
would support only this fixed-room comparison. Under #20, split by room **family**,
not merely random seed: variants sharing layouts/solution templates belong in the
same split. Freeze and publish held-out family/instance membership and generation
seeds before tuning; keep them out of prompts, examples, policy construction and
development feedback. Verify solvability and observation privacy independently.
No held-out generalization claim is allowed until such rooms actually exist and are
evaluated without tuning on their outcomes. Multiple seeds of the same template
are not independent evidence of generalization to a new family.

Campaign eligibility requires declared model/condition/room identity and pinned
clean source plus a complete, recorded environment. Freeze configuration and prompt/
schema/room hashes. Dirty/unavailable source or unknown custom-agent identity may
support diagnostic runs, not a reproducible confirmatory cohort. Check eligibility
before launch; if discovered afterward, retain the trials and label the affected
cohort as nonconfirmatory. Never discard failed trials to repair provenance quality.
Provider revision/sampling limits remain disclosures even when local inputs are
fully identified; no deterministic remote-output promise follows from provenance.

## Outcomes and denominators

The primary binary endpoint is **operational success**: engine `win=true` and final
`stop_reason="victory"`. Every launched trial contributes to its denominator,
including zero-call stops, setup errors, aborts, cancellations and missing artifacts.
An engine victory with `local_error` is an engine win and an operational failure.
Unknown outcomes have no observed operational success and remain explicitly unknown
on the engine axis; this does not assert they were engine defeats.

Report two axes for every trial:

1. Engine state: win, defeat, known nonterminal, or unknown/unrecoverable. Give
   `completed`, scores when defined, and last resolved turn/checkpoint.
2. Execution status: `victory`, `defeat`, `turn_limit`, `call_budget`, `spend_budget`,
   `provider_error`, `unreliable_agent`, `internal_error`, `local_error`, `cancelled`,
   or a separately named pre-match setup failure/missing outcome. Keep original
   execution stop and final recording stop distinct when they differ.

Always publish planned, launched, unlaunched, artifact-available, terminal,
nonterminal, aborted, cancelled, and unknown counts by arm/assignment/room. Define
launch as the scheduler beginning trial setup, before config/output/client creation;
mere preallocation of a UUID is not launch. Attach timestamps/reasons for unlaunched
trials. Aborted/cancelled are execution categories and can overlap engine terminal
state; publish a cross-tabulation rather than adding overlapping categories.

Turn/budget limits are bounded incomplete runs unless the engine itself terminated.
Provider, reliability, local/internal errors and cancellation do not automatically
become engine losses. Shape-invalid outputs and fallbacks are attempt/phase metrics,
not new independent trials. Report schema-valid engine-illegal actions separately.
Terminal-conditional win rates can be secondary descriptions only, with their exact
selected denominator. Do not omit censored/failed trials from primary success rates.

For missing artifacts, report observed success over all launched trials and bounds
allowing unknown launched outcomes to succeed; do not silently infer a world state.
Also give all-planned bounds allowing unknown/unlaunched outcomes to succeed. A
campaign stopped by budget or infrastructure before its planned cohort completes
is incomplete: report descriptive estimates/bounds, not a complete confirmatory
comparison or a selectively completed-pairs result.

A recorded pre-match setup failure is a known **zero operational success**, even
if it leaves no manifest or recoverable engine state. It does not enter the unknown
operational group merely because the engine axis is unknown. If `S` successes and
`U` genuinely unknown operational outcomes occur among `L` launches out of `P`
planned trials, launched bounds are `S/L` to `(S+U)/L`, and all-planned bounds are
`S/P` to `(S+U+P-L)/P`. Report undefined rates for zero denominators. Known setup
failures stay zero in both bounds; missing operational outcomes alone can widen
the launched upper bound. The ledger, rather than manifest presence, determines
whether a setup failure is known.

Synthetic accounting example (not an experiment): 12 planned, 10 launched, 2
unlaunched; the launched trials comprise 5 ordinary victories, 1 engine win with
`local_error`, 1 defeat, 1 turn limit, 1 provider abort, and 1 cancellation. Assuming
the last three have known nonterminal checkpoints and all ten artifacts are known,
operational success is **5/10 = 50%**; engine wins are **6/10**; terminal-only engine
win rate is **6/7 = 85.7%**, a selected subset. All-planned operational bounds are
**5/12 to 7/12 = 41.7%–58.3%**. None of the incomplete trials is relabeled a defeat.

## Analysis and uncertainty

Publish raw per-trial rows and cell counts, then equal-weight summaries over
prespecified role assignments. Separate rooms and rosters; any pooled summary must
use registered weights and retain per-cell results. Use two-sided **95% Wilson
intervals** for individual binary rates, reporting numerator/denominator. For the
synthetic 5/10 operational rate the interval is approximately **23.7%–76.3%**.
Intervals describe repeated-trial uncertainty under the stated design, not coverage
of unseen rooms, independent providers or a stable future service.

For the primary full-minus-disabled success-rate difference, use a **stratified
paired-block bootstrap**, 10,000 resamples, analysis seed 0. Within each role
assignment for a given room/roster, sample its 30 repetition blocks with replacement,
keep all arms together, compute arm-rate differences, then average assignments
equally. Report the observed absolute difference in percentage points and the 2.5th/
97.5th percentiles of bootstrap differences using **Hyndman–Fan Type 7** linear
interpolation: for sorted zero-indexed values, interpolate at `h=(n-1)*p` between
`floor(h)` and `ceil(h)` for `p=0.025` and `0.975`. Record
the analysis code/version and PRNG implementation. The analysis seed is not a model
seed. Independent trials do not become matched remote random draws by being paired.

Confirmatory inference requires the full prespecified cohort and no unknown
outcomes: launched failures remain zero operational successes; missing or unlaunched
members are not dropped, imputed as known outcomes, or replaced by a convenient
complete-pair subset. Otherwise report bounds and an incomplete-cohort limitation.
Report degenerate bootstrap intervals explicitly; identical outcomes and zero
observed differences do not establish equivalence or absence of an effect. This
fixed sample design has no prespecified minimum detectable effect. Treat secondary
contrasts and score/efficiency comparisons as exploratory, without a significance
claim selected from multiple comparisons. Do not extend fixed-room intervals to a
room population; a future held-out-family design needs its own clustered analysis.

## Reliability, efficiency, usage, and cost

Report all stop reasons, per-role/phase attempts, retries, refusals, incomplete
responses, shape errors, engine-illegal actions, silent/WAIT fallbacks, and unknown
usage. Distinguish started attempts from reserved allowance and released capacity.
Use counts with their units/denominators; valid-but-illegal game actions receive no
strategic retry. Preserve failed-trial diagnostics with sanitized stage/status data.

The campaign runner measures trial wall time from launch through finalization/client
teardown. Separately report provenance `lifecycle.elapsed_seconds`, which
covers match execution and cooperative task draining but excludes final artifact
writes/client cleanup. Missing end times remain unknown, not zero. Give per-attempt
latency and trial-duration distributions with counts and median/interquartile range;
do not rank a fast abort as efficient completion. Report successful-terminal
turns/scores/energy and conditional efficiency separately from all-trial success.
Nonterminal scores remain undefined/null; do not fabricate losses or zero scores.

Use reported input/output/cached/reasoning token counts with their coverage and
`unknown_usage_calls`. Partial usage is not complete usage; show known counts and
retained estimates separately. Estimated USD uses the recorded price table and
reservation policy, not provider invoices. Null means unavailable, never free.
Mocks with complete pricing report known zero usage/cost; unpriced mocks retain
null. Report cost per launched trial and successful completion with explicit
denominators and coverage; do not silently drop unknown-cost or failed trials.

#19 supplies additional accounting instrumentation for that split.
The legacy `estimated_cost_usd` field merges known-usage prices and retained quotes;
Slice 8 additionally records each call quote and settlement basis. Record the per-attempt reservation quote,
whether settlement used complete usage or retained the estimate, and the settled
amount; expose separate known-usage and retained-estimate totals in budget output.
Their sum must reconcile with the existing estimate when fully priced. Preserve
partial token coverage independently, and use null monetary amounts when unpriced.
The Slice 8 campaign guide documents those additive accounting fields.

## Registration and campaign budgets

Before any launch, register experiment UUID, protocol version, hypothesis/arms,
room split, roster/rotations, pilot and confirmatory counts, all source/input hashes,
per-match limits/prices, ordering seed, concurrency/rate policy, analysis plan,
campaign call and estimated-dollar ceilings, and rules for infrastructure stops.
Use the same engine deadline and per-request settings across arms; only the stated
phase/image treatments differ. The current defaults are 12 turns, 216 call ceiling,
2 attempts, 60-second request timeout, 2,048 output tokens and 4 history turns;
freeze all actual settings, not only these examples. Complete pricing is required
for a dollar guard. Record seed/sampling only when supported and effective.

Choose one common per-match dollar cap that the pilot and conservative worst-case
quotes support as nonbinding across all arms, then freeze it. A tight common cap
can stop expensive arms earlier and create differential censoring despite equal
numeric limits. Retain and cross-tabulate those stops; a comparison with binding
caps estimates success under those caps, not an uncensored communication effect.
Do not raise a cap after observing confirmatory outcomes or drop capped trials.

The runner must reserve/check that a full next block fits registered
remaining exposure before starting it, using the applicable per-arm maximum
attempts and conservative dollar estimates. Keep per-match whole-phase reservation
semantics intact. With 12 turns, 3 roles and 2 attempts, theoretical attempt bounds
are 216/full, 144/reduced, 72/disabled, 216/withheld and 216/no-images: **864 per
five-arm block**. For the six-assignment design this is at most **25,920 pilot and
155,520 confirmatory attempts per room/roster**, before additional baselines or
separately reported reruns. Actual calls may be lower. These figures are design
bounds for the implemented controls, not spending authorization.

Report configured ceilings, planned maximum exposure, started/reserved/released
calls, known/estimated/unknown dollar exposure, actual completion counts, and why
trials remained unlaunched. Keep pilot and confirmation budgets distinguishable.
Dollar reservations cannot guarantee provider billing ceilings; unknown usage
retains estimates, and provider-side spending controls remain necessary. An
unexpected limit/outage stops new launches and leaves an explicit incomplete ledger,
not an invitation to change settings until favorable results appear.

## Reporting checklist and remaining work

A report must link its registration, analysis revision and raw manifest/result/
call/phase/turn evidence (review spectator privacy before sharing), list all planned
cells and departures, and disclose unknown identities, missing artifacts, service
drift, timing/cost coverage and selection limits. Present pilot separately, all
launched outcomes and denominator cross-tabs, primary estimate/interval/bounds,
exploratory contrasts, baselines, role assignments and room splits. Synthetic
examples and scripted verification stay labeled separately from model evidence.

Current [provenance](PROVENANCE.md) supplies individual-run identity and lifecycle.
#18 supplies tested policies and request controls; #19 supplies the pre-launch
ledger, scheduling, campaign budgeting and aggregation/analysis. #20 remains future
work for held-out families and solvability/privacy checks. None
of this protocol establishes live compatibility or requires a paid run in this PR.

## Slice 8 controls delivery

Issue #18 now has explicit condition selection, actual provider image omission,
withheld-history filtering, role-local deterministic policies, request-format v2
and provenance v2 with a frozen v1 reader. The workbench exports the same conditions
and invalidates live preparation after changes. The prospective requirements above
remain the campaign acceptance specification; delivery does not establish model
performance, held-out generalization or standing authorization for live requests.

## Slice 8 campaign delivery

The [campaign guide](CAMPAIGNS.md) documents implemented registration, scheduling,
whole-block admission, durable launch/setup/failure receipts, bounded cleanup,
all-outcome JSON/CSV reporting and protocol-defined statistics. The normative
requirements above continue to apply where their original wording anticipated
future implementation. Delivery is verified offline using scripted/intercepted
agents; no model campaign, held-out evaluation or benchmark claim is established.
Parent #9 remains open for #20 and its reporting gates.
