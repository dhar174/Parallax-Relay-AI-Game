# Roadmap

The goal is a reliable research game in which distinct observations and public
communication matter to successful cooperation. This is a proposed sequence with
completion gates, not a dated release commitment. The current implementation is
Milestone 2: one fixed room, three roles, offline-tested infrastructure, and no
verified real-model match.

Findings referenced below are in [Review](docs/REVIEW.md). Priorities describe impact
and dependencies; optional mechanics are not automatically defects.

## 1. Documented baseline

**Status:** documentation delivered in the current working changes; runtime findings
remain open.

Establish reproducible onboarding, explain current contracts and limitations, and
provide compact coding-agent guidance. Preserve original milestone evidence while
separating it from fresh review results.

**Completion gate:** the offline quickstart and fast mode produce the expected
seven-turn fixtures; documentation links and commands are checked; each finding
has source evidence, a classification, a proposed remedy, and an acceptance test.
Browser and security-scan limitations must remain explicit, not implied successes.

## 2. Reliable execution

**Status:** proposed. Depends on the documented baseline.

Resolve local error handling and output recovery (R01, R03), mock cost semantics
(R02), and the non-MOVE contract mismatch (R04). Decide and enforce safe legacy-demo
output behavior (R05). Verify each provider's exact endpoint and schema contract,
then perform explicitly authorized, bounded live smoke tests (R06).

Add offline CI, supported Python/platform checks, and a reproducible development
dependency strategy (R09). Include retry/cancellation, partial usage, malformed
responses, output failures, and privacy regressions in the relevant tests.

**Completion gate:** reproduced defects have regression tests; the full offline
suite and mock runs pass in the declared supported matrix; provider references
match wire tests; every claimed live-compatible provider/model has dated smoke-test
evidence. Live results identify errors and token usage without publishing secrets.
Document remaining limitations rather than silently switching models or contracts.

## 3. Reproducible evaluation

**Status:** proposed. Depends on reliable execution.

Add run provenance and an experiment runner (R08), recording source/configuration,
prompt/schema/room versions, dependency environment, model identifiers, trial IDs,
and sampling settings where supported. Store no credentials. A seed may describe
room generation or a supported provider option; it cannot promise deterministic
model output.

Define evaluation protocols before making comparative claims (R07): repeated trials,
provider-to-role rotations, scripted and simple policy baselines, communication
ablations, and observation ablations. The current `--fast` mode reduces communication
but does not disable it. Account separately for victories, defeats, incomplete runs,
invalid outputs, reliability failures, usage, latency, and estimated cost.

**Completion gate:** another researcher can reconstruct experiment configuration and
aggregate results from saved artifacts; the runner enforces a campaign budget;
results include denominators, uncertainty, role assignments, and all stop reasons.
Publish no claim of causal communication benefit without a controlled comparison.

## 4. Meaningful cooperative challenges

**Status:** proposed. Depends on the evaluation protocol.

Introduce explicit room definitions and variants whose hidden facts, resource
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
