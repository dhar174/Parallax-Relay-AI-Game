# Roadmap

The goal is a reliable research game in which distinct observations and public
communication matter to successful cooperation. This is a proposed sequence with
completion gates, not a dated release commitment. The current implementation is
Milestone 2: one fixed room, three roles, offline-tested infrastructure, and no
verified real-model match.

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
Credentialed provider validation (R06) and source/privacy and dependency/license audits (#23/#24) remain
open. See the verification guide for actual hosted results.

Local error handling/output recovery (R01, R03), mock cost semantics (R02), the
non-MOVE contract (R04), and safe legacy-demo outputs (R05) have regression coverage.
The dated API audit checks the three existing endpoint/schema contracts. Next
select compatible models and perform explicitly authorized, bounded live smoke
tests (#14–#16/R06); no shortlist or billable execution is supplied by that audit.
Slice 7 adds a separate dated smoke profile, single-invocation helper, native
artifact verifier and matching workbench preset. The selected roster is two
independent OpenAI agents and one Gemini agent; characters and abilities are
unchanged. Anthropic #15 is deferred because credits were unavailable. Live
acceptance still requires actual evidence; see the verification record. PR #33
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

## 3. Reproducible evaluation

**Status:** partly implemented. Slice 5 adds versioned run provenance (#10);
the prospective evaluation protocol (#17) is specified. Controls/baselines (#18),
the experiment runner (#19) and controlled campaigns remain future work.

Run provenance (R08) now records source/configuration,
prompt/schema/room versions, dependency environment, model identifiers, trial IDs,
and sampling settings where supported. Store no credentials. A seed may describe
room generation or a supported provider option; it cannot promise deterministic
model output. See [Run provenance](docs/PROVENANCE.md). The experiment runner must
still schedule/aggregate trials and preserve setup failures and missing artifacts.

[Evaluation protocol v1](docs/EVALUATION.md) specifies repeated trials, balanced
role assignments, policy baselines and five comparison arms. Its selected design
is 5 pilot plus 30 confirmatory trials per unique assignment/condition/room, with
all-trial denominators, uncertainty and campaign budgets. The current `--fast`
mode reduces communication but does not disable it; the other controls and campaign
machinery still need implementation. No experimental results are claimed.

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
