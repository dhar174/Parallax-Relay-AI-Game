# Verification record

Original milestone release date: November 12, 2026.

The original evidence below is historical. See the dated repository import and
documentation-review sections for subsequent checks. A passed offline suite does
not establish live model compatibility or browser behavior in a new environment.

## Original milestone evidence summary

| Check | Result |
|---|---|
| Full unittest suite | 72 tests passed |
| Original engine regression tests | All 6 retained and passed |
| Default orchestrator scripted match | Victory, 7 turns, 63 scripted calls, energy 5 |
| Fast-mode scripted match | Victory, 7 turns, 42 scripted calls |
| Real adapter serialization + synthetic HTTP + engine | Victory; 64 intercepted requests including one HTTP 429 retry |
| Original standalone demo | Victory, 7 turns, all three scores 100 |
| Python compilation | Passed |
| Replay page title and meaningful content | Passed in Chromium |
| Replay next/previous controls | Round 1 -> Round 2 -> Round 1 passed |
| Mobile horizontal overflow at 390px | None observed |
| Empty/interrupted-run controls | Hidden correctly after CSS fix |
| Browser JavaScript runtime errors | None in final checks |
| Credentialed API calls / real LLM match | **Not run** |

Offline infrastructure tests cannot establish remote model availability, image
understanding, real cooperation, output reliability, provider billing, or gameplay
success. The fixture's seven-turn win is evidence about the host infrastructure and
room solvability, not model intelligence.

## Environment and methods

Python 3.13.5 on Linux; Pillow 12.3.0, Pydantic 2.13.5, httpx 0.28.1. The code targets
Python 3.11+; Windows and other Python versions were not executed here.

Tests use `unittest` and actual code paths. Provider tests intercept HTTP with
`httpx.MockTransport`: requests are serialized by the shipping adapters and responses
use synthetic provider envelopes. The integration test runs those adapters through
the complete orchestrator and deterministic engine, including a single simulated
rate-limit response and usage accounting. It also checks no API key enters prompt
bodies or output logs, and no role's private notes enter another's request.

Concurrency tests synchronize tasks to verify phase barriers, not simply request
counts. Visibility tests mutate hidden state and compare rendered sensor pixels;
these complement HUD/history/event assertions. They are not an exhaustive proof
against every future rendering change.

The browser flow tested was replay load -> next/previous round -> updated sensor/chat
content, plus empty-run and mobile states. Playwright with local Chromium was used.
The Browser plugin's browser skill was not available in the listed skill context.
The container Chromium policy blocked file:// and localhost navigation. For browser
QA only, the generated HTML was loaded through `set_content` and local PNG references
were replaced with inline PNG data. No browser policy was modified. The shipping
viewer retains local relative PNG paths. Direct file navigation therefore remains
untested in this environment; corresponding files and reference names were checked.

Screenshots and browser-check script were kept outside the source project. No browser
automation dependency is required for ordinary project use or the unittest suite.

## Review and corrections

This was an author self-review; no independent reviewer or subagent reviewed the code.
The review checked contracts, isolation, budgets, failure handling, logs and run modes.

Corrections verified during development:

- Exact motor heat leaked through the starter's public event text. Public event
  filtering now strips that value while the authorized thermal image retains it.
- Static collect instructions disclosed hidden item coordinates. They now direct
  players to sensors or teammates.
- The previous render contained a misleading static hot-span label with no simulated
  hazard. It was removed; the actual motor heat is legible in the thermal view.
- An empty replay's `hidden` controls were overridden by flexbox CSS. A browser test
  reproduced it; an explicit hidden rule fixed it, and the browser check passed.
- A non-UTF-8 environment file caused an uncaught decoding traceback. A failing CLI
  regression test preceded the fix; it now returns a sanitized configuration error.

Known minor presentation limitation: the omniscient motor/console labels can be
crowded where the robots overlap. This does not change player-specific observations
or physics; visual-art polish is deferred.

## Scope decisions

