# Phase-2 campaign preparation

For the current under-$20 task, use the explicit
[`exploratory-under20-v1` profile](EXPLORATORY_STUDY.md), implemented for review with
`prepare/check --profile exploratory-under20-v1`. It creates pilot and validation
candidates with $3.75/$7.50 local campaign guards and a common $0.25 match guard.
The combined new guard exposure is $11.25; the separate prior-Q allowance is $0.25.
These local limits are not invoice guarantees or spending approval.

The original protocol-2 preparation design below is retained as a dated formal
proposal. Its larger Q/P/C proposals are superseded **for this task only**; its
5/30-repetition protocol, historical receipts and default generator behavior are
unchanged. Do not use its worksheet or Q/P/C gates as the current study's approval
request. See the new guide for safety pricing, frozen identities, resource checks
and separate pilot/validation approvals.

This is **preparation only**, not standing authorization to spend, evidence of model
compatibility, a registration, or campaign results. The approved requested roster
is two independent OpenAI `gpt-6-luna` agents and one Gemini
`gemini-3.5-flash-lite` agent. Repeated OpenAI identities deduplicate to three role
assignments. Each match still creates three fresh independent agent instances.

## Generate and verify a candidate

Use the locked development interpreter from the intended checkout. Keep output in
an ignored fresh `runs/` destination; an untracked nonignored preparation artifact
would make the source identity dirty.

```bash
python scripts/prepare_campaign.py prepare --out runs/phase2-candidate
python scripts/prepare_campaign.py check --bundle runs/phase2-candidate
python scripts/prepare_campaign.py check --bundle runs/phase2-candidate --require-clean
```

The first command writes three candidate specs and `receipt.json`, then reads and
checks every file back. The checker independently rebuilds them using current
code, catalog, smoke profile, source-verification record and environment. It strictly
validates each candidate against `CampaignSpec` and compares raw canonical hashes
for specs, receipt and write/readback, rejecting integer/float/boolean substitutions
as well as edits or drift. Source, profile, specs, receipt and written-file readback
reject duplicate JSON object keys at any depth before validation or hashing; the
source record also requires an integer schema version. `--require-clean` also
requires clean Git and complete environment identity. It never reads credential
files, resolves keys, constructs HTTP agents,
registers campaigns or executes trials. Shared Git provenance probes look up only
the [public process settings allowlist](PROVENANCE.md), rather than copying the
whole process environment into Git children. This is a privacy boundary, not a
sandbox or an audit of Git configuration files. Schedule construction counts exposure;
its temporary UUIDs are discarded, and no trial allocation or launch is recorded.

`qualification.json` is explicitly a **protocol-2 diagnostic** with only Split Span,
no baseline policies, all five conditions, one repetition, two turns, 36 maximum
calls per match and two attempts. Pilot and confirmatory candidates use all three
development/all six held-out rooms, respectively, all five arms, all three baseline
policies, five/30 repetitions, 12 turns and 216 calls per match. All candidates fix
4096 output tokens, four history turns, 60-second timeout, 0.5-second retry delay,
three consecutive failures, image reserve 8192, seed 0, serial trials and a
one-second minimum launch interval.

| Candidate | Model trials | Baseline trials | Total | Maximum attempts |
|---|---:|---:|---:|---:|
| Qualification Q | 15 | 0 | 15 | 432 |
| Pilot P | 225 | 105 | 330 | 57,024 |
| Confirmation C | 2,700 | 960 | 3,660 | 632,448 |

The call ceilings include all retries and baseline calls; baselines have no paid
provider exposure. Do not execute duplicate live baseline cohorts or separately
duplicate the full 105/960 offline cohorts. The historical 45-trial development
diagnostic remains a separate bounded diagnostic, not pilot evidence.
The receipt separates total maximum calls from maximum paid-provider attempts:
432 for Q, 38,880 for P and 466,560 for C.

## Reservation worksheet and prices

