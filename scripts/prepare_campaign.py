"""Offline Phase-2 candidate specs and conservative LOCAL reservation worksheet.

This command cannot register campaigns, construct provider agents, read credentials,
or execute trials. Its synthetic request envelopes are never player inputs.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
from decimal import Decimal, ROUND_CEILING
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from parallax_relay.budget import Budget
from parallax_relay.campaign import frozen_inputs
from parallax_relay.campaign_models import CampaignSpec, assignments, schedule, trial_exposure
from parallax_relay.conditions import CONDITIONS
from parallax_relay.config import MatchSettings, Rates
from parallax_relay.prompts import SYSTEM_RULES
from parallax_relay.protocol import (AgentRequest, ChatMessage, Observation, ROLES,
    MAX_MESSAGE_CHARS, MAX_NOTES_CHARS, MAX_REPLY_CHARS, response_schema)
from parallax_relay.provenance import canonical_hash
from parallax_relay.rooms import rooms
from parallax_relay.state import initial_world, public_hud

SOURCES = ROOT / 'configs/campaign_preparation_sources.json'
PROFILE = ROOT / 'configs/live_smoke.json'
# Public events have fixed engine templates with bounded role/kind/numeric fields.
# 128 ASCII bytes exceeds every current legal engine event (longest < 100).
EVENT_BYTES = 128
UNICODE = '\U0010ffff'  # 12 ASCII bytes per character after ensure_ascii JSON.


def load_inputs():
    sources = json.loads(SOURCES.read_text(encoding='utf-8'))
    profile = json.loads(PROFILE.read_text(encoding='utf-8'))
    if sources['schema_version'] != 1 or date.fromisoformat(sources['verified_date']) > date.today():
        raise ValueError('Invalid documentation verification date')
    common = {'communication_rounds': 2, 'max_attempts': 2,
        'timeout_seconds': 60.0, 'max_output_tokens': 4096, 'history_turns': 4,
        'retry_delay_seconds': 0.5, 'max_consecutive_failures': 3, 'image_token_reserve': 8192}
    if any(profile['config']['match'].get(k) != v for k, v in common.items()):
        raise ValueError('Smoke profile differs from approved common limits')
    roster = []
    for role in ROLES:
        player = profile['config']['players'][role]
        model = profile['models'][role]
        identity = f"{player['provider']}/{model}"
        source = sources['models'][identity]
        if source['pricing'] != player['pricing']:
            raise ValueError('Documentation rates and selected roster differ; reverify sources')
        roster.append(dict(provider=player['provider'], model=model,
                           api_key_env=player['api_key_env'], pricing=player['pricing']))
    if [(p['provider'], p['model']) for p in roster] != [
            ('openai', 'gpt-6-luna'), ('openai', 'gpt-6-luna'), ('gemini', 'gemini-3.5-flash-lite')]:
        raise ValueError('This worksheet requires the explicitly approved roster')
    return sources, profile, roster


def envelope(role, turn, phase, condition, history_turns):
    """A dominating size envelope, deliberately not a reachable simultaneous state.

    Keep the real HUD shape, inflate all bounded numbers and public events, use
    six maximal escaped messages per history, and add a full MAX_REPLY_CHARS of
    action padding to cover even schema-valid enormous integer parameters.
    Extra history padding is a worksheet device, never an orchestration change.
    """
    huds = []
    for room in rooms():
        if room.width > 13 or room.deadline != 12 or room.energy + len(room.cells) * room.cell_value > 99:
            raise ValueError('Room bounds changed; requalify the worksheet')
        hud = public_hud(initial_world(room.id), role)
        for key in ('turn', 'max_turns', 'lane_width', 'shared_energy', 'shared_coolant', 'your_x'):
            hud[key] = -999
        hud['teammate_positions'] = {r: -999 for r in ROLES if r != role}
        hud['recent_events'] = ['E' * EVENT_BYTES] * 12
        huds.append(hud)
    hud = max(huds, key=lambda h: len(json.dumps(h, ensure_ascii=True)))
    messages = tuple(ChatMessage(r, 11, p, UNICODE * MAX_MESSAGE_CHARS)
                     for p in ('broadcast', 'negotiate') for r in ROLES)
    history = [{
        'turn': 11, 'your_observation': hud,
        'public_messages': [asdict(m) for m in messages] if CONDITIONS[condition].deliver_messages else [],
        'your_action': {'kind': 'REROUTE', 'direction': 0, 'steps': 0},
        'bounded_action_padding': '9' * MAX_REPLY_CHARS,
        'events': ['E' * EVENT_BYTES] * 12,
    }] * min(turn, history_turns)
    current_messages = messages[:3] if phase == 'negotiate' else messages if phase == 'commit' else ()
    if not CONDITIONS[condition].deliver_messages:
        current_messages = ()
    return AgentRequest(Observation(role, turn, json.dumps(hud), b''), phase,
        messages=current_messages, history_json=json.dumps(history),
        private_notes=UNICODE * MAX_NOTES_CHARS if turn else '',
        # Retry repair is fixed ASCII text under 256 bytes; the initial phase
        # reservation itself has no repair, so padding this is conservative.
        repair='R' * 256, max_output_tokens=4096,
        include_image=CONDITIONS[condition].include_image, condition=condition)


def worksheet(spec):
    rows = []
    maximum_input = 0
    bound = Decimal(0)
    # No model agent or execution function is imported or called. Exercise the
    # real phase reservation and unknown-usage settlement path on size envelopes.
    for assignment in assignments(spec):
        rates = {r: Rates.model_validate(p['pricing']) for r, p in assignment['players'].items()}
        for condition in spec.conditions:
            settings = MatchSettings.model_validate({**spec.match.model_dump(),
                'max_estimated_cost_usd': None})
            budget = Budget(settings, rates)
            for turn in range(settings.max_turns):
                for phase in CONDITIONS[condition].phases:
                    requests = {r: envelope(r, turn, phase, condition, settings.history_turns) for r in ROLES}
                    input_sizes = {r: len((SYSTEM_RULES + req.prompt_text() +
                        json.dumps(response_schema(phase))).encode('utf-8')) +
                        (settings.image_token_reserve if req.include_image else 0) + 2048
                        for r, req in requests.items()}
                    maximum_input = max(maximum_input, *input_sizes.values())
                    tickets = budget.reserve_phase(requests)
                    quote = sum((t.quote for t in tickets.values()), Decimal(0)) * settings.max_attempts
                    rows.append({'assignment': assignment['assignment_id'], 'condition': condition,
                        'turn': turn, 'phase': phase, 'input_quote_tokens': input_sizes,
                        'whole_phase_retry_quote_usd': float(quote)})
                    for ticket in tickets.values():
                        for _ in range(settings.max_attempts):
                            ticket.start()
                            ticket.settle(None)
                        ticket.release()
            bound = max(bound, budget.spent)
    if maximum_input >= 272000:
        raise ValueError('Envelope exceeds verified OpenAI short-context pricing; reverify before preparation')
    guard = (bound * Decimal('1.10')).quantize(Decimal('.01'), rounding=ROUND_CEILING)
    return {'maximum_request_input_quote_tokens': maximum_input,
        'retained_quote_bound_usd': float(bound), 'match_guard_usd': float(guard),
        'phase_retry_attempts': 3 * spec.match.max_attempts,
        'guard_margin': '10 percent, rounded upward to the next cent',
        'image_token_reserve': spec.match.image_token_reserve,
        'output_token_allowance_each_attempt': spec.match.max_output_tokens,
        'event_ascii_byte_bound': EVENT_BYTES, 'event_count_bound': 12,
        'history_action_padding_bytes_each_turn': MAX_REPLY_CHARS,
        'cost_is_estimate_not_billing_guarantee': True, 'phase_quotes': rows}


def build_bundle():
    sources, profile, roster = load_inputs()
    specs, stages = {}, {}
    for stage, turns, repetitions in (('qualification', 2, 1), ('pilot', 12, 5), ('confirmatory', 12, 30)):
        match = dict(profile['config']['match'])
        match.update(max_turns=turns, max_calls=36 if stage == 'qualification' else 216,
                     max_estimated_cost_usd=1.0)
        spec = CampaignSpec.model_validate({
            'schema_version': 2, 'protocol_version': 2,
            'stage': 'diagnostic' if stage == 'qualification' else stage, 'mode': 'live',
            'rooms': ['split_span'] if stage == 'qualification' else
                     [r.id for r in rooms(split='development' if stage == 'pilot' else 'held_out')],
            'policies': [] if stage == 'qualification' else ['scripted', 'wait', 'uniform'],
            'roster': roster, 'conditions': list(CONDITIONS), 'repetitions': repetitions,
            'match': match, 'campaign_max_calls': 10**9,
            'campaign_max_estimated_cost_usd': 10**9,
            'scheduler_seed': 0, 'min_trial_interval_seconds': 1.0,
        })
        sheet = worksheet(spec) if stage != 'confirmatory' else stages['pilot']['worksheet']
        trials = schedule(spec)
        model_count = sum(t['team'] == 'models' for t in trials)
        calls = sum(trial_exposure(spec, trial)[0] for trial in trials)
        provider_attempts = sum(trial_exposure(spec, trial)[0] for trial in trials if trial['team'] == 'models')
        value = spec.model_dump(mode='json')
        value['match']['max_estimated_cost_usd'] = sheet['match_guard_usd']
        value['campaign_max_calls'] = calls
        value['campaign_max_estimated_cost_usd'] = float(Decimal(str(sheet['match_guard_usd'])) * model_count)
        value = CampaignSpec.model_validate(value).model_dump(mode='json')
        specs[stage + '.json'] = value
        stages[stage] = {'spec_file': stage + '.json', 'spec_sha256': canonical_hash(value),
            'trials': len(trials), 'model_trials': model_count, 'baseline_trials': len(trials) - model_count,
            'assignments': len(assignments(spec)), 'max_calls': calls,
            'max_provider_attempts': provider_attempts, 'worksheet': sheet,
            'campaign_estimate_guard_usd': value['campaign_max_estimated_cost_usd']}
    frozen = frozen_inputs(CampaignSpec.model_validate(specs['pilot.json']))
    receipt = {'schema_version': 1, 'kind': 'offline_preparation_candidate',
        'spending_authorized': False, 'registration_created': False,
        'sources': sources, 'source_record_sha256': canonical_hash(sources),
        'smoke_profile_sha256': canonical_hash(profile),
        'source': frozen['source'], 'environment': frozen['environment'],
        'catalog_sha256': frozen['catalog']['sha256'], 'frozen_inputs_sha256': canonical_hash(frozen),
        'stages': stages,
        'remaining_gates': ['Integrate Phase1 and freeze clean source/environment, then regenerate and check.',
            'Review a current numeric Q receipt and obtain separate Q spending approval before registration/run.',
            'Complete Q model/arm compatibility review before requesting separate pilot spending approval.',
            'Complete an eligible pilot before confirmation registration; preserve all frozen pilot inputs and obtain separate confirmation spending approval.']}
    return specs, receipt


def write_bundle(out):
    specs, receipt = build_bundle()
    out.mkdir(parents=True, exist_ok=False)
    for filename, data in {**specs, 'receipt.json': receipt}.items():
        path = out / filename
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if json.loads(path.read_text(encoding='utf-8')) != data:
            raise ValueError('Candidate write/readback mismatch')
    check_bundle(out, require_clean=False)
    return receipt


def check_bundle(bundle, require_clean=False):
    specs, expected = build_bundle()
    receipt = json.loads((bundle / 'receipt.json').read_text(encoding='utf-8'))
    if receipt != expected:
        raise ValueError('Receipt differs from current source/environment/inputs or worksheet')
    for filename, value in specs.items():
        if json.loads((bundle / filename).read_text(encoding='utf-8')) != value:
            raise ValueError('Candidate spec differs from qualified design')
    if require_clean and (receipt['source']['status'] != 'clean' or
                         receipt['environment']['value']['status'] != 'complete'):
        raise ValueError('Clean source and complete environment required for frozen review')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--out', type=Path, required=True)
    check = sub.add_parser('check')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--require-clean', action='store_true')
    args = parser.parse_args(argv)
    try:
        receipt = write_bundle(args.out) if args.command == 'prepare' else check_bundle(args.bundle, args.require_clean)
        print(json.dumps({'kind': receipt['kind'], 'spending_authorized': False,
            'source': receipt['source'], 'receipt_sha256': canonical_hash(receipt),
            'guards_usd': {stage: row['campaign_estimate_guard_usd'] for stage, row in receipt['stages'].items()}}))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('Preparation failed: existing destination, invalid/drifted inputs, receipt, or worksheet; inspect offline.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
