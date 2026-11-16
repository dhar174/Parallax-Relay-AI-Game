"""Register once, execute serially, and retain every attempted trial.

No providers are constructed by registration or analysis. Live execution requires
an explicit --live invocation, credentials, and both local estimate guards.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import re
from pathlib import Path
import sys
from time import monotonic
from uuid import UUID, uuid4

from .campaign_models import CampaignSpec, schedule, trial_settings, trial_exposure
from .conditions import CONDITIONS
from .orchestrator import MatchExecutionError, run_match
from .play import CLEANUP_TIMEOUT_SECONDS, load_env_file
from .policies import make_policy
from .protocol import ROLES
from .providers import HTTPAgent, provider_contract
from .provenance import (ROOT, PlayerIdentity, ProvenanceContext, canonical_hash,
                         collect_environment, collect_source, input_identities)
from .recording import Recorder
from .config import Rates, ConfigError
from .money import total as money_total, difference, json_fields, amount
from .campaign_validation import validate_frozen, utc, equal_money
from .state import initial_world


class CampaignError(ValueError):
    """Fixed sanitized messages only."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def atomic_json(path: Path, value) -> None:
    encoded = json.dumps(value, ensure_ascii=True, allow_nan=False, indent=2) + '\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'),
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (OSError, ValueError, RecursionError):
        raise CampaignError('Missing or invalid campaign JSON') from None


def frozen_inputs(spec: CampaignSpec) -> dict:
    return {'source': collect_source(ROOT), 'environment': collect_environment(),
            'inputs': {name: input_identities(initial_world().snapshot(),
                       trial_settings(spec, {'condition': name, 'team': 'models' if spec.mode == 'live' else 'wait'}))
                       for name in spec.conditions},
            'provider_contracts': {p.provider: provider_contract(p.provider) for p in spec.roster},
            'sampling': 'provider_default', 'known_model_revisions': None,
            'analysis': {'version': 1, 'bootstrap_resamples': 10000, 'seed': 0,
                         'percentile': 'Hyndman-Fan-7', 'prng': 'random.Random',
                         'concurrency': 1, 'primary_contrast': ['full', 'disabled']}}


def register(value: dict, out: Path, *, pilot: Path | None = None) -> dict:
    spec = CampaignSpec.model_validate(value)
    frozen = frozen_inputs(spec)  # Before creating output; never resolves credentials.
    if spec.stage != 'diagnostic' and (frozen['source']['status'] != 'clean' or
                                      frozen['environment']['value']['status'] != 'complete'):
        raise CampaignError('Protocol cohorts require clean source and complete environment identity')
    pilot_record = None
    if spec.stage == 'confirmatory':
        if pilot is None:
            raise CampaignError('Confirmation requires a completed pilot registration')
        from .campaign_analysis import analyze
        pilot_data = read_registration(pilot)
        pilot_report = analyze(pilot)
        if pilot_data['spec']['stage'] != 'pilot' or not pilot_report['cohort_eligible']:
            raise CampaignError('Confirmation requires a completed pilot registration')
        if (pilot_data['spec']['mode'] != spec.mode or pilot_data['spec']['rooms'] != spec.rooms or
                sorted(pilot_data['spec']['roster'],key=lambda p:(p['provider'],p['model'])) !=
                sorted([p.model_dump() for p in spec.roster],key=lambda p:(p['provider'],p['model'])) or
                set(pilot_data['spec']['policies']) != set(spec.policies)):
            raise CampaignError('Changed roster, policies or rooms require a new pilot')
        pilot_record = {'registration_sha256': pilot_data['sha256'],
                        'changed_frozen_sections': [k for k in frozen if frozen[k] != pilot_data['frozen'][k]],
                        'match_settings_changed': spec.match.model_dump() != pilot_data['spec']['match']}
    elif pilot is not None:
        raise CampaignError('Only confirmation can reference a pilot')
    data = {'schema_version': 1, 'experiment_id': str(uuid4()), 'created_at': now(),
            'spec': spec.model_dump(mode='json'), 'frozen': frozen, 'pilot': pilot_record,
            'schedule': schedule(spec)}
    exposures = [trial_exposure(spec, trial) for trial in data['schedule']]
    data['planned_exposure'] = json_fields({'calls': sum(c for c, _ in exposures),
                                'estimated_usd': money_total(Decimal(str(d)) for _, d in exposures),
                                'cost_is_estimate_not_billing_guarantee': True})
    data['sha256'] = canonical_hash(data)
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / 'registration.json', data)
    if read_json(out / 'registration.json') != data:
        raise CampaignError('Registration readback failed')
    return data


