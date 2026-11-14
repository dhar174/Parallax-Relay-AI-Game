# Contributing

Start with the [README](README.md), [architecture](docs/ARCHITECTURE.md), and
[review](docs/REVIEW.md). Work against the current implementation, and distinguish
bug fixes from roadmap features. A scripted victory proves infrastructure and room
solvability, not model intelligence.

## Environment

Use Python 3.12 by default (minimum 3.11) and a fresh local virtual environment as
shown in the README. Bootstrap pip 26.3, then install with:

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements-dev.lock -r requirements.txt
```

`requirements-dev.lock` is a complete, hashed verification set, including transitive
runtime dependencies. It uses universal resolution from Python 3.11 upward; its
portability is established only for environments actually exercised. Both files
are supplied to installation so incompatible ranges or missing pins fail rather
than silently resolving a different environment. Binary wheels are required.
`requirements.txt` retains direct compatibility ranges. `requirements-tested.txt`
preserves the original milestone's three direct versions and is not a lockfile.
The [verification record](docs/VERIFICATION.md) records actual environments.

### Updating the lock

Use uv **0.13.6** as a development-only generator, installed in a separate tooling
environment (for example `python -m pip install uv==0.13.6` there). uv is not needed
to install the lock or run the game. From the checkout root:

```bash
uv pip compile requirements.txt --universal --generate-hashes --python-version 3.11 --no-header --no-annotate --upgrade --output-file requirements-dev.lock
```

Use `--upgrade` to refresh an existing lock; omit it for the initial generation.
Review every version/marker/hash change and confirm direct versions stay within
the compatibility ranges. Install in fresh environments with pip 26.3 and run all
checks below before accepting the change. Record the generator version, exact
installed inventory, Python/OS, commands, results, and limitations in a dated
verification entry. Preserve the historical direct-version file. Coordinate audit
findings with the exact locked versions; generation alone is not a security audit.

Run commands from the repository root with the environment activated:

```bash
python -m pip check
python -m unittest discover -s tests -v
python -m compileall -q parallax_relay tests scripts
python -m parallax_relay.play --mock
python -m parallax_relay.play --mock --fast
python scripts/check_mock_runs.py
```

The main launcher chooses a unique output directory when `--out` is omitted.
Default and fast mock matches should win in seven turns, with 63 and 42 scripted
calls respectively. They should both finish with five energy and scores of 100.

For a focused module, use discovery rather than assuming `tests` is a package:

```bash
python -m unittest discover -s tests -p 'test_protocol.py' -v
```

## Supported environments and CI

The focused support targets are:

| GitHub-hosted operating system | Python | Dependency set |
|---|---|---|
| Ubuntu 24.04 | 3.11, 3.12, 3.13 | Locked |
| Windows Server 2022 | 3.12 | Locked |
| macOS 15 | 3.12 | Locked |
| Ubuntu 24.04 | 3.12 | Fresh compatibility-range resolution |

Support is limited to successful matrix combinations recorded in the
[verification record](docs/VERIFICATION.md#slice-4-ci-and-smoke-checks--november-14-2026).
Newer Python versions, other OS/version combinations,
architectures outside the runners' reported architecture, and WSL are unverified.
Python 3.11 is the minimum, not a promise that all later releases work.

The [offline workflow](.github/workflows/offline.yml) runs on pull requests, pushes
to `main`, and manual dispatch. Each of its six jobs checks dependencies, runs the
complete unittest suite, compiles sources, and checks both real mock CLI outcomes.
Each job creates a fresh virtual environment, bootstraps pip 26.3 there, and uses
that interpreter for installation and verification, excluding preinstalled runner
packages from the verification environment.
The standalone checker uses temporary destinations, strips provider credentials
from its child environments, fails on incorrect results, and removes outputs.
For an independent compatibility check, install `requirements.txt` alone in a
fresh environment using pip 26.3, then run the same checks. The floating job tests
the latest compatible resolution for Python 3.12, not every historical combination.

Offline here means no real provider/model calls: providers are intercepted in
tests and CLI smoke runs use `--mock`. Registry access is still needed for installs.
CI configures no provider keys, does not print environment variables, and uploads
no spectator artifacts. Python, pip, OS/architecture, dependencies, test diagnostics,
and concise mock outcomes remain in job logs. Runner images and Python patch
versions can change; the lock pins dependencies rather than the entire OS image.

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
The legacy demo also rejects existing paths. Use `python -m parallax_relay.demo`
for a unique ignored destination, or supply a fresh `--out` path. Never target the
committed `demo_output/` directory for routine verification.

Historical milestone plans and red/green logs document earlier work. They are not
current instructions or fresh verification. Add dated evidence rather than rewriting
those logs. Report the exact environment, commands, results, and untested areas.

Do not commit API keys, populated environment files, virtual environments, caches,
or unrelated run output. `.env.example` is a blank template. Read the
[running guide](docs/RUNNING.md) before sharing privileged spectator logs.

Before handing off, inspect `git diff --check`, the changed-file list, and the
relevant documentation links. Describe the problem, final behavior, verification,
and any remaining limitations. Inspect all six CI job results on the actual PR
revision before treating the configured matrix as verified.
