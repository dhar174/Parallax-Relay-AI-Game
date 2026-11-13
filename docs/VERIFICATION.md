# Milestone 2 verification

Release date: November 12, 2026.

## Evidence summary

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
python -m parallax_relay.demo --out demo_output
```

Use new output directories. Historical red/green test logs are in `docs/verification/`.
They record the test-first implementation sequence and are not the final test status.
The final fresh test output is `docs/verification/final-tests.txt`.

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
