"""Prepare one explicit live invocation, or verify its artifacts offline.

No automatic reruns, remote probes, model fallbacks, or browser execution.
The checked-in profile is a run sheet, not standing spending authorization.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parallax_relay.config import ConfigError, GameConfig, load_config
from parallax_relay.play import load_env_file
from parallax_relay.protocol import ROLES
from parallax_relay.provenance import read_provenance
from parallax_relay.providers import _source_usage

PROFILE = ROOT / 'configs/live_smoke.json'
PHASES = ('broadcast', 'negotiate', 'commit')


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def profile_digest(profile: dict) -> str:
    return hashlib.sha256(_canonical(profile).encode('utf-8')).hexdigest()


def load_profile(path: Path = PROFILE) -> dict:
    try:
        profile = json.loads(path.read_text(encoding='utf-8'))
        if set(profile) != {'schema_version', 'verified_date', 'models', 'sources', 'config'}:
            raise ValueError
        if type(profile['schema_version']) is not int or profile['schema_version'] != 1:
            raise ValueError
        date.fromisoformat(profile['verified_date'])
        config = GameConfig.model_validate(profile['config'])
        if set(profile['models']) != set(ROLES) or set(profile['sources']) != set(ROLES):
            raise ValueError
        model_vars = {p.model_env for p in config.players.values()}
        if len(model_vars) != len(ROLES) or model_vars & {p.api_key_env for p in config.players.values()}:
            raise ValueError
        for role in ROLES:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', profile['models'][role]):
                raise ValueError
            source = profile['sources'][role]
            if set(source) != {'model_url', 'pricing_url', 'notes'} or not all(
                    isinstance(value, str) for value in source.values()):
                raise ValueError
        # Normalize defaults once for both the launcher and generated Site contract.
        profile['config'] = config.model_dump()
        profile_digest(profile)
        return profile
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise ValueError('Invalid smoke profile; review the public profile before execution.') from None


def configuration_toml(config: GameConfig) -> str:
    lines = ['# Frozen smoke configuration; model IDs are pinned by scripts/live_smoke.py', '[match]']
    lines += [f'{key} = {json.dumps(value)}' for key, value in config.match.model_dump().items()
              if value is not None]
    for role in ROLES:
        player = config.players[role]
        lines += ['', f'[players.{role}]']
        lines += [f'{key} = {json.dumps(getattr(player, key))}'
                  for key in ('provider', 'model_env', 'api_key_env')]
        if player.pricing:
            lines += [f'[players.{role}.pricing]']
            lines += [f'{key} = {value}' for key, value in player.pricing.model_dump().items()]
    return '\n'.join(lines) + '\n'


def prepare_environment(profile: dict, environ=None, env_file: Path | None = None) -> dict:
    env = dict(os.environ if environ is None else environ)
    if env_file is not None:
        load_env_file(env_file, env)
    config = GameConfig.model_validate(profile['config'])
    for role, player in config.players.items():
        env[player.model_env] = profile['models'][role]
    config.resolve(env)
    # Exclude Python startup/import overrides. Keep process transport settings;
    # some execution environments require a proxy/certificate configuration.
    for key in list(env):
        if key.upper() in {'PYTHONPATH', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'}:
            del env[key]
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def _count(value) -> bool:
    return type(value) is int and value >= 0


def verify_run(directory: Path, profile: dict) -> dict:
    """Check structural evidence, not authenticity or model intelligence."""
    report = {'accepted': False, 'cli_returncode': None, 'checks': {},
              'providers': {role: {'accepted': False, 'attempts': 0} for role in ROLES}}
    try:
        objects = {name: json.loads((directory / f'{name}.json').read_text(encoding='utf-8'))
                   for name in ('manifest', 'result', 'final_state', 'smoke_launch')}
        records = {name: [json.loads(line) for line in
                         (directory / f'{name}.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
                   for name in ('calls', 'phases', 'replay')}
        if any(not isinstance(item, dict) for item in objects.values()) or any(
                not isinstance(item, dict) for rows in records.values() for item in rows):
            raise ValueError
        manifest, result, state, receipt = (objects[n] for n in
                                          ('manifest', 'result', 'final_state', 'smoke_launch'))
        calls, phases, replay = (records[n] for n in ('calls', 'phases', 'replay'))
        provenance = read_provenance(manifest)
        cfg = GameConfig.model_validate(profile['config'])
        expected_players = {r: {'provider': cfg.players[r].provider, 'model': profile['models'][r]}
                            for r in ROLES}
        execution = provenance['execution']['value']
        checks = report['checks']
        code = receipt.get('cli_returncode')
        report['cli_returncode'] = code if type(code) is int else None
        checks['launcher'] = (type(code) is int and code == 0 and receipt.get('schema_version') == 1
                              and receipt.get('profile_sha256') == profile_digest(profile))
        checks['configuration'] = (
            manifest.get('schema_version') == 2 and manifest.get('mode') == 'live'
            and manifest.get('players') == expected_players
            and _canonical(manifest.get('settings')) == _canonical(profile['config']['match'])
            and execution['mode'] == 'live'
            and _canonical(execution['settings']) == _canonical(profile['config']['match'])
            and execution['pricing'] == {r: cfg.players[r].pricing.model_dump() for r in ROLES}
            and all(all(execution['players'][r][k] == v for k, v in p.items())
                    for r, p in expected_players.items()))
        checks['outcome'] = (
            result.get('schema_version') == 2 and result.get('stop_reason') == 'turn_limit'
            and result.get('completed') is False and result.get('win') is False
            and result.get('loss') is False and result.get('scores') is None
            and type(result.get('turns')) is int and result['turns'] == 1
            and len(replay) == 1 and replay[0].get('turn') == 1
            and not replay[0].get('fallbacks') and replay[0]['state_after'] == state
            and type(state.get('turn')) is int and state['turn'] == 1
            and state.get('win') is False and state.get('loss') is False
            and result.get('energy') == state.get('energy'))
        budget = result['budget']
        checks['calls'] = (9 <= len(calls) <= cfg.match.max_calls
                           and type(budget['calls_started']) is int and budget['calls_started'] == len(calls)
                           and budget['max_calls'] == cfg.match.max_calls
                           and all(c.get('role') in ROLES and c.get('phase') in PHASES
                                   and type(c.get('turn')) is int and c['turn'] == 0 for c in calls)
                           and all(_count(budget[k]) for k in
                                   ('reported_input_tokens', 'reported_output_tokens', 'unknown_usage_calls')))
        checks['phases'] = (len(phases) == 3 and [p['phase'] for p in phases] == list(PHASES)
                            and all(type(p.get('turn')) is int and p['turn'] == 0 for p in phases))
        checks['lifecycle'] = (provenance['lifecycle']['stage'] == 'ended'
                               and provenance['lifecycle']['stop_reason'] == 'turn_limit'
                               and provenance['lifecycle']['execution_stop_reason'] == 'turn_limit')
        report['source'] = {key: provenance['source'][key] for key in ('revision', 'status', 'reason')}
        totals = {'reported_input_tokens': 0, 'reported_output_tokens': 0, 'unknown_usage_calls': 0}
        usage_valid = True
        for call in calls:
            usage = call.get('usage')
            if usage is not None and not isinstance(usage, dict):
                usage_valid = False
                continue
            values = [(usage or {}).get(key) for key in ('input_tokens', 'output_tokens')]
            usage_valid &= all(value is None or _count(value) for value in values)
            for key, value in zip(('reported_input_tokens', 'reported_output_tokens'), values):
                if _count(value):
                    totals[key] += value
            totals['unknown_usage_calls'] += int(any(value is None for value in values))
        cost = budget.get('estimated_cost_usd')
        checks['usage'] = (usage_valid and all(budget[key] == value for key, value in totals.items())
                           and type(cost) in (int, float) and math.isfinite(cost) and cost >= 0)
        if checks['usage']:
            report['budget'] = {**totals, 'estimated_cost_usd': cost}
        for role in ROLES:
            own = [c for c in calls if c.get('role') == role]
            successes = True
            for phase in PHASES:
                attempts = [c for c in own if c.get('phase') == phase]
                successes &= (1 <= len(attempts) <= cfg.match.max_attempts
                              and [c.get('attempt') for c in attempts] == list(range(1, len(attempts) + 1))
                              and all(type(c.get('attempt')) is int for c in attempts)
                              and attempts[-1].get('status') == 'ok'
                              and sum(c.get('status') == 'ok' for c in attempts) == 1
                              and len([p for p in phases if p.get('phase') == phase
                                       and p.get('statuses', {}).get(role) == 'ok']) == 1)
            report['providers'][role] = {
                'accepted': bool(successes), 'attempts': len(own), **expected_players[role],
                'statuses': [c['status'] if isinstance(c.get('status'), str)
                             and re.fullmatch(r'[a-z_]{1,48}', c['status']) else 'unknown' for c in own],
                'source_usage': [],
            }
            allowed = _source_usage(cfg.players[role].provider, {})
            for call in own:
                source = (call.get('usage') or {}).get('source_usage')
                safe = {}
                if isinstance(source, dict):
                    for key in allowed:
                        item = source.get(key)
                        if isinstance(item, dict) and item.get('state') in {'omitted', 'null', 'count', 'invalid'}:
                            value = item.get('value')
                            if (item['state'] == 'count' and _count(value)) or (item['state'] != 'count' and value is None):
                                safe[key] = {'state': item['state'], 'value': value}
                report['providers'][role]['source_usage'].append(safe or None)
        # Require the role PNGs used for the resolved turn and final viewer.
        checks['artifacts'] = (directory / 'index.html').is_file() and all(
            (directory / f'turn_00_{role.lower()}.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            for role in ROLES)
        report['accepted'] = all(checks.values()) and all(p['accepted'] for p in report['providers'].values())
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        report['checks']['readable_evidence'] = False
    return report


def launch(profile: dict, *, live: bool, environ=None, out: Path | None = None,
           config_path: Path | None = None, env_file: Path | None = None) -> dict:
    config = GameConfig.model_validate(profile['config'])
    if config_path is not None and load_config(config_path).model_dump() != config.model_dump():
        raise ValueError('Export differs from the frozen smoke profile; review changes before execution.')
    env = prepare_environment(profile, environ, env_file)
    directory = (out or ROOT / 'runs' / ('live_smoke_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                                       + '_' + uuid4().hex[:8])).resolve() if live else None
    if directory is not None and directory.exists():
        raise ValueError('Use a fresh output directory.')
    with tempfile.TemporaryDirectory(prefix='parallax-smoke-') as temp:
        config_file, empty_env = Path(temp) / 'smoke.toml', Path(temp) / 'empty.env'
        config_file.write_text(configuration_toml(config), encoding='utf-8')
        empty_env.write_text('', encoding='utf-8')
        # An explicit empty env file prevents the ordinary CLI's implicit .env
        # fallback. Credentials already came from the selected process/file.
        command = [sys.executable, '-m', 'parallax_relay.play', '--live' if live else '--check',
                   '--config', str(config_file), '--env-file', str(empty_env), '--quiet']
        if live:
            command += ['--out', str(directory)]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                   text=True, encoding='utf-8', errors='replace', timeout=600)
    result = {'cli_returncode': completed.returncode, 'out': str(directory) if directory else None}
    if live:
        receipt = {'schema_version': 1, 'profile_sha256': profile_digest(profile),
                   'cli_returncode': completed.returncode}
        if directory.is_dir():
            (directory / 'smoke_launch.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        result['verification'] = verify_run(directory, profile)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check', action='store_true', help='Local validation only; no provider requests.')
    modes.add_argument('--live', action='store_true', help='One potentially billable invocation; requires authorization.')
    modes.add_argument('--verify', type=Path, metavar='RUN_DIR', help='Verify existing artifacts offline.')
    parser.add_argument('--config', type=Path, help='Optional workbench TOML; must match the profile.')
    parser.add_argument('--env-file', type=Path, help='Local keys; process values take precedence. Defaults to .env.smoke if present.')
    parser.add_argument('--out', type=Path, help='Fresh output directory, only with --live.')
    args = parser.parse_args(argv)
    if args.out and not args.live:
        parser.error('--out requires --live')
    try:
        profile = load_profile()
        if args.verify:
            report = verify_run(args.verify, profile)
            print(json.dumps(report, indent=2))
            return 0 if report['accepted'] else 1
        env_file = args.env_file or (ROOT / '.env.smoke' if (ROOT / '.env.smoke').is_file() else None)
        result = launch(profile, live=args.live, out=args.out, config_path=args.config, env_file=env_file)
        print(json.dumps(result, indent=2))
        code = result['cli_returncode']
        return code if code != 0 else 0 if args.check or result['verification']['accepted'] else 1
    except (ConfigError, ValueError):
        print('Smoke configuration/credentials invalid. Check the profile, matching export and required local variables.', file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError):
        print('Smoke launcher failed; results are unverified. Do not rerun live without authorization.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