The supplied one-lane, three-player engine is preserved. No 2/4-player balance,
playable temporal role, full platformer, difficult competing-goal campaign or live web
interface is claimed. Direct httpx REST adapters were selected instead of SDKs because
they keep the shipped dependency set small and enable exact offline wire tests. This
requires maintaining the payload mappings when provider contracts change.

Credentialed calls were deliberately not performed. The provided live launcher must
first be exercised with a bounded one-round smoke test on the user's machine.
Spending controls include a hard request count and an optional local dollar estimate,
not a hard provider-enforced monetary ceiling.

## Reproduce

```bash
python -m unittest discover -s tests -v
python -m compileall -q parallax_relay tests
python -m parallax_relay.play --mock --out runs/verification-normal
python -m parallax_relay.play --mock --fast --out runs/verification-fast
python -m parallax_relay.demo --out runs/verification-legacy-01
```

Use new output directories. Historical red/green test logs are in `docs/verification/`.
They record the test-first implementation sequence and are not the final test status.
The original milestone's final test output is `docs/verification/final-tests.txt`.
It is not a log of the later repository review.

## Repository import verification — November 13, 2026

Imported all 117 files from `parallax-relay-milestone2.zip` into the repository
root, removing only the archive's enclosing directory. Retained the repository's
MIT license and the supplied demo recordings and historical verification logs.
Updated the README with GitHub clone instructions and a fuller project map, and
extended `.gitignore` for local build and editor artifacts. Game code is unchanged.

Fresh checks on Linux with Python 3.12.14, Pillow 12.3.0, Pydantic 2.14.3 and
httpx 0.28.1 (installed from `requirements.txt`):

- `python -m unittest discover -s tests -v`: all 72 tests passed.
- `python -m parallax_relay.play --mock --quiet --out runs/import-check`:
  victory in seven turns, 63 scripted calls, all scores 100, energy 5.
- `python -m parallax_relay.demo --out runs/import-demo`:
  victory in seven turns, all scores 100, energy 5.
- `python -m pip check`: no broken requirements.

The virtual environment and newly generated runs are ignored. Browser checks and
credentialed provider calls were not rerun for this import; the earlier browser
results above describe the supplied milestone's verification.

## Documentation review — November 13, 2026

Runtime baseline: `719c7696c4bfe50934fc936bbccfb62812633164`. Linux/Python 3.12.14;
Pillow 12.3.0, Pydantic 2.14.3, httpx 0.28.1. Existing virtual-environment dependencies
were used without changing requirement files. All new run output is ignored.