def read_registration(root: Path) -> dict:
    data = read_json(root / 'registration.json')
    try:
        if type(data['schema_version']) is not int or data['schema_version'] != 1:
            raise ValueError()
        digest = data['sha256']
        if digest != canonical_hash({k: v for k, v in data.items() if k != 'sha256'}):
            raise ValueError()
        if str(UUID(data['experiment_id']))!=data['experiment_id']:
            raise ValueError()
        utc(data['created_at'])
        spec = CampaignSpec.model_validate(data['spec'])
        validate_frozen(data['frozen'],spec)
        pilot=data['pilot']
        if spec.stage=='confirmatory':
            if (not isinstance(pilot,dict) or not isinstance(pilot.get('registration_sha256'),str) or
                not re.fullmatch(r'[0-9a-f]{64}',pilot['registration_sha256']) or
                type(pilot.get('match_settings_changed')) is not bool or
                not isinstance(pilot.get('changed_frozen_sections'),list) or
                any(key not in data['frozen'] for key in pilot['changed_frozen_sections'])):
                raise ValueError()
        elif pilot is not None:raise ValueError()
        actual, expected = data['schedule'], schedule(spec)
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError()
        ids, blocks = set(), {}
        for trial, template in zip(actual, expected):
            if set(trial) != set(template):
                raise ValueError()
            for key in ('trial_id', 'block_id'):
                if str(UUID(trial[key])) != trial[key]:
                    raise ValueError()
            if trial['trial_id'] in ids:
                raise ValueError()
            ids.add(trial['trial_id'])
            group = tuple(trial[k] for k in ('room', 'team', 'assignment_id', 'repetition'))
            if trial['block_id'] in blocks and blocks[trial['block_id']] != group:
                raise ValueError()
            blocks[trial['block_id']] = group
            if {k: v for k, v in trial.items() if k not in ('trial_id', 'block_id')} != {
                    k: v for k, v in template.items() if k not in ('trial_id', 'block_id')}:
                raise ValueError()
        if len(blocks) != len(set(blocks.values())):
            raise ValueError()
        exposures=[trial_exposure(spec,t) for t in actual]
        if (type(data['planned_exposure']['calls']) is not int or
            data['planned_exposure']['calls']!=sum(c for c,_ in exposures) or
            not equal_money(data['planned_exposure'],'estimated_usd',money_total(Decimal(str(d)) for _,d in exposures))):
            raise ValueError()
        return data
    except (KeyError, TypeError, ValueError, RecursionError, AttributeError, OverflowError):
        raise CampaignError('Invalid campaign registration or schedule') from None


class Ledger:
    def __init__(self, root: Path):
        self.root, self.sequence = root, 0

    def emit(self, event: str, **fields) -> dict:
        self.sequence += 1
        record = {'schema_version': 1, 'sequence': self.sequence, 'event': event,
                  'at': now(), **json_fields(fields)}
        with (self.root / 'ledger.jsonl').open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        atomic_json(self.root / 'status.json', record)
        return record


async def execute_trial(root: Path, registration: dict, spec: CampaignSpec, trial: dict,
                        environ: dict) -> dict:
    settings = trial_settings(spec, trial)
    agents, recorder, result = {}, None, None
    started = monotonic()
    stage, stop, cleanup = 'setup', 'setup_failure', 'ok'
    execution_stop = None
    cancelled = None
    try:
        model_team = trial['team'] == 'models'
        identities = {r: PlayerIdentity(provider=trial['players'][r]['provider'], model=trial['players'][r]['model'])
                      if model_team else PlayerIdentity(provider='mock', model=(
                          'scripted-fixture' if trial['team'] == 'scripted' else trial['team'] + '-v1')) for r in ROLES}
        context = ProvenanceContext(mode='live' if model_team else 'mock',
                                    experiment_id=UUID(registration['experiment_id']), trial_id=UUID(trial['trial_id']),
                                    players=identities, requested_settings=settings.model_copy(update={
                                        'max_estimated_cost_usd': spec.match.max_estimated_cost_usd}),
                                    policy=None if model_team else trial['team'])
        recorder = Recorder(root / 'trials' / trial['trial_id'], {'room': 'The Split Span'}, context=context)
        rates = {}
        for role in ROLES:
            if model_team:
                player = trial['players'][role]
                agents[role] = HTTPAgent(player['provider'], player['model'], environ.get(player['api_key_env'], ''),
                                         timeout_seconds=settings.timeout_seconds)
                rates[role] = Rates.model_validate(player['pricing'])
            else:
                agents[role] = make_policy(trial['team'], role, UUID(trial['trial_id']))
        stage = 'execution'
        result = await run_match(agents, settings, rates=rates, recorder=recorder)
        stop = result.stop_reason
    except MatchExecutionError as error:
        result, stop, execution_stop = error.result, error.result.stop_reason, error.original_stop_reason
    except asyncio.CancelledError as error:
        cancelled = error
        result, stop = getattr(error, 'result', None), 'cancelled'
    except Exception:
        stop = 'setup_failure' if stage == 'setup' else 'internal_error'
    finally:
        try:
            closed = await asyncio.wait_for(asyncio.gather(*(a.close() for a in agents.values()),
                                                           return_exceptions=True), CLEANUP_TIMEOUT_SECONDS)
            if any(isinstance(value, BaseException) for value in closed):
                cleanup = 'failed'
        except asyncio.CancelledError as error:
            cancelled, cleanup, stop = error, 'cancelled', 'cancelled'
        except Exception:
            cleanup = 'failed'
    summary = result.summary() if result is not None else None
    if cleanup == 'failed' and cancelled is None:
        stop = 'local_error'
    provenance = recorder.manifest['provenance'] if recorder else None
    evidence = {'trial_id': trial['trial_id'], 'stage': stage, 'stop_reason': stop,
                'result': summary, 'cleanup_status': cleanup, 'elapsed_seconds': monotonic() - started,
                'run_id': provenance['run_id'] if provenance else None,
                'execution_stop_reason': execution_stop or (provenance or {}).get('lifecycle', {}).get('execution_stop_reason'),
                'recording_stop_reason': summary['stop_reason'] if summary else None,
                'cancelled': cancelled is not None}
    # Cancellation remains cancellation, with its safe receipt attached.
    if cancelled is not None:
        cancelled.campaign_trial = evidence
        raise cancelled
    return evidence


