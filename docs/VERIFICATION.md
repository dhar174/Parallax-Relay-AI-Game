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