| Check | Fresh result |
|---|---|
| Full unittest discovery | 72 tests passed |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q parallax_relay tests` | Passed |
| Default mock | Victory, 7 turns, 63 calls, all scores 100, energy 5 |
| Fast mock | Victory, 7 turns, 42 calls, all scores 100, energy 5 |
| One-turn mock | `turn_limit`, 1 turn, 9 calls, no terminal score |
| Legacy demo in fresh directory | Victory, 7 turns, all scores 100, energy 5 |
| Local configuration check with fake values | Exit 0; no credential sentinel in output |
| Zero-turn call-budget stop | Exit 4, no calls, final PNG and HTML present |
| Published review reproduction snippets | Matched recorded results for R01, R02, R03 |
| Retry-sleep cancellation probe | `cancelled`, three logged calls, final result preserved |
| Partial usage reservation probe | Quote retained; unknown count 1; reservations released |
| Malformed Gemini envelope probe | Retryable `invalid_provider_response` |
| Existing/generated replay static checks | PNG references present and valid; no external script sources |
| Markdown local links and anchors | Passed |

The mock commands used fresh destinations under `runs/docs-review-*`; omit `--out`
for repeatable verification without directory collisions. No committed example was
regenerated. The review's Python snippets are standalone reproductions, not passing
regressions for fixes; the defects remain present.

### Limits and tools

The source/doc review used Plugin Management discovery, execution/debugging/
verification guidance, and prose editing. Context7 retrieved excerpts from official
provider documentation and the Anthropic SDK for independent contract checks.
[API sources](API_SOURCES.md) records the specific evidence and its limits.

A standard Codex Security scan was attempted at setup, but its required preflight
reference could not be retrieved and no scan host tool was available. No scanner
preflight completed and no scanner report was produced. Security observations in
[Review](REVIEW.md) are source-review observations, not a substitute certification.
Browser skill discovery found no browser-control or cloud-browser tool. Therefore
no new browser navigation, mobile layout, visual inspection, or accessibility
result is claimed. Static checks and historical browser results are distinct.

Credentialed provider calls, live model quality, billing reconciliation, cross-OS
execution, and a dependency vulnerability audit remain untested. Documentation
changes do not fix the runtime findings listed in Review.

A fresh documentation reviewer checked the guides and source-backed findings, found
no blocking issue, and requested reconciliation of this verification record. That
reconciliation is included here. This was a documentation review, not an independent
security audit or provider compatibility test.

## Slice 1 implementation — November 13, 2026

Linux/Python 3.12.14, using the existing virtual environment and dependency versions
recorded above. Historical reproduction outputs remain baseline evidence.

- R01: the loader and subprocess encoding regressions failed before the fix
  (UnicodeDecodeError / exit 1), then the full offline suite passed: 75 tests.
  Invalid syntax/fields remain sanitized; invalid UTF-8 now exits 2 without creating
  output or exposing the test sentinel.
- R04: engine subcases and a one-turn orchestration regression failed before the
  guard (invalid VENT still cooled the motor), then all 80 tests passed. The
  regressions cover signed/nonzero fields on every non-MOVE kind, both collectors,
  canonical effects, input purity, teammate controls/order, parser acceptance,
  nine successful attempts without repair, and the unmodified recorded commitment.
- R05: new direct/CLI tests failed before the fix on overwrite, missing replay-path
  output, unique defaults, and local error handling. After the fix, all 88 offline
  tests passed. Empty/populated directories, files, and supported symlinks remain
  untouched; new/nested destinations retain seven-turn results and 28 valid PNGs;
  two default runs create distinct folders and preserve old demo_output evidence.
- Final checks: `pip check` found no broken requirements; compilation and diff
  whitespace checks passed. Standalone default/fast mock CLIs won in seven turns
  with 63/42 calls, five energy and all scores 100; the no-argument demo also won
  and printed its unique replay path. Generated runs are ignored.
- A fresh code reviewer found no actionable issue and independently ran the full
  suite: 88 tests passed. No dependency, historical fixture, or provider contract
  changed; no live requests or new browser verification were performed.

Issues R01/R04/R05 are implemented on the slice 1 branch and await merge; R02/R03
and the remaining research/validation work remain open. Existing historical logs
and baseline reproduction outputs above were preserved rather than regenerated.

### PR #27 review follow-up — November 13, 2026

Checked the actual PR branch for every point in comment `6859687556`. The existing
implementation already preserves unknown-action diagnostics, sorts parameter
validation by role, creates missing output parents exclusively, and propagates
CLI exit 2 through `SystemExit(main())`. No production behavior change was needed.

Added three targeted regressions: unknown `FLY` commands with nonzero parameters
retain their distinct diagnostic; all six action-map permutations emit identical
public invalid-parameter events under different private heat values; and a real
subprocess filesystem failure (a parent path is a file) exits 2 without traceback
or sentinel disclosure. Existing tests cover missing `runs/`, fresh nested paths,
existing paths, canonical actions, original commitments, and no-retry behavior.

Fresh `python -m unittest discover -s tests -q`: **91 tests passed** on the same
Linux/Python 3.12 environment. The run emitted asyncio slow-task diagnostics but
no test failures or errors. `git diff --check` passed. The suite uses unittest;
pytest is not required. Historical fixtures and dependencies remain unchanged.

## Slice 2 implementation — November 13, 2026

Baseline: merged slice 1 (`a95acc7`). Linux/Python 3.12.14 with the existing
Pillow 12.3.0, Pydantic 2.14.3, and httpx 0.28.1 environment.

The new CLI regression first reproduced exit 4 / `spend_budget` / zero calls with
a $0.001 cap and complete test pricing (input 1/output 2 per million for each role).
After the CLI-only settings copy, the full offline suite passed: **99 tests**.

Verified scenarios include normal/fast priced mock victories (63/42 calls), zero
reported usage/cost, requested/effective manifest settings after CLI overrides,
unchanged source configuration, no provider construction or environment-file read,
turn/call limits, null estimates with absent/partial pricing, and rejection of
invalid requested configuration. Synthetic live execution and direct scripted or
arbitrary programmatic agents retain the cap and stop before responding. Partial
usage retains its estimate and releases the remaining reservations.

`python -m pip check` found no broken requirements; compilation and diff whitespace
checks passed. Standalone normal/fast mock CLIs also won in seven turns with five
energy, scores of 100, and 63/42 calls; their unpriced estimates remain null and
requested/effective settings match. Checked 37 local documentation links/anchors.

A fresh reviewer found no actionable issues and independently passed all seven mock
CLI tests and six budget tests. Shared budget/orchestrator/config/provider code,
historical fixtures, and dependencies remain unchanged. No paid provider requests
or new browser checks were performed. Issue #4 awaits merge; recording recovery
remains slice 3 work. The old programmatic R02 probe intentionally still stops at
its configured cap and is not a reproduction of the fixed CLI-only policy.

### PR #28 pre-merge review — November 13, 2026

The review requested confirmation that `--check` never applies the mock override.
Source inspection confirms it returns before `_run`, where the override lives.
Added a regression using a valid tiny-cap priced configuration and fake credentials:
`--check` returns 0, retains the requested cap/configuration, creates no run output,
constructs no provider, and never starts the match driver. Requested-settings
metadata is still mock-only; existing live and mock manifest tests cover that rule.

Fresh full unittest discovery: **100 tests passed**. The run emitted asyncio
slow-task diagnostics but no failures/errors; diff checks passed. No production
behavior change or live provider request was needed for this review follow-up.

## Slice 3 implementation — November 13, 2026

Baseline: merged slice 2 (`e6c3576`), Linux/Python 3.12.14 and the existing dependency
environment. The first regression reproduced raw OSError escaping after a phase
write; the old path produced no final summary/viewer. Recovery now raises sanitized
MatchExecutionError with a partial result and original exception for trusted callers.

Fresh full suite after implementation and review corrections: **111 tests passed**.
Fault-injection cases cover call/phase/turn/observation writes before, after, and
partway through persistence; progress and unexpected driver errors; each of seven
final artifacts; persistent/secondary failures; a transient finalization failure
after victory; cancellation with failed logging/finalization; sibling draining and
released reservations; CLI status/privacy/current-viewer reporting; client-close
timeout; and fresh cancellation during failed-match client cleanup. The last case
was found in independent review, reproduced red, fixed to propagate cancellation,
then verified with the green full suite. No other actionable review finding remained.

Finalization is capped at two passes, each independently attempting seven atomic
artifacts. The resolved world, in-memory records, recovered JSONL, summary, final
state and embedded replay agree. Cancellation-resistant Python code and blocking
filesystem calls remain outside the cooperative/bounded-attempt guarantee.

`pip check`, compilation, diff checks, and 35 local documentation links passed.
Standalone normal/fast mocks retained seven-turn wins, 63/42 calls, five energy,
and scores of 100. Existing provider-stop, cancellation, privacy, budget and mock
cost-policy tests passed. Some tests emitted asyncio slow-task diagnostics without
failures/errors. Historical fixtures and dependency files remain unchanged. No
paid requests, replay UI expansion, or browser verification were included.

### PR #29 pre-merge review — November 13, 2026

Checked the review's atomic final-artifact, error-hygiene, and bounded-shutdown
concerns against the current source. PNG and HTML finalization both use the shared
temporary-file/replace helper. Added a regression that interrupts each temporary
write halfway: existing final bytes remain unchanged, failed HTML is not marked
current, the aggregated public exception is sanitized, and persisted metadata
contains no exception sentinel. Existing CLI fault and shutdown-timeout tests
verify that local failure status survives slow teardown and raw errors stay private.

Fresh full unittest discovery: **112 tests passed**, with an asyncio slow-task
diagnostic and no failures/errors. Diff checks passed. The review required no
production behavior correction; this follow-up adds explicit atomicity evidence.

## Slice 4 dependency checkpoint — November 14, 2026

Baseline: merged slice 3 (`cda9220`). Fresh Linux x86_64/glibc 2.41 environments
used Python **3.11.18** and **3.12.14**, with pip **26.3**. uv **0.13.6** generated
the universal Python-3.11-minimum lock, with 12 pinned distributions and 247 SHA-256
entries. No compatibility ranges or historical direct pins were changed.

Both installations used `--require-hashes --only-binary=:all:` with
`-r requirements-dev.lock -r requirements.txt`. Their installed inventories matched
all 12 pins (apart from the separately pinned pip bootstrap):

```text
annotated-types==0.8.0
anyio==4.16.0
certifi==2026.10.23
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.20
pillow==12.3.0
pydantic==2.14.3
pydantic-core==2.50.4
typing-extensions==4.16.0
typing-inspection==0.4.5
```

At this dependency checkpoint both interpreters passed the existing **112 tests**,
`pip check`, and compilation. Normal/fast mock results were checked for exit 0,
victory in seven turns, 63/42 calls, five energy, and every score 100. A dry-run
installation with conflicting httpx requirements failed with `ResolutionImpossible`;
removing the httpx lock entry failed the hash-mode exact-pin requirement. Both
negative cases returned exit 1 as required.

Hosted matrix evidence and the completed smoke-checker suite follow separately.
This checkpoint does not establish Windows/macOS support or complete R09's audits.

## Slice 4 CI and smoke checks — November 14, 2026

The checker tests first failed because the helper was absent (three expected
failures), then passed after implementation. They cover both modes, current
interpreter use, credential stripping, fresh destinations, cleanup on success and
failure, subprocess failure/timeout/launch errors, missing/malformed JSON, wrong
call counts, incomplete outcomes, and missing role scores.

Fresh complete discovery passed **115 tests** on both Linux/Python 3.11.18 and
3.12.14 with the locked inventories above. Both real CLI modes also passed their
explicit outcome checks. Compilation includes the new scripts directory. Local
workflow validation passed with actionlint 1.7.12 after correcting YAML quoting
around pip's binary-only option. `pip check` and diff whitespace checks passed.

The workflow targets Ubuntu 24.04/Python 3.11–3.13, Windows Server 2022/Python 3.12,
macOS 15/Python 3.12, and a separate Ubuntu/Python 3.12 range-resolution job. The
action release commits are pinned and no provider credentials are configured.
The [initial PR run](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/43563157911)
passed the four Linux jobs and macOS, each with 115 tests and the asserted mocks.
Windows installed the lock successfully but reported 16 decoding errors in tests
that read UTF-8 HTML with the Windows cp1252 default, plus one legacy-demo assertion:
Windows can raise `FileExistsError` for a nonexistent destination below a file.

Tests now read recording artifacts explicitly as UTF-8. The demo checks the
destination with `lstat` before choosing its existing-path message; parent-file
failures retain the sanitized local-file error and exit 2. An injected Windows
error regression failed before this correction and passed afterward. The complete
**116-test** suite passed on Linux/Python 3.11 and on 3.12 with cp1252 emulation for
unspecified pathlib text encodings. No assertions were relaxed or tests skipped.

The initial logs also exposed preinstalled runner packages, so each revised job
creates a fresh virtual environment and bootstraps pip 26.3 into it. The exact
workflow bootstrap was exercised locally and produced only pip before project
installation. An additional fresh Linux/Python 3.12 range installation passed
115 tests, compilation, and both asserted mocks before the portability correction.
Hosted verification of the revised jobs is pending. Historical fixtures and their
PNGs remain unchanged; no private run artifacts are published.