async def run_campaign(root: Path, *, offline: bool = False, live: bool = False,
                       environ: dict | None = None) -> None:
    registration = read_registration(root)
    spec = CampaignSpec.model_validate(registration['spec'])
    if offline == live or offline != (spec.mode == 'offline'):
        raise CampaignError('Select the registered execution mode explicitly: --offline or --live')
    selected_env=dict(os.environ if environ is None else environ)
    if live:
        for player in spec.roster:
            key=selected_env.get(player.api_key_env)
            if not isinstance(key,str) or not key.strip():
                raise CampaignError('Missing selected live credentials; configure keys before campaign launch')
            key=key.strip()
            if '\r' in key or '\n' in key:
                raise CampaignError('Invalid selected live credential format')
            selected_env[player.api_key_env]=key
    current = frozen_inputs(spec)
    matches = current == registration['frozen']
    if spec.stage != 'diagnostic' and not matches:
        raise CampaignError('Frozen source/environment/inputs changed; register a new cohort')
    lock = root / '.runner.lock'
    # Atomic directory creation rejects every existing directory entry, including
    # broken symlinks on Windows (where file open('x') can follow their target).
    ledger = Ledger(root)
    stop = 'completed'
    calls_used, dollars_used = 0, Decimal(0)
    last_launch = None
    active_block = None
    block_calls, block_dollars = 0, Decimal(0)
    lock.mkdir()
    try:
        if any(path.exists() or path.is_symlink() for path in (root/'started.json',root/'ledger.jsonl')):
            raise CampaignError('Campaign already attempted; analyze it without relaunching')
        atomic_json(root / 'started.json', {'registration_sha256': registration['sha256'], 'at': now()})
        ledger.emit('campaign_started', registration_sha256=registration['sha256'],
                    registration_matches=matches)
        blocks = {}
        for trial in registration['schedule']:
            blocks.setdefault(trial['block_id'], []).append(trial)
        for block_id, trials in blocks.items():
            exposure = [trial_exposure(spec, t) for t in trials]
            block_calls = sum(c for c, _ in exposure)
            block_dollars = money_total(Decimal(str(d)) for _, d in exposure)
            cap = spec.campaign_max_estimated_cost_usd
            if calls_used + block_calls > spec.campaign_max_calls or (cap is not None and
                    money_total((dollars_used,block_dollars)) > Decimal(str(cap))):
                stop = 'campaign_call_budget' if calls_used + block_calls > spec.campaign_max_calls else 'campaign_spend_budget'
                break
            ledger.emit('block_reserved', block_id=block_id, reserved_calls=block_calls,
                        reserved_estimated_usd=block_dollars)
            active_block = block_id
            for trial, (max_calls, max_dollars) in zip(trials, exposure):
                if last_launch is not None:
                    await asyncio.sleep(max(0, spec.min_trial_interval_seconds - (monotonic() - last_launch)))
                if spec.stage != 'diagnostic' and frozen_inputs(spec) != registration['frozen']:
                    stop = 'frozen_input_drift'
                    break
                ledger.emit('trial_launched', trial_id=trial['trial_id'], block_id=block_id)
                last_launch = monotonic()
                interrupted = None
                try:
                    receipt = await execute_trial(root, registration, spec, trial,selected_env)
                except asyncio.CancelledError as error:
                    interrupted = error
                    receipt = getattr(error, 'campaign_trial', {
                        'trial_id': trial['trial_id'], 'stage': 'setup', 'stop_reason': 'cancelled',
                        'result': None, 'cleanup_status': 'cancelled', 'elapsed_seconds': monotonic()-last_launch,
                        'run_id': None, 'execution_stop_reason': None, 'recording_stop_reason': None,
                        'cancelled': True})
                summary = receipt['result']
                budget = summary['budget'] if summary else None
                actual_calls = budget['calls_started'] if budget else (0 if receipt['stage'] == 'setup' else None)
                actual_dollars = amount(budget,'estimated_cost_usd') if budget else None
                accounted_calls = actual_calls if actual_calls is not None else max_calls
                accounted_dollars = (actual_dollars if actual_dollars is not None else
                                     Decimal(0) if trial['team'] != 'models' or receipt['stage'] == 'setup' else Decimal(str(max_dollars)))
                calls_used += accounted_calls
                dollars_used = money_total((dollars_used,accounted_dollars))
                block_calls -= max_calls
                block_dollars = difference(block_dollars,Decimal(str(max_dollars)))
                ledger.emit('trial_finished', **receipt, accounted_calls=accounted_calls,
                            accounted_estimated_usd=accounted_dollars,
                            released_calls=max(0, max_calls - accounted_calls),
                            released_estimated_usd=max(Decimal(0), difference(Decimal(str(max_dollars)),accounted_dollars)))
                if interrupted is not None:
                    raise interrupted
                if accounted_calls > max_calls or accounted_dollars > Decimal(str(max_dollars)) or (
                        cap is not None and dollars_used > Decimal(str(cap))):
                    stop = 'accounting_overrun'
                    break
                if receipt['stop_reason'] in {'setup_failure', 'local_error', 'internal_error', 'provider_error',
                                               'unreliable_agent', 'call_budget', 'spend_budget'}:
                    stop = receipt['stop_reason']
                    break
            ledger.emit('block_released', block_id=block_id, released_calls=block_calls,
                        released_estimated_usd=block_dollars)
            active_block = None
            if stop != 'completed':
                break
        ledger.emit('campaign_stopped', reason=stop, accounted_calls=calls_used,
                    accounted_estimated_usd=dollars_used)
    except asyncio.CancelledError:
        if active_block is not None:
            ledger.emit('block_released', block_id=active_block, released_calls=block_calls,
                        released_estimated_usd=block_dollars)
        ledger.emit('campaign_stopped', reason='cancelled', accounted_calls=calls_used,
                    accounted_estimated_usd=dollars_used)
        raise
    finally:
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    registration = commands.add_parser('register', help='Freeze a campaign without provider requests.')
    registration.add_argument('--spec', type=Path, required=True)
    registration.add_argument('--out', type=Path, required=True)
    registration.add_argument('--pilot', type=Path)
    run = commands.add_parser('run', help='Execute a registered campaign once.')
    run.add_argument('--campaign', type=Path, required=True)
    modes = run.add_mutually_exclusive_group(required=True)
    modes.add_argument('--offline', action='store_true')
    modes.add_argument('--live', action='store_true', help='Explicit potentially billable invocation.')
    run.add_argument('--env-file', type=Path)
    analysis = commands.add_parser('analyze', help='Read artifacts and write a fresh JSON/CSV report.')
    analysis.add_argument('--campaign', type=Path, required=True)
    analysis.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'register':
            data = register(read_json(args.spec), args.out, pilot=args.pilot)
            print(f"Registered {len(data['schedule'])} trials; no API requests made.")
        elif args.command == 'run':
            env = dict(os.environ)
            if args.env_file is not None:
                if not args.live:
                    raise CampaignError('Offline campaigns do not read credential files')
                load_env_file(args.env_file, env)
            asyncio.run(run_campaign(args.campaign, offline=args.offline, live=args.live, environ=env))
            from .campaign_analysis import analyze
            report = analyze(args.campaign)
            print(json.dumps({'completion_status': report['completion_status'], 'counts': report['counts']}))
            return 0 if report['completion_status'] == 'complete' else 4
        else:
            from .campaign_analysis import analyze, write_report
            report = analyze(args.campaign)
            write_report(report, args.out)
            print(f"Report: {args.out / 'report.json'}")
        return 0
    except KeyboardInterrupt:
        print('Interrupted; analyze the existing campaign without relaunching.', file=sys.stderr)
        return 130
    except (CampaignError,ConfigError) as error:
        print(str(error),file=sys.stderr)
        return 2
    except FileExistsError:
        print('Campaign/report path or runner lock already exists; choose a fresh output or analyze the existing campaign.',file=sys.stderr)
        return 2
    except (ValueError, OSError, TypeError, KeyError):
        print('Campaign operation failed; inspect registration and available sanitized ledger/artifacts.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    from .campaign import main as entrypoint
    raise SystemExit(entrypoint())
