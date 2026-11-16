# Roadmap

The goal is a reliable research game in which distinct observations and public
communication matter to successful cooperation. This is a proposed sequence with
completion gates, not a dated release commitment. The current implementation is
Milestone 2: one fixed room, three roles, offline-tested infrastructure, and one
verified bounded live turn. A full real-model victory and benchmark results remain
unverified.

Findings referenced below are in [Review](docs/REVIEW.md). Priorities describe impact
and dependencies; optional mechanics are not automatically defects.

## 1. Documented baseline

**Status:** documentation delivered in PR #1.

Establish reproducible onboarding, explain current contracts and limitations, and
provide compact coding-agent guidance. Preserve original milestone evidence while
separating it from fresh review results.

**Completion gate:** the offline quickstart and fast mode produce the expected
seven-turn fixtures; documentation links and commands are checked; each finding
has source evidence, a classification, a proposed remedy, and an acceptance test.
Browser and security-scan limitations must remain explicit, not implied successes.

## 2. Reliable execution

**Status:** partially implemented. Slice 1 delivered R01/R04/R05 in PR #27,
slice 2 delivered R02 in PR #28, and slice 3 delivered R03 in PR #29. Slice 4's
CI/lock work (#21/#22) was delivered in merged PR #30. Slice 6's independent
provider-contract audit (#13) adds source-backed offline coverage and corrections;
PR #32 review adds adversarial-envelope, retry, cleanup and priced-driver regressions.
R06 has bounded live evidence for the selected OpenAI/Gemini roster and an explicit
Anthropic scope exception; #14/#16/#8 are closed completed and #15 not planned. Source/privacy
and dependency/license audits (#23/#24) remain open. See the verification guide for
actual results.

Local error handling/output recovery (R01, R03), mock cost semantics (R02), the
non-MOVE contract (R04), and safe legacy-demo outputs (R05) have regression coverage.
The dated API audit checks the three existing endpoint/schema contracts; the
offline audit itself supplies neither live evidence nor spending authorization.
Slice 7 adds a separate dated smoke profile, single-invocation helper, native
artifact verifier and matching workbench preset. The selected roster is two
independent OpenAI agents and one Gemini agent; characters and abilities are
unchanged. The initial attempt was blocked by six Gemini HTTP 429 failures; its
historical evidence is preserved. A separately authorized retry on clean `d76be6c`
completed all nine requests on their first attempts, resolved one turn, and stopped
at `turn_limit` with no final score. The [acceptance record](docs/VERIFICATION.md#provider-acceptance-and-scope-decision--november-15-2026)
records #14/#16/#8 completed for revised scope and #15 retired as not planned
(not live-verified) after merged PR #38. Anthropic remains implemented,
tested offline and live-unverified; ordinary defaults are unchanged. PR #33
supplies the static workbench and mock-only companion; general release automation
#34 and comprehensive browser coverage #35 remain separate.

Offline CI, the focused Python/platform matrix, and reproducible dependencies
(R09) are covered by PR #30. Its suite includes retry/cancellation, partial usage,
malformed responses, output failures, and privacy regressions. The separate audits
remain required before closing R09's parent #11.

**Completion gate:** reproduced defects have regression tests; the full offline
suite and mock runs pass in the declared supported matrix; provider references
match wire tests; every claimed live-compatible provider/model has dated smoke-test
evidence. Live results identify errors and token usage without publishing secrets.
Document remaining limitations rather than silently switching models or contracts.

### Provider and model extensibility

**Status:** future work, tracked by [#37](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/37).
The direction is any combination of supported APIs and model types per role,
starting with the existing OpenAI, Anthropic and Gemini adapters. All 27 provider
assignments across three roles validate and resolve offline, including repeated
providers; only the dated live roster has the recorded live evidence.

Separate transport/API implementation, model identity/capabilities and game-role
behavior before adding hosted/local APIs. Design explicit observation and response
bridges for text-only, image, audio, video and non-chat models. Preserve role-local
inputs, sealed commitments, budgets, provenance and authoritative engine actions;
never silently drop unsupported inputs or substitute spectator information.

Distinguish declared capabilities, offline-tested behavior, dated bounded live
verification, unverified combinations and inputs unsupported by the current
contract. Evidence identifies the exact API/version, model/known revision, role
assignment, input/output contract, limits and date. Neither a provider-wide claim
nor exhaustive Cartesian-product coverage follows from one successful roster.
Coordinate observation ablations with #18, campaigns with #19 and rooms with #20.
New modalities/adapters require separately reviewed slices and spending approval;
this roadmap introduces no runtime feature, automatic fallback or paid execution.

## 3. Reproducible evaluation

**Status:** partly implemented. Slice 5 adds versioned run provenance (#10);
the prospective evaluation protocol (#17) is specified. Slice 8 controls/baselines (#18) implement the five protocol arms and WAIT/uniform-v1
policies. Slice 8 also adds campaign registration, a bounded serial trial runner
and JSON/CSV aggregation (#19). Controlled model campaigns remain unrun.

Run provenance (R08) now records source/configuration,
prompt/schema/room versions, dependency environment, model identifiers, trial IDs,
and sampling settings where supported. Store no credentials. A seed may describe
room generation or a supported provider option; it cannot promise deterministic
model output. See [Run provenance](docs/PROVENANCE.md). The [campaign runner](docs/CAMPAIGNS.md) schedules/aggregates trials and preserves
setup failures and missing artifacts.

[Evaluation protocol v1](docs/EVALUATION.md) specifies repeated trials, balanced
role assignments, policy baselines and five comparison arms. Its selected design
is 5 pilot plus 30 confirmatory trials per unique assignment/condition/room, with
all-trial denominators, uncertainty and campaign budgets. The current `--fast`
mode reduces communication but does not disable it; the five explicit controls and campaign
machinery now exist. No experimental results are claimed.

**Completion gate:** another researcher can reconstruct experiment configuration and
aggregate results from saved artifacts; the runner enforces a campaign budget;
results include denominators, uncertainty, role assignments, and all stop reasons.
Publish no claim of causal communication benefit without a controlled comparison.

## 4. Meaningful cooperative challenges

**Status:** issue #20 implementation adds nine curated rooms and enforced
development/held-out workflow; empirical comparison remains gated by eligible
campaigns. See [catalog](docs/ROOMS.md).

Implemented explicit room definitions and variants whose hidden facts, resource
choices, or compatible/competing objectives require different plans (R07). Preserve
engine authority and role-specific observations. Separate development rooms from
held-out evaluation rooms and retain a solvability oracle or scripted baseline for
each supported variant.

**Completion gate:** validated room variants are solvable, their hidden-state
projections pass privacy tests, and evaluations distinguish observation/communication
conditions from memorized fixed scripts. Difficulty claims must identify the room
set and evidence; incompatible objectives require an explicit scoring design.

## 5. Later exploration

**Status:** deferred until earlier gates justify expansion.

Improve replay accessibility and unfinished-run inspection (R10). Consider a live
spectator interface, additional roles including ECHO, richer mechanics, or deployment
only through separate proposals that state their effect on reproducibility and
information boundaries.

**Completion gate for starting a proposal:** describe the intended user, concrete
problem, maintenance cost, security boundary changes, and success criteria. These
items are not scheduled deliverables of the current documentation work.
