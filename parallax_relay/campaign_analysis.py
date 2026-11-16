"""All-trial protocol-v1 reporting using only the standard library.

Unsigned local records establish consistency, not authenticity. No model dialogue,
private notes, HUDs or image bytes are copied into aggregate reports.
"""
from collections import Counter, defaultdict
import csv
from decimal import Decimal
import json
import math
import os
from pathlib import Path
import random
from statistics import NormalDist

from .campaign import CampaignError, atomic_json, now, read_json, read_registration
from .campaign_models import CampaignSpec, trial_settings
from .conditions import CONDITIONS
from .provenance import ROOT, collect_source, read_provenance, _WorldSnapshot
from .protocol import ROLES
from .campaign_validation import validate_summary, BUDGET_COUNTS, BUDGET_MONEY, utc, cross_artifacts
from .policies import policy_identity
from .money import amount, total as money_total, difference, json_fields
from uuid import UUID

TRIAL_STOPS = frozenset({'victory', 'defeat', 'turn_limit', 'call_budget', 'spend_budget',
                         'provider_error', 'unreliable_agent', 'internal_error', 'local_error',
                         'cancelled', 'setup_failure'})
ATTEMPT_STATUSES = frozenset({'ok', 'cancelled', 'timeout', 'refusal', 'incomplete',
                             'invalid_json_schema', 'stale_turn', 'response_size', 'internal_error',
                             'response_failed', 'response_too_large', 'quota_exhausted', 'http_error',
                             'invalid_provider_response', 'network_error', 'provider_error', 'no_response'})


def percentile(values: list[float], p: float) -> float | None:
    if type(p) not in (int,float) or not math.isfinite(p) or not 0<=p<=1:
        raise ValueError('Percentile probability must lie between zero and one')
    if not values:
        return None
    ordered = sorted(values)
    h = (len(ordered) - 1) * p
    lo, hi = math.floor(h), math.ceil(h)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (h - lo)


def distribution(values: list[float]) -> dict:
    return {'count': len(values), 'median': percentile(values, .5),
            'q1': percentile(values, .25), 'q3': percentile(values, .75)}


def wilson(successes: int, total: int) -> list[float] | None:
    if type(successes) is not int or type(total) is not int or not 0<=successes<=total:
        raise ValueError('Invalid binary counts')
    if total == 0:
        return None
    z = NormalDist().inv_cdf(.975)
    rate = successes / total
    center = rate + z*z/(2*total)
    spread = z * math.sqrt(rate*(1-rate)/total + z*z/(4*total*total))
    scale = 1 + z*z/total
    return [max(0, (center-spread)/scale), min(1, (center+spread)/scale)]


def success_summary(successes: int, launched: int, planned: int, unknown: int) -> dict:
    if (any(type(n) is not int for n in (successes,launched,planned,unknown)) or
            not (0 <= successes <= launched <= planned and 0 <= unknown <= launched-successes)):
        raise ValueError('Invalid outcome counts')
    return {'successes': successes, 'launched': launched, 'planned': planned, 'unknown': unknown,
            'rate': successes / launched if launched else None,
            'wilson_95': wilson(successes, launched),
            'launched_bounds': [successes/launched, (successes+unknown)/launched] if launched else None,
            'all_planned_bounds': [successes/planned, (successes+unknown+planned-launched)/planned] if planned else None}


def paired_bootstrap(strata: dict[str, list[tuple[int, int]]], *, resamples: int = 10000, seed: int = 0) -> dict:
    if not strata or any(not values for values in strata.values()) or resamples < 1:
        raise ValueError('Empty paired blocks')
    groups = [strata[key] for key in sorted(strata)]
    observed = sum(sum(a-b for a, b in group)/len(group) for group in groups)/len(groups)
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        estimates = []
        for group in groups:
            estimates.append(sum((lambda pair: pair[0]-pair[1])(group[rng.randrange(len(group))])
                                 for _ in group)/len(group))
        draws.append(sum(estimates)/len(estimates))
    interval = [percentile(draws, .025), percentile(draws, .975)]
    return {'difference_percentage_points': observed*100,
            'interval_95_percentage_points': [value*100 for value in interval],
            'degenerate_interval': interval[0] == interval[1],
            'resamples': resamples, 'seed': seed, 'percentile': 'Hyndman-Fan-7',
            'prng': 'random.Random', 'interpretation': 'Fixed-room comparison; a degenerate interval does not establish equivalence.'}


