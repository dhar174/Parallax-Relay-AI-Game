# Contributing

Start with the [README](README.md), [architecture](docs/ARCHITECTURE.md), and
[review](docs/REVIEW.md). Work against the current implementation, and distinguish
bug fixes from roadmap features. A scripted victory proves infrastructure and room
solvability, not model intelligence.

## Environment

Use Python 3.11+ and a local virtual environment as shown in the README. Install
`requirements.txt`; it expresses supported direct-dependency ranges.
`requirements-tested.txt` records the original milestone's three direct versions,
not a complete dependency lockfile. The [verification record](docs/VERIFICATION.md)
lists environments actually exercised. Do not imply all Python versions or operating
systems have been tested.

Run commands from the repository root with the environment activated:

```bash
python -m pip check
python -m unittest discover -s tests -v
python -m compileall -q parallax_relay tests
python -m parallax_relay.play --mock
python -m parallax_relay.play --mock --fast
```

The main launcher chooses a unique output directory when `--out` is omitted.
Default and fast mock matches should win in seven turns, with 63 and 42 scripted
calls respectively. They should both finish with five energy and scores of 100.

For a focused module, use discovery rather than assuming `tests` is a package:

```bash
python -m unittest discover -s tests -p 'test_protocol.py' -v
```

## Making a change

Use a focused branch and explain the behavior being changed. For a bug fix,
reproduce the trigger and add a meaningful regression test before changing code.
Run focused tests while working and the full offline suite before delivery. Do not
introduce tests that merely restate implementation details or rewrite generated
fixtures for unrelated changes.

Use `httpx.MockTransport` for provider tests. Check serialized requests, response
handling, retries, and usage accounting. Synthetic responses must not be presented
as proof of remote API compatibility. Live testing needs explicit authorization,
local credentials, a selected model for each provider, and a bounded run.

Preserve the engine's deterministic action resolution and player information
boundaries. When changing schemas, defaults, stop reasons, CLI behavior, or output
formats, update the relevant protocol/running documentation and affected tests.
Changing a provider contract also requires dated source evidence in the API guide.

## Fixtures and review evidence

`example_run/` and `demo_output/` are committed historical fixtures with accompanying
PNGs. Generate new development runs under ignored `runs/` or a temporary directory.
The legacy demo overwrites files in an existing destination; always give it a fresh
path, never the committed `demo_output/` directory for routine verification.

Historical milestone plans and red/green logs document earlier work. They are not
current instructions or fresh verification. Add dated evidence rather than rewriting
those logs. Report the exact environment, commands, results, and untested areas.

Do not commit API keys, populated environment files, virtual environments, caches,
or unrelated run output. `.env.example` is a blank template. Read the
[running guide](docs/RUNNING.md) before sharing privileged spectator logs.

Before handing off, inspect `git diff --check`, the changed-file list, and the
relevant documentation links. Describe the problem, final behavior, verification,
and any remaining limitations. No CI workflow is currently configured, so local
checks are the available automated evidence.
