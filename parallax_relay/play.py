"""CLI: explicit offline/mock, live, or local configuration check."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4
from pydantic import ValidationError

from .agents import ScriptedAgent
from .config import ConfigError, MatchSettings, load_config
from .orchestrator import MatchExecutionError, run_match
from .protocol import ROLES
from .providers import HTTPAgent
from .recording import Recorder

ROOT = Path(__file__).resolve().parent.parent
CLEANUP_TIMEOUT_SECONDS = 5


def load_env_file(path: Path, environ: dict | None = None) -> None:
    """Small literal KEY=VALUE reader; no interpolation, imports or execution.

    Existing process environment wins. Supports whole-line comments and single
    or double quoted values. Does not support multiline values or inline comments.
    """
    env = os.environ if environ is None else environ
    try:
        if path.stat().st_size > 65536:
            raise ConfigError('Environment file is too large')
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeError:
        raise ConfigError('Environment file must use UTF-8 encoding') from None
    except OSError:
        raise ConfigError(f'Cannot read environment file: {path.name}') from None
    pending = {}
    for index, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].strip()
        key, sep, value = line.partition('=')
        key, value = key.strip(), value.strip()
        if not sep or not re.fullmatch(r'[A-Z_][A-Z0-9_]{0,127}', key):
            raise ConfigError(f'Invalid environment assignment at line {index}')
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ConfigError(f'Unclosed environment value at line {index}')
            value = value[1:-1]
        pending[key] = value
    for key, value in pending.items():
        env.setdefault(key, value)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Run three independent Parallax Relay players.')
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument('--mock', action='store_true', help='Offline scripted agents; no API calls or keys.')
    modes.add_argument('--live', action='store_true', help='Real, potentially billable provider calls.')
    modes.add_argument('--check', action='store_true', help='Validate local config/credentials; no API requests.')
    p.add_argument('--config', type=Path, default=ROOT/'configs'/'three_models.toml')
    p.add_argument('--env-file', type=Path, help='Literal .env file (defaults to .env when it exists).')
    p.add_argument('--out', type=Path, help='New output directory. Existing directories are rejected.')
    p.add_argument('--max-turns', type=int, choices=range(1,13))
    p.add_argument('--max-calls', type=int)
    p.add_argument('--fast', action='store_true', help='One communication pass instead of two.')
    p.add_argument('--quiet', action='store_true', help='Only print the result and replay path.')
    return p


async def _run(args, cfg, settings, runtime) -> int:
    requested_settings = settings.model_dump()
    if args.mock:
        # Only this CLI path constructs the known zero-usage scripted players.
        # Keep generic/programmatic and live cost guards intact.
        settings = settings.model_copy(update={'max_estimated_cost_usd': None})
    out = args.out or Path('runs')/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid4().hex[:6])
    mode = 'mock' if args.mock else 'live'
    players = ({r: {'provider':'mock','model':'scripted-fixture'} for r in ROLES} if args.mock else
               {r: {'provider':p.provider,'model':p.model} for r,p in runtime.items()})
    manifest = {'schema_version':2, 'mode':mode, 'players':players,
                'settings':settings.model_dump(), 'room':'The Split Span'}
    if args.mock:
        manifest['requested_settings'] = requested_settings
    try:
        recorder = Recorder(out, manifest)
    except FileExistsError:
        # Windows also uses EEXIST for a nonexistent path below a regular file.
        try:
            out.lstat()
        except OSError:
            raise OSError('Cannot create output directory') from None
        raise
    agents = {}
    failure = None
    try:
        for role in ROLES:
            if args.mock:
                agents[role] = ScriptedAgent(role)
            else:
                p = runtime[role]
                agents[role] = HTTPAgent(p.provider, p.model, p.api_key, timeout_seconds=settings.timeout_seconds)
        def progress(event):
            if not args.quiet:
                status = ', '.join(f'{r}={s}' for r,s in event['statuses'].items())
                print(f"Round {event['turn']+1:02d} | {event['phase']:<9} | {status}", flush=True)
        rates = {r:cfg.players[r].pricing for r in ROLES}
        result = await run_match(agents, settings, rates=rates, recorder=recorder, progress=progress)
        print(json.dumps(result.summary(),indent=2))
        print(f'Replay: {out / "index.html"}')
        if result.stop_reason in {'provider_error','internal_error','unreliable_agent'}:
            return 3
        if result.stop_reason in {'call_budget','spend_budget'}:
            return 4
        return 1 if result.world.loss else 0
    except MatchExecutionError as error:
        failure = error
        print(json.dumps(error.result.summary(), indent=2))
        print(f'Match stopped: {error.result.stop_reason} during {error.operation}.', file=sys.stderr)
        if recorder.viewer_ready:
            print(f'Replay: {out / "index.html"}')
        else:
            print(f'Partial output: {out}; replay recovery incomplete.', file=sys.stderr)
        return 2 if error.result.stop_reason == 'local_error' else 3
    except BaseException as error:
        failure = error
        raise
    finally:
        cleanup_errors = []
        try:
            closed = await asyncio.wait_for(
                asyncio.gather(*(a.close() for a in agents.values()), return_exceptions=True),
                timeout=CLEANUP_TIMEOUT_SECONDS)
            cleanup_errors = [('client_close', e) for e in closed if isinstance(e, BaseException)]
        except asyncio.CancelledError as error:
            # A fresh caller cancellation takes precedence over an earlier failure.
            # Individual close() cancellations are returned by gather instead.
            if failure is not None:
                if hasattr(failure, 'result'):
                    error.result = failure.result
                error.secondary_errors = (('prior_execution', failure),)
            raise
        except Exception as error:
            cleanup_errors.append(('client_close', error))
        if cleanup_errors:
            if isinstance(failure, (MatchExecutionError, asyncio.CancelledError)):
                failure.secondary_errors = (*getattr(failure, 'secondary_errors', ()), *cleanup_errors)
            print('Provider cleanup incomplete.', file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        values = cfg.match.model_dump()
        if args.fast: values['communication_rounds'] = 1
        if args.max_turns is not None: values['max_turns'] = args.max_turns
        if args.max_calls is not None: values['max_calls'] = args.max_calls
        settings = MatchSettings.model_validate(values)
        runtime = {}
        if not args.mock:
            if args.env_file:
                load_env_file(args.env_file)
            elif Path('.env').is_file():
                load_env_file(Path('.env'))
            runtime = cfg.resolve()
        if args.check:
            print('Configuration valid; no API requests made. Remote access and model capabilities are not verified.')
            print(json.dumps({r: {'provider':p.provider,'model':p.model} for r,p in runtime.items()},indent=2))
            return 0
        if not args.quiet:
            print('MOCK scripted fixture; no network calls.' if args.mock else
                  'LIVE API mode: calls may be billable. Limits and usage are recorded.')
        return asyncio.run(_run(args,cfg,settings,runtime))
    except FileExistsError:
        print('Output directory already exists. Choose a new --out path.',file=sys.stderr)
        return 2
    except (ConfigError, ValidationError) as exc:
        print(str(exc) if isinstance(exc,ConfigError) else 'Invalid match settings.',file=sys.stderr)
        return 2
    except OSError:
        print('Local file or connection setup failed. Check paths and permissions.',file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted. Partial logs were retained when a match had started.',file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