def _jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            value = json.loads(line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(value, dict):
                raise ValueError('Invalid row')
            rows.append(value)
    return rows


def _project_usage(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    def count(n):
        return n if type(n) is int and n >= 0 else None
    projected = {key: count(value.get(key)) for key in (
        'input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens')}
    source = value.get('source_usage')
    if isinstance(source, dict):
        from .providers import _source_usage
        allowed = set().union(*(_source_usage(provider, {}).keys() for provider in ('openai', 'anthropic', 'gemini')))
        projected['source_usage'] = {key: {'state': data['state'],
                                               'value': count(data.get('value')) if data['state'] == 'count' else None}
                                     for key, data in source.items() if key in allowed and isinstance(data, dict)
                                     and data.get('state') in ('count', 'null', 'omitted', 'invalid')}
    return projected


def _valid_summary(value) -> bool:
    try:
        validate_summary(value)
        return True
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):
        return False


def _artifacts(root: Path, trial: dict, registration: dict) -> tuple[dict, list[str]]:
    path = root / 'trials' / trial['trial_id']
    data, issues = {}, []
    for name in ('manifest', 'result', 'final_state', 'calls', 'phases', 'replay'):
        try:
            data[name] = _jsonl(path / (name+'.jsonl')) if name in ('calls', 'phases', 'replay') else read_json(path / (name+'.json'))
        except (OSError, ValueError, TypeError, RecursionError):
            issues.append(name + '_unavailable')
    settings = trial_settings(CampaignSpec.model_validate(registration['spec']), trial)
    # Validate each container independently: a malformed manifest must not bypass
    # checks on the remaining records, or prevent other trials being reported.
    for name in tuple(data):
        try:
            if name == 'manifest':
                p = read_provenance(data[name])
                if p is None or p['trial_id'] != trial['trial_id'] or p['experiment_id'] != registration['experiment_id']:
                    raise ValueError()
                if data[name].get('schema_version')!=(3 if p['schema_version']==3 else 2):raise ValueError()
                execution = p['execution']['value'] if p['execution'] else None
                expected_settings = settings.model_dump()
                if p['schema_version'] < 3: expected_settings.pop('room_id')
                if execution is None or execution['settings'] != expected_settings:
                    raise ValueError()
                if (p['lifecycle']['stage']!='ended' or str(UUID(p['run_id']))!=p['run_id'] or
                    execution['mode']!=('live' if trial['team']=='models' else 'mock')):
                    raise ValueError()
                expected_policy=None
                if trial['team']!='models':
                    expected_policy=policy_identity(trial['team'],UUID(trial['trial_id']),settings.max_turns)
                    if trial['team']=='uniform':expected_policy['python_version']=p['environment']['value']['python']['version']
                if execution['policy']!=expected_policy:raise ValueError()
                for role in ROLES:
                    expected = trial['players'][role] if trial['team'] == 'models' else {
                        'provider': 'mock', 'model': 'scripted-fixture' if trial['team'] == 'scripted' else trial['team']+'-v1'}
                    if any(p['players'][role][key] != expected[key] for key in ('provider', 'model')):
                        raise ValueError()
                    if trial['team'] == 'models' and (execution['pricing'][role] != expected['pricing'] or
                            p['players'][role]['api_contract'] != registration['frozen']['provider_contracts'][expected['provider']]):
                        raise ValueError()
                    if trial['team']!='models' and execution['pricing'][role] is not None:raise ValueError()
                data['provenance'] = p
                if p['source'] != registration['frozen']['source'] or p['environment'] != registration['frozen']['environment']:
                    issues.append('provenance_drift')
                frozen_inputs=registration['frozen']['inputs']
                if registration['schema_version']==2:frozen_inputs=frozen_inputs[trial['room']]
                if p['inputs'] != frozen_inputs[trial['condition']]:
                    issues.append('input_drift')
            elif name == 'result':
                if not _valid_summary(data[name]):
                    raise ValueError()
                if 'manifest' in data and data[name]['schema_version']!=data['manifest']['schema_version']:raise ValueError()
            elif name == 'final_state':
                if data.get('provenance', {}).get('schema_version') == 3:
                    from .rooms import RoomDefinition, validate_snapshot
                    room = RoomDefinition.model_validate_json(json.dumps(data['provenance']['inputs']['room']['value']['definition']))
                    validate_snapshot(data[name], room)
                else:
                    _WorldSnapshot.model_validate(data[name])
            elif name == 'calls':
                for call in data[name]:
                    if (call.get('role') not in ROLES or call.get('phase') not in CONDITIONS[trial['condition']].phases or
                        type(call.get('turn')) is not int or not 0 <= call['turn'] < settings.max_turns or
                        type(call.get('attempt')) is not int or not 1 <= call['attempt'] <= settings.max_attempts or
                        not isinstance(call.get('status'), str) or type(call.get('latency_seconds')) not in (int, float) or
                        not math.isfinite(call['latency_seconds']) or call['latency_seconds'] < 0 or
                        call.get('settlement_basis') not in ('complete_usage', 'retained_estimate')):
                        raise ValueError()
                    for key in ('reservation_quote_usd', 'settled_amount_usd'):
                        amount(call,key)
            elif name == 'phases':
                for phase in data[name]:
                    if (not isinstance(phase.get('statuses'), dict) or set(phase['statuses']) != set(ROLES) or
                        any(not isinstance(status, str) for status in phase['statuses'].values()) or
                        phase.get('phase') not in CONDITIONS[trial['condition']].phases):
                        raise ValueError()
            elif name == 'replay':
                for turn in data[name]:
                    if data.get('provenance',{}).get('schema_version')==3:
                        from .rooms import RoomDefinition,validate_snapshot
                        room=RoomDefinition.model_validate_json(json.dumps(data['provenance']['inputs']['room']['value']['definition']))
                        validate_snapshot(turn['state_after'],room)
                    if (not isinstance(turn.get('action_outcomes'), dict) or set(turn['action_outcomes']) != set(ROLES) or
                        any(code not in ('wait', 'applied', 'already_done', 'overload', 'invalid_parameters',
                                         'outer_wall', 'unbridged_gap', 'role_or_range', 'insufficient_resource',
                                         'nothing_to_collect', 'unknown_action') for code in turn['action_outcomes'].values())):
                        raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            issues.append(name + '_inconsistent')
            data.pop(name, None)
    result = data.get('result')
    if result:
        if 'calls' in data:
            if len(data['calls']) != result['budget']['calls_started']:
                issues.append('call_count_mismatch')
            amounts = [c['settled_amount_usd'] for c in data['calls']]
            total = result['budget']['estimated_cost_usd']
            if total is not None and (any(a is None for a in amounts) or not math.isclose(sum(amounts), total, rel_tol=1e-9, abs_tol=1e-12)):
                issues.append('cost_settlement_mismatch')
        if 'final_state' in data and any(data['final_state'][key] != result[key] for key in ('win', 'loss')):
            issues.append('world_outcome_mismatch')
        if 'final_state' in data and data['final_state']['turn'] != result['turns']:
            issues.append('world_turn_mismatch')
        if 'replay' in data and len(data['replay']) != result['turns']:
            issues.append('resolved_turn_count_mismatch')
    try:issues.extend(cross_artifacts(data,trial,settings))
    except (ValueError,TypeError,KeyError,OverflowError):issues.append('accounting_inconsistent')
    return data, sorted(set(issues))


def _counts(rows: list[dict]) -> dict:
    launched = [r for r in rows if r['launched']]
    return {'planned': len(rows), 'launched': len(launched), 'unlaunched': len(rows)-len(launched),
            'artifact_available': sum(r['artifact_available'] for r in launched),
            'operational_successes': sum(r['operational_success'] is True for r in launched),
            'known_operational_failures': sum(r['operational_success'] is False for r in launched),
            'unknown_operational': sum(r['operational_success'] is None for r in launched),
            'engine_win': sum(r['engine_outcome'] == 'win' for r in launched),
            'engine_defeat': sum(r['engine_outcome'] == 'defeat' for r in launched),
            'terminal': sum(r['engine_outcome'] in ('win', 'defeat') for r in launched),
            'nonterminal': sum(r['engine_outcome'] == 'nonterminal' for r in launched),
            'unknown_engine': sum(r['engine_outcome'] == 'unknown' for r in launched),
            'aborted': sum(r['stop_reason'] in ('setup_failure', 'provider_error', 'unreliable_agent', 'internal_error', 'local_error') for r in launched),
            'cancelled': sum(r['stop_reason'] == 'cancelled' for r in launched)}


def _summary(rows: list[dict]) -> dict:
    counts = _counts(rows)
    known_costs = [amount(r,'estimated_cost_usd') for r in rows if r['launched'] and r['estimated_cost_usd'] is not None]
    known_cost_total=money_total(known_costs)
    successes = [r for r in rows if r['operational_success'] is True]
    return {'counts': counts,
            'operational_success': success_summary(counts['operational_successes'], counts['launched'],
                                                   counts['planned'], counts['unknown_operational']),
            'engine_execution_cross_tab': dict(Counter(r['engine_outcome']+'/'+r['stop_reason'] for r in rows if r['launched'])),
            'stop_reasons': dict(Counter(r['stop_reason'] for r in rows)),
            'trial_duration_seconds': distribution([r['elapsed_seconds'] for r in rows if r['elapsed_seconds'] is not None]),
            'execution_duration_seconds': distribution([r['execution_elapsed_seconds'] for r in rows if r['execution_elapsed_seconds'] is not None]),
            'successful_terminal_turns': distribution([r['turns'] for r in successes]),
            'successful_terminal_energy': distribution([r['energy'] for r in successes if r['energy'] is not None]),
            'successful_terminal_scores': {role: distribution([r['scores'][role] for r in successes if r['scores']]) for role in ROLES},
            'usage': {key: sum(r.get(key) or 0 for r in rows) for key in ('calls_started', 'reported_input_tokens',
                      'reported_output_tokens', 'unknown_usage_calls', 'input_usage_calls', 'output_usage_calls',
                      'reported_cached_input_tokens', 'reported_reasoning_output_tokens')},
            'usage_coverage': {'trials_with_summary': sum(r['calls_started'] is not None for r in rows),
                               'launched_trials_without_summary': sum(r['launched'] and r['calls_started'] is None for r in rows)},
            'cost': json_fields({'priced_trials': len(known_costs), 'unpriced_or_unknown_launched_trials': counts['launched']-len(known_costs),
                     'known_estimated_usd': known_cost_total if known_costs else None,
                     'known_usage_estimated_usd': money_total(amount(r,'known_usage_estimated_usd') or Decimal(0) for r in rows) if known_costs else None,
                     'retained_estimate_usd': money_total(amount(r,'retained_estimate_usd') or Decimal(0) for r in rows) if known_costs else None,
                     'per_launched_trial_usd': float(known_cost_total/counts['launched']) if counts['launched'] and len(known_costs) == counts['launched'] else None,
                     'per_successful_completion_usd': float(known_cost_total/len(successes)) if successes and len(known_costs) == counts['launched'] else None,
                     'cost_is_estimate_not_billing_guarantee': True})}


def analyze(root: Path) -> dict:
    registration = read_registration(root)
    spec = CampaignSpec.model_validate(registration['spec'])
    launched, finished, anomalies, events = {}, {}, [], []
    campaign_start, campaign_stop = None, None
    ledger_path = root / 'ledger.jsonl'
    if ledger_path.exists():
        # A truncated trailing write never erases earlier durable launches.
        with ledger_path.open(encoding='utf-8') as handle:
            for sequence, line in enumerate(handle, 1):
                try:
                    row = json.loads(line,parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                    if (type(row['sequence']) is not int or row['sequence'] != sequence or
                            type(row['schema_version']) is not int or row['schema_version'] != 1):
                        raise ValueError()
                    event = row['event']
                    utc(row.get('at'))
                    numeric = {'block_reserved': ('reserved_calls', 'reserved_estimated_usd'),
                               'block_released': ('released_calls', 'released_estimated_usd'),
                               'trial_finished': ('accounted_calls', 'accounted_estimated_usd', 'released_calls',
                                                  'released_estimated_usd', 'elapsed_seconds'),
                               'campaign_stopped': ('accounted_calls', 'accounted_estimated_usd')}
                    if event not in ('campaign_started', 'trial_launched', *numeric):
                        raise ValueError()
                    for key in numeric.get(event, ()):
                        value = row.get(key)
                        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                            raise ValueError()
                        if key.endswith('_calls') and type(value) is not int:
                            raise ValueError()
                        if key.endswith('_usd'):amount(row,key)
                    if event == 'trial_finished' and (row.get('cleanup_status') not in ('ok', 'failed', 'cancelled') or
                            row.get('stage') not in ('setup', 'execution') or row.get('stop_reason') not in TRIAL_STOPS):
                        raise ValueError()
                    if event=='trial_finished':
                        for key in ('execution_stop_reason','recording_stop_reason'):
                            value=row.get(key)
                            if value is not None and (not isinstance(value,str) or value not in TRIAL_STOPS):raise ValueError()
                        run_id=row.get('run_id')
                        if run_id is not None and (not isinstance(run_id,str) or str(UUID(run_id))!=run_id):raise ValueError()
                    if event == 'campaign_started' and (type(row.get('registration_matches')) is not bool or
                            row.get('registration_sha256') != registration['sha256']):
                        raise ValueError()
                    if event == 'campaign_stopped' and row.get('reason') not in (TRIAL_STOPS | {
                            'completed', 'frozen_input_drift', 'accounting_overrun', 'campaign_call_budget', 'campaign_spend_budget'}):
                        raise ValueError()
                    if event == 'trial_launched':
                        if row['trial_id'] in launched:
                            raise ValueError()
                        launched[row['trial_id']] = row
                    elif event == 'trial_finished':
                        if row['trial_id'] not in launched or row['trial_id'] in finished:
                            raise ValueError()
                        finished[row['trial_id']] = row
                    elif event == 'campaign_started':
                        if campaign_start is not None or events:raise ValueError()
                        campaign_start = row
                    elif event == 'campaign_stopped':
                        if campaign_stop is not None:raise ValueError()
                        campaign_stop = row
                    if campaign_stop is not None and event!='campaign_stopped':raise ValueError()
                    events.append(row)
                except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                    anomalies.append('ledger_incomplete_or_invalid')
                    break
    ids = {t['trial_id'] for t in registration['schedule']}
    expected_blocks={t['trial_id']:t['block_id'] for t in registration['schedule']}
    block_ids=set(expected_blocks.values());reserved_blocks=set();released_blocks=set()
    for event in events:
        name=event['event'];block=event.get('block_id')
        if name in ('block_reserved','block_released','trial_launched'):
            if not isinstance(block,str) or block not in block_ids:
                anomalies.append('block_event_mismatch');continue
            if name=='block_reserved':
                if block in reserved_blocks:anomalies.append('block_event_mismatch')
                reserved_blocks.add(block)
            elif block not in reserved_blocks or block in released_blocks:
                anomalies.append('block_event_mismatch')
            elif name=='block_released':released_blocks.add(block)
    if any(row.get('block_id')!=expected_blocks.get(key) for key,row in launched.items()):
        anomalies.append('launch_block_mismatch')
    if set(launched) - ids or set(finished) - ids:
        raise CampaignError('Ledger refers to an unregistered trial')
    rows, attempt_rows = [], []
    for trial in registration['schedule']:
        trial_id = trial['trial_id']
        launch, receipt = launched.get(trial_id), finished.get(trial_id)
        row = {**{k: trial[k] for k in ('trial_id', 'block_id', 'room', 'condition', 'repetition', 'team', 'assignment_id', 'rerun_of', 'rerun_reason')},
               'launched': launch is not None, 'launched_at': launch['at'] if launch else None,
               'unlaunched_reason': (campaign_stop or {}).get('reason', 'not_started_or_interrupted') if not launch else None,
               'unlaunched_observed_at': (campaign_stop or {}).get('at', registration['created_at']) if not launch else None,
               'engine_outcome': 'unknown', 'stop_reason': 'missing_outcome' if launch else 'unlaunched',
               'execution_stop_reason': None, 'recording_stop_reason': None, 'cleanup_status': None,
               'operational_success': None, 'artifact_available': False, 'artifact_issues': [],
               'elapsed_seconds': None, 'execution_elapsed_seconds': None, 'turns': None, 'energy': None,
               'scores': None, 'completed': None, 'run_id': None,
               'artifact_directory': 'trials/'+trial_id,
               'estimated_cost_usd': None, 'known_usage_estimated_usd': None, 'retained_estimate_usd': None}
        row.update({key+'_decimal':None for key in BUDGET_MONEY})
        for key in BUDGET_COUNTS:
            row[key] = None
        data, issues = _artifacts(root, trial, registration) if launch else ({}, [])
        row['artifact_issues'] = issues
        row['artifact_available'] = bool(launch and not issues)
        result = receipt.get('result') if receipt else None
        receipt_invalid = False
        if result is not None and not _valid_summary(result):
            issues.append('ledger_result_invalid')
            receipt_invalid = True
            result = None
        if result is None:
            result = data.get('result')
        if receipt:
            row.update(stop_reason=receipt['stop_reason'], cleanup_status=receipt['cleanup_status'],
                       execution_stop_reason=receipt['execution_stop_reason'],
                       recording_stop_reason=receipt['recording_stop_reason'],
                       elapsed_seconds=receipt['elapsed_seconds'], run_id=receipt['run_id'])
            if not receipt_invalid:
                row['operational_success'] = (bool(result['win'] and result['stop_reason'] == 'victory' and
                                                    receipt['stop_reason'] == 'victory' and receipt['cleanup_status'] == 'ok')
                                               if result else False if receipt['stop_reason'] != 'victory' else None)
        elif result and result['stop_reason'] != 'victory':
            row['stop_reason'] = result['stop_reason']
            row['operational_success'] = False
        if result:
            row.update(engine_outcome='win' if result['win'] else 'defeat' if result['loss'] else 'nonterminal',
                       turns=result['turns'], completed=result['completed'], energy=result.get('energy'), scores=result['scores'])
            row.update({key:result['budget'].get(key) for key in BUDGET_COUNTS+BUDGET_MONEY})
            for key in BUDGET_MONEY:
                row[key+'_decimal']=result['budget'].get(key+'_decimal')
        if receipt and data.get('result') and receipt.get('result') != data['result']:
            issues.append('ledger_artifact_disagreement')
            if receipt.get('result') is not None:
                row.update(operational_success=None,engine_outcome='unknown')
            elif row['operational_success'] is True:
                row['operational_success']=None
        if receipt and data.get('provenance'):
            native=data['provenance'];life=native['lifecycle']
            if receipt['run_id']!=native['run_id']:issues.append('run_id_mismatch')
            if receipt['recording_stop_reason']!=life['stop_reason']:issues.append('recording_stop_mismatch')
            if receipt['execution_stop_reason']!=life['execution_stop_reason']:issues.append('execution_stop_mismatch')
        row['artifact_available'] = bool(launch and not issues)
        provenance = data.get('provenance')
        if provenance:
            row['execution_elapsed_seconds'] = provenance['lifecycle']['elapsed_seconds']
        if data.get('calls') is not None:
            for call in data['calls']:
                attempt_rows.append({'trial_id': trial_id, 'room':trial['room'], 'team': trial['team'], 'condition': trial['condition'],
                                     **{k: call.get(k) for k in ('role', 'turn', 'phase', 'attempt', 'status', 'latency_seconds',
                                                               'reservation_quote_usd', 'settlement_basis', 'settled_amount_usd')},
                                     'status': call['status'] if call['status'] in ATTEMPT_STATUSES else 'unknown_status',
                                     'usage': _project_usage(call.get('usage'))})
        row['fallbacks'] = (sum(status != 'ok' for phase in data['phases'] for status in phase['statuses'].values())
                            if 'phases' in data else None)
        row['engine_illegal_actions'] = (sum(code not in ('wait', 'applied', 'already_done', 'overload')
                                            for turn in data['replay'] for code in turn['action_outcomes'].values())
                                       if 'replay' in data else None)
        rows.append(row)
    counts = _counts(rows)
    def event_total(event_names, key):
        return money_total((amount(event,key) if key.endswith('_usd') else Decimal(event.get(key,0)))
                           for event in events if event['event'] in event_names)
    calls_reserved = int(event_total(('block_reserved',), 'reserved_calls'))
    calls_released = int(event_total(('trial_finished', 'block_released'), 'released_calls'))
    calls_accounted = int(event_total(('trial_finished',), 'accounted_calls'))
    dollars_reserved = event_total(('block_reserved',), 'reserved_estimated_usd')
    dollars_released = event_total(('trial_finished', 'block_released'), 'released_estimated_usd')
    dollars_accounted = event_total(('trial_finished',), 'accounted_estimated_usd')
    balance_calls=calls_reserved-calls_released-calls_accounted
    balance_usd=difference(difference(dollars_reserved,dollars_released),dollars_accounted)
    uncertainty=money_total(Decimal(str(math.ulp(float(event[key])))) for event in events
        if event['event'] in ('block_reserved','block_released','trial_finished')
        for key in ('reserved_estimated_usd','released_estimated_usd','accounted_estimated_usd')
        if key in event and key+'_decimal' not in event)
    if balance_calls:anomalies.append('unbalanced_call_reservations')
    if abs(balance_usd)>uncertainty:anomalies.append('unbalanced_estimate_reservations')
    settlement_uncertainty=money_total((uncertainty,Decimal(str(math.ulp(float(campaign_stop['accounted_estimated_usd']))))
        if campaign_stop and 'accounted_estimated_usd_decimal' not in campaign_stop else Decimal(0)))
    if campaign_stop and (campaign_stop['accounted_calls']!=calls_accounted or
            abs(difference(amount(campaign_stop,'accounted_estimated_usd'),dollars_accounted))>settlement_uncertainty):
        anomalies.append('campaign_settlement_mismatch')
    complete = len(launched)==len(finished) and counts['launched'] == counts['planned'] and counts['unknown_operational'] == 0 and not anomalies and bool(
        campaign_stop and campaign_stop['reason'] == 'completed')
    eligible = complete and all(r['artifact_available'] for r in rows) and bool(
        campaign_start and campaign_start['registration_matches']) and registration['frozen']['source']['status'] == 'clean' and registration['frozen']['environment']['value']['status'] == 'complete'
    cells = defaultdict(list)
    for row in rows:
        cells[(row['room'], row['team'], row['assignment_id'], row['condition'])].append(row)
    cell_reports = [{'room': key[0], 'team': key[1], 'assignment_id': key[2], 'condition': key[3],
                     'deterministic_control': key[1] in ('scripted', 'wait'), **_summary(group)}
                    for key, group in sorted(cells.items())]
    arm_groups = defaultdict(list)
    for cell in cell_reports:
        arm_groups[(cell['room'], cell['team'], cell['condition'])].append(cell)
    equal_weight_arms = []
    for (room, team, condition), group in sorted(arm_groups.items()):
        values = [cell['operational_success'] for cell in group]
        equal_weight_arms.append({'room': room, 'team': team, 'condition': condition,
            'assignment_count': len(values), 'weights': 'equal_per_prespecified_assignment',
            'observed_rate': sum(v['rate'] for v in values)/len(values) if all(v['rate'] is not None for v in values) else None,
            'launched_bounds':[sum(v['launched_bounds'][i] for v in values)/len(values) for i in (0,1)] if all(v['launched_bounds'] is not None for v in values) else None,
            'all_planned_bounds': [sum(v['all_planned_bounds'][i] for v in values)/len(values) for i in (0, 1)]})
    contrasts = []
    analysis_source = collect_source(ROOT)
    inference_eligible = eligible and analysis_source == registration['frozen']['source']
    if spec.stage == 'confirmatory' and inference_eligible:
        cohorts = defaultdict(list)
        for row in rows:
            if row['team'] in ('models', 'uniform'):
                cohorts[(row['room'], row['team'])].append(row)
        for (room, team), cohort in sorted(cohorts.items()):
            for comparison in ('disabled', 'reduced', 'withheld', 'no_images'):
                blocks = defaultdict(dict)
                for row in cohort:
                    blocks[(row['assignment_id'], row['block_id'])][row['condition']] = int(row['operational_success'])
                strata = defaultdict(list)
                for (assignment, block_id), arms in sorted(blocks.items()):
                    strata[assignment].append((arms['full'], arms[comparison]))
                if any(len(group) != 30 for group in strata.values()):
                    raise CampaignError('Incomplete prespecified repetition blocks')
                contrasts.append({'room': room, 'team': team, 'contrast': 'full-minus-'+comparison,
                                  'exploratory': comparison != 'disabled', **paired_bootstrap(strata)})
    attempts = Counter(call['status'] for call in attempt_rows)
    # Cross-room summaries remain descriptive; inference stays within each room.
    catalog=registration['frozen'].get('catalog')
    definitions={r['id']:r for r in catalog['value']['rooms']} if catalog else {}
    def labels(room_id):
        room=definitions.get(room_id,{'family':'crossing','split':'development','version':1})
        return {'family':room['family'],'split':room['split'],'room_version':room['version'],
                'catalog_sha256':catalog['sha256'] if catalog else None}
    for collection in (rows,cell_reports,equal_weight_arms,contrasts,attempt_rows):
        for row in collection:
            if 'room' in row:row.update(labels(row['room']))
    descriptive={}
    def descriptive_summary(group):
        summary=_summary(group)
        summary['operational_success'].pop('wilson_95')
        return summary
    for dimension in ('family','split'):
        groups=defaultdict(list)
        for row in rows:groups[row[dimension]].append(row)
        descriptive[dimension+'_summaries']=[{dimension:key,'interpretation':'Descriptive only; rooms are curated, not independent draws from a task population.',**descriptive_summary(group)} for key,group in sorted(groups.items())]
    report = {'schema_version': 2, 'analysis_version': 2, 'analyzed_at': now(),
              'analysis_source': analysis_source, 'registration_sha256': registration['sha256'],
              'experiment_id': registration['experiment_id'], 'stage': spec.stage,
              'registration': registration, 'completion_status': 'complete' if complete else 'incomplete',
              'cohort_eligible': eligible,
              'confirmatory_eligible': bool(spec.stage == 'confirmatory' and inference_eligible),
              'counts': counts, 'overall': (descriptive_summary(rows) if len({row['room'] for row in rows})>1 else _summary(rows)), 'cells': cell_reports,
              'equal_weight_arm_summaries': equal_weight_arms,
              'overall_interpretation': 'Descriptive accounting across the full schedule; comparisons use room/team/assignment cells and registered equal weights.',
              'contrasts': contrasts, 'trials': rows, 'attempts': attempt_rows,**descriptive,
              'catalog':catalog,
              'attempt_metrics': {'observed_records': len(attempt_rows), 'statuses': dict(attempts),
                                  'retries': sum(c['attempt'] > 1 for c in attempt_rows),
                                  'latency_seconds': distribution([c['latency_seconds'] for c in attempt_rows]),
                                  'per_role_phase_status': dict(Counter(c['role']+'/'+c['phase']+'/'+c['status'] for c in attempt_rows))},
              'campaign_stop': campaign_stop, 'anomalies': anomalies,
              'campaign_accounting': {
                  'configured_call_ceiling': spec.campaign_max_calls,
                  'configured_estimated_usd_ceiling': spec.campaign_max_estimated_cost_usd,
                  'planned_maximum_exposure': registration['planned_exposure'],
                  'calls_reserved_total': calls_reserved, 'calls_released_total': calls_released,
                  'calls_accounted': calls_accounted,
                  'reservation_balance_calls': calls_reserved-calls_released-calls_accounted,
                  'estimated_usd_reserved_total': float(dollars_reserved),
                  'estimated_usd_released_total': float(dollars_released),
                  'estimated_usd_accounted': float(dollars_accounted),
                  'reservation_balance_estimated_usd': float(balance_usd),
                  'reservation_balance_estimated_usd_decimal':str(balance_usd),
                  'legacy_rounding_uncertainty_usd':float(uncertainty),
                  'legacy_settlement_rounding_uncertainty_usd':float(settlement_uncertainty),
                  'launched_without_finished_receipt': len(launched)-len(finished),
                  'interpretation': 'An interrupted ledger can retain reservations; balances beyond the reported legacy rounding uncertainty expose unmatched exposure. Monetary reservations are local estimates, not invoices.'},
              'limitations': ['No provider ranking or task-population generalization follows from this finite curated catalog.',
                              'Pilot and diagnostic runs are not confirmatory estimates.',
                              'Missing and unlaunched outcomes are retained; no complete-pair subset substitutes for the cohort.',
                              'Known setup failures are zero operational successes, not engine defeats.',
                              'Costs are local estimates; null amounts are unavailable, never free.',
                              'Provider aliases/backend revisions and remote randomness are not attested.',
                              'Unsigned files and fingerprints establish consistency, not authenticity.']}
    if not inference_eligible:
        report['limitations'].append('Incomplete or ineligible cohort: report descriptive rates/bounds without confirmatory inference.')
    report['attempt_metrics']['usage_counter_origins'] = dict(Counter(
        key+'/'+entry['state'] for c in attempt_rows for key, entry in (c.get('usage') or {}).get('source_usage', {}).items()))
    return report


def write_report(report: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out / 'report.json', report)
    for name in ('trials', 'cells', 'attempts'):
        rows = report[name]
        fields = list(rows[0]) if rows else {'trials':['trial_id'],'cells':['room','team','condition'],
                                            'attempts':['trial_id','role','turn','phase','attempt','status']}[name]
        target=out/(name+'.csv');temporary=target.with_suffix('.csv.tmp')
        def cell(value):
            if isinstance(value,(dict,list)):return json.dumps(value,ensure_ascii=True,allow_nan=False)
            if isinstance(value,str) and (value.startswith(('\t','\r','\n')) or value.lstrip().startswith(('=','+','-','@'))):
                return "'"+value
            return value
        try:
            with temporary.open('w',encoding='utf-8',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=fields,lineterminator='\n',quoting=csv.QUOTE_ALL);writer.writeheader()
                writer.writerows({k:cell(v) for k,v in row.items()} for row in rows)
                handle.flush();os.fsync(handle.fileno())
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        with (out / (name+'.csv')).open(encoding='utf-8', newline='') as handle:
            if len(list(csv.DictReader(handle))) != len(rows):
                raise CampaignError('Report readback failed')
    if read_json(out / 'report.json') != report:
        raise CampaignError('Report readback failed')