The public [source record](../configs/campaign_preparation_sources.json) documents
official pages read on **2026-11-16**. OpenAI's
[model page](https://developers.openai.com/api/docs/models/gpt-6-luna.md) and
[pricing page](https://developers.openai.com/api/docs/pricing.md) confirmed standard
short-context input/output rates of $0.10/$0.50 per million tokens, Responses API,
text/image input and structured outputs. The official Gemini model/pricing pages
redirected from `ai.google.dev` to the
[model page](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite) and
[pricing section](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite),
confirming stable model code, text/image input, structured outputs and standard
paid input/output rates of $0.30/$2.50 per million, including output thinking.
This verifies public documentation, not account access, quota or live behavior.
Unknown remote revisions and provider-default sampling/reasoning remain disclosed.
No free-tier, cache-read, batch or flex reduction is assumed. Recheck documentation
before spending; update the public verification record if rates or support changed,
then regenerate. The offline checker does not retrieve current remote documents.

The official [prompt-caching guide](https://developers.openai.com/api/docs/guides/prompt-caching.md)
and model page were rechecked on **2026-11-16**: implicit caching is enabled by
default, and a default 30-minute cache write uses **$0.125/M OpenAI input**. This
is a total input rate, not a surcharge added to $0.10. The adapter does not disable
caching or distinguish write charges, and runtime `Budget` still uses the configured
nominal $0.10/M rate. Thus its local estimate can understate billed cache-write
input. Omitting cache-read discounts does not remove this possible write premium.
Actual cache activity remains unknown; no cache setting, wire option or core billing
feature is changed by preparation.

Each stage also has a separately labeled **all OpenAI input at $0.125/M** scenario,
with Gemini and output rates unchanged. It uses the same request-size envelope,
retry simulation, short-context threshold and upward-rounded 10% margin. For
100,000 OpenAI input plus 1,000 output tokens, nominal arithmetic is **$0.0105**;
all-input-write arithmetic is **$0.013**. Review both scenario exposures and the
known runtime-estimate limitation before approval. Neither scenario is an invoice
ceiling. Configured token prices stay unchanged; the known write-premium scenario
is explicitly included when choosing the actual match/campaign estimate guards.

`Budget.reserve_phase` counts UTF-8 bytes of system rules, `prompt_text()` and the
response schema, adds 2048 framing tokens plus the configured image reserve when
attached, then quotes 4096 output tokens. The preparation tool exercises that real
reservation path and starts/settles every simulated ticket with unknown usage,
retaining its complete quote. This is local accounting simulation, not a provider
request or a game execution. The receipt lists every whole-team phase quote,
including both attempts, for every condition/assignment/turn.

Future player outputs are unknown. The worksheet uses a **dominating size envelope**
rather than just quoting a small initial observation or claiming a simultaneously
reachable maximum state:

- Real own-HUD shapes from the finite catalog, with bounded scalar fields enlarged
  to four ASCII bytes, the longer shared goal, and 12 public events of 128 ASCII
  bytes. Current legal engine event templates are under 100 bytes; roles/action
  kinds are finite, positions/resources bounded, and arbitrary action integers
  are never interpolated into public events.
- Six messages, each 400 maximum-length Unicode characters; each character expands
  to 12 ASCII bytes under JSON escaping. The same maximum is included in each of
  up to four history entries. Withheld inputs omit messages. Smaller phase/arm
  opportunities can be overbounded, never undercounted.
- Each historical action gets an additional 16,384 ASCII bytes of padding, covering
  the entire locally accepted reply limit, including schema-valid huge integer
  parameters. This avoids treating legal action kinds as proof of small numeric
  values. The padding key is worksheet-only and is never a real player input.
- 1000 maximum-length escaped private-note characters after the first turn, 256
  bytes of fixed repair allowance, 8192 image tokens when attached, 4096 output
  tokens per attempt, and the whole phase's retry allowance before any starts.

Sum retained quotes over the full match and take the maximum over all assignments
and arms separately for each pricing scenario. Add 10% and round upward to a cent,
then choose the **maximum of the nominal and write-scenario margin guards** for the
actual spec. The same selected 12-turn guard is frozen for pilot and confirmation. The current
envelope's maximum input quote is 257,400 tokens, under OpenAI's 272K short-context
threshold; the tool refuses preparation if that threshold is reached. The image
reserve and byte heuristic remain local estimates, not a provider tokenizer or
invoice guarantee. New engine templates/protocol/room bounds require reviewing
this derivation as well as regenerating checksums.

With the recorded prices and current code, the **nominal comparison only** has a
two-turn bound of $0.5461948, margin guard $0.61 and Q exposure $9.15. Its 12-turn
bound is $8.2329486, margin guard $9.06, P exposure $2,038.50 and C exposure $24,462.00.
Its largest whole-phase retry quotes are $0.1368122 for Q and $0.2860566 for P/C.
These nominal comparison amounts are not the selected approval guards.

The all-OpenAI-input-write scenario has a two-turn bound of **$0.5836073** and a
12-turn bound of **$8.9529555**. It selects the actual specs' **Mq=$0.65**,
**Q=15Mq=$9.75**, **M=$9.85**, **P=225M=$2,216.25** and **C=2700M=$26,595.00**.
Maximum whole-phase retry quotes are $0.14762535 for Q and $0.31179275 for P/C.
Show the nominal comparison and selected write-scenario amounts with the known
billing-estimate gap, using these selected guards as the spending-approval request.
The guards are **not expected invoices or provider billing ceilings**. Use the
regenerated receipt's numbers if code, inputs or verified prices change.

## Frozen review and separate spending gates

The receipt records source revision/status, complete environment inventory/hash,
catalog hash, frozen-input hash, source-record/profile hashes, spec hashes, all
limits and exposure calculations. It saves sizes and quotes only, without actual
provider prompts, private user data or credentials. Hashes establish consistency,
not authenticity. A dirty preview is useful development output but cannot be the
final spending-review identity.

The generated receipt explicitly leaves `operational_planning` **not_started** and
provider account/quota access **unverified**. A passing cost/hash check does not
complete operational approval. Before any paid request, prepare a separate ignored
approval brief linked to the unchanged receipt hash, covering all of the following:

- Current frozen source/environment/spec hashes and documentation date, both nominal
  and all-input-write exposures, all match/campaign guards, and the independent
  approval requested for Q alone.
- The bounded 45-trial offline development diagnostic's evidence path, elapsed time,
  artifact bytes and trial/call counts; conservative Q duration/storage projections
  with stated assumptions and headroom. Do not duplicate the full pilot/confirmatory
  baseline cohorts to obtain these projections.
- Current disk-free measurement for the actual planned output filesystem and enough
  headroom for projected artifacts. Record timestamp, bytes/units and assumptions;
  do not substitute a historical measurement or leave this check implicit.
- Account/model quota details available from an authorized dashboard, including
  relevant request/token limits and the serial launch/timeout/retry plan. If the
  dashboard is unavailable, report quota and account access as **unverified** in the
  Q approval request. Do not perform live provider queries before Q approval.
- Fresh planned Q candidate/registration/trial/report/progress-log output paths,
  exact intended commands and interpreter, monitoring/checkpoint responsibility,
  and stop/report procedure. Root must populate these concrete values before asking
  for paid-run approval; placeholders and cost calculations do not mark them ready.
- After an approved launch actually starts, immediately record its real PID, start
  time, command/output locations and first checkpoint. PID is **not_started** during
  preparation. For a long-running command that becomes idle, send checkpoints at
  least every ten minutes, reporting elapsed time, observable progress/call/estimate
  totals, output status and any stop or uncertainty. Keep notes sanitized and retain
  partial/stopped evidence rather than relaunching automatically.

The immutable generated receipt records what this offline tool can verify. The
separate approval brief supplies operational observations; do not edit the receipt
to claim them complete. Unfinished operational checks block a ready claim, while
unavailable dashboard/quota facts must remain explicit uncertainties in the approval
request. Qualification is the eventual approved test of remote account/model access.

1. Integrate the latest Phase-1 runtime, replay and dependency-remediation work;
   commit preparation; freeze a clean checkout and environment. Regenerate into a
   fresh ignored directory and run the
   checker with `--require-clean`. Review exact source/environment/input/spec hashes,
   documentation date, numeric Q quotes and all guards before asking for Q spending
   approval. Preserve this receipt alongside the eventual registration for review.
2. Register that exact Q candidate offline with the existing campaign CLI and
   verify its readback and spec/frozen identities against the receipt for concrete
   review. Registration itself does not authorize execution or enlarge exposure.
   Obtain separate explicit **Q spending approval** for the reviewed receipt and
   registration before running that exact registration. Q must
   produce reviewed model/arm compatibility evidence; refusals, invalid outputs,
   failures, stopped trials and omissions remain in the evidence.
3. Review Q and obtain separate explicit **P spending approval** for the concrete
   pilot receipt/registration before any pilot provider calls. Q does not authorize
   P. Any necessary treatment/input changes require regeneration and fresh review.
4. Do **not** register confirmation until a completed eligible pilot exists. Keep
   the entire Git source, environment, roster/prices, provider contracts, catalog,
   prompts, inputs, policies and match settings unchanged from pilot to confirmation.
   Use the existing `register --pilot` eligibility/transition gate. Review the
   concrete C receipt and obtain separate explicit **C spending approval** before
   confirmation calls. Pilot data are never pooled into confirmatory results.

Use the [campaign CLI](CAMPAIGNS.md) for eventual registration, execution and
analysis. Missing/inaccessible approved models or documentation are blockers;
there is no silent model replacement. Preserve stopped/missing trials and one-shot
markers; do not alter a registration or erase evidence to resume a cohort.
