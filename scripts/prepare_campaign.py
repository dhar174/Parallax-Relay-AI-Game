"""Offline campaign candidate specs and conservative LOCAL reservation assessments.

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
from parallax_relay.config import GameConfig, MatchSettings, Rates
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


def read_json(path):
    """Reject ambiguous objects before validating or hashing any input."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON object key')
            result[key] = value
        return result
    def finite_constant(_):
        raise ValueError('Nonfinite JSON number')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object,
                      parse_constant=finite_constant)


def load_inputs():
    sources = read_json(SOURCES)
    profile = read_json(PROFILE)
    if (type(sources['schema_version']) is not int or sources['schema_version'] != 1 or
            date.fromisoformat(sources['verified_date']) > date.today()):
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


def quotation_rates(players, *, openai_input_rate=None):
    """Scenario-only prices; never mutate the configured roster or wire options."""
    rates = {}
    for role, player in players.items():
        value = dict(player['pricing'])
        if player['provider'] == 'openai' and openai_input_rate is not None:
            value['input_per_million'] = openai_input_rate
        rates[role] = Rates.model_validate(value)
    return rates


def worksheet(spec, *, openai_input_rate=None):
    rows = []
    maximum_input = 0
    bound = Decimal(0)
    # No model agent is constructed or trial execution function called. Exercise the
    # real phase reservation and unknown-usage settlement path on size envelopes.
    for assignment in assignments(spec):
        rates = quotation_rates(assignment['players'], openai_input_rate=openai_input_rate)
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
        'openai_short_context_threshold_tokens': 272000,
        'event_ascii_byte_bound': EVENT_BYTES, 'event_count_bound': 12,
        'history_action_padding_bytes_each_turn': MAX_REPLY_CHARS,
        'cost_is_estimate_not_billing_guarantee': True, 'phase_quotes': rows}


def _build_standard_bundle():
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
        sheet = (worksheet(spec) if stage != 'confirmatory' else
                 stages['pilot']['nominal_configured_rate_scenario']['worksheet'])
        write_rate = sources['models']['openai/gpt-6-luna']['cache_write_input_per_million']
        write_sheet = (worksheet(spec, openai_input_rate=write_rate) if stage != 'confirmatory' else
                       stages['pilot']['all_openai_input_at_cache_write_rate']['worksheet'])
        trials = schedule(spec)
        model_count = sum(t['team'] == 'models' for t in trials)
        calls = sum(trial_exposure(spec, trial)[0] for trial in trials)
        provider_attempts = sum(trial_exposure(spec, trial)[0] for trial in trials if trial['team'] == 'models')
        value = spec.model_dump(mode='json')
        selected_guard = max(sheet['match_guard_usd'], write_sheet['match_guard_usd'])
        value['match']['max_estimated_cost_usd'] = selected_guard
        value['campaign_max_calls'] = calls
        value['campaign_max_estimated_cost_usd'] = float(Decimal(str(selected_guard)) * model_count)
        value = CampaignSpec.model_validate(value).model_dump(mode='json')
        specs[stage + '.json'] = value
        stages[stage] = {'spec_file': stage + '.json', 'spec_sha256': canonical_hash(value),
            'trials': len(trials), 'model_trials': model_count, 'baseline_trials': len(trials) - model_count,
            'assignments': len(assignments(spec)), 'max_calls': calls,
            'max_provider_attempts': provider_attempts,
            'match_estimate_guard_usd': selected_guard,
            'selected_guard_basis': 'Maximum of nominal and all-OpenAI-input-cache-write scenario margin guards; configured token rates unchanged.',
            'nominal_configured_rate_scenario': {
                'worksheet': sheet,
                'campaign_guard_usd': float(Decimal(str(sheet['match_guard_usd'])) * model_count)},
            'all_openai_input_at_cache_write_rate': {
                'assumption': 'All OpenAI input priced at the default 30-minute cache-write rate; Gemini/output rates unchanged.',
                'openai_input_per_million': write_rate, 'actual_cache_activity': 'unknown',
                'configured_runtime_rates_changed': False, 'worksheet': write_sheet,
                'campaign_guard_usd': float(Decimal(str(write_sheet['match_guard_usd'])) * model_count)},
            'campaign_estimate_guard_usd': value['campaign_max_estimated_cost_usd']}
    frozen = frozen_inputs(CampaignSpec.model_validate(specs['pilot.json']))
    receipt = {'schema_version': 1, 'kind': 'offline_preparation_candidate',
        'spending_authorized': False, 'registration_created': False,
        'sources': sources, 'source_record_sha256': canonical_hash(sources),
        'smoke_profile_sha256': canonical_hash(profile),
        'source': frozen['source'], 'environment': frozen['environment'],
        'pricing_limitations': [
            'Runtime Budget prices OpenAI input at configured .10/M and does not distinguish cache-write charges.',
            'Implicit caching/default 30-minute writes can bill OpenAI input at .125/M; actual cache activity is unknown.',
            'Selected runtime guards include the all-input-write scenario; configured token rates and cache controls remain unchanged. Neither scenario is an invoice ceiling.'],
        'catalog_sha256': frozen['catalog']['sha256'], 'frozen_inputs_sha256': canonical_hash(frozen),
        'stages': stages,
        'operational_planning': {
            'status': 'not_started', 'offline_diagnostic_evidence': 'not_started',
            'time_projection': 'not_started', 'storage_projection': 'not_started',
            'disk_free_check': 'not_started', 'provider_account_quota': 'unverified',
            'planned_q_output_paths': 'not_started', 'exact_q_command': 'not_started',
            'launch_checkpoint': 'not_started', 'heartbeat': 'not_started'},
        'remaining_gates': ['Integrate Phase1 and freeze clean source/environment, then regenerate and check.',
            'Review a current numeric Q receipt and obtain separate Q spending approval before any live execution.',
            'Complete Q model/arm compatibility review before requesting separate pilot spending approval.',
            'Complete an eligible pilot before confirmation registration; preserve all frozen pilot inputs and obtain separate confirmation spending approval.']}
    return specs, receipt


def _exploratory_inputs():
    """Check nominal source inputs separately from the profile's safety rates."""
    sources, smoke, roster = load_inputs()
    if (type(smoke['schema_version']) is not int or smoke['schema_version'] != 1 or
            date.fromisoformat(smoke['verified_date']) > date.today()):
        raise ValueError('Invalid smoke profile verification record')
    GameConfig.model_validate(smoke['config'], strict=True)
    common = {'communication_rounds': 2, 'max_attempts': 2,
        'timeout_seconds': 60.0, 'max_output_tokens': 4096, 'history_turns': 4,
        'retry_delay_seconds': 0.5, 'max_consecutive_failures': 3, 'image_token_reserve': 8192}
    if canonical_hash({k: smoke['config']['match'].get(k) for k in common}) != canonical_hash(common):
        raise ValueError('Smoke profile differs from approved typed common limits')
    approved = [dict(provider=provider, model=model, api_key_env=key, pricing=pricing)
        for provider, model, key, pricing in (
            ('openai', 'gpt-6-luna', 'OPENAI_API_KEY', {'input_per_million': 0.1, 'output_per_million': 0.5}),
            ('openai', 'gpt-6-luna', 'OPENAI_API_KEY', {'input_per_million': 0.1, 'output_per_million': 0.5}),
            ('gemini', 'gemini-3.5-flash-lite', 'GEMINI_API_KEY', {'input_per_million': 0.3, 'output_per_million': 2.5}))]
    if (canonical_hash(roster) != canonical_hash(approved) or
            canonical_hash(sources['models']['openai/gpt-6-luna']['cache_write_input_per_million']) != canonical_hash(0.125)):
        raise ValueError('Exploratory source rates or credential binding names changed')
    return sources, smoke


def _envelope_summary(sheet):
    # Retain the quantified evidence without duplicating thousands of synthetic
    # phase rows in a candidate receipt. These are bounds, not expected invoices.
    return {key: value for key, value in sheet.items() if key != 'phase_quotes'}


def _build_exploratory_bundle():
    from parallax_relay.exploratory import PROFILE_ID, GEMINI_ROLE_BY_ROOM, profile_spec, profile_analysis
    sources, smoke = _exploratory_inputs()
    specs, stages, frozen_stages = {}, {}, []
    pilot_spec = None
    for stage, counts in (('pilot', (60, 15, 45, 10368, 2592, 3.75)),
                          ('validation', (120, 30, 90, 20736, 5184, 7.5))):
        spec = CampaignSpec.model_validate(profile_spec(stage), strict=True)
        value = spec.model_dump(mode='json')
        trials = schedule(spec)
        paid = [trial for trial in trials if trial['team'] == 'models']
        calls = sum(trial_exposure(spec, trial)[0] for trial in trials)
        paid_calls = sum(trial_exposure(spec, trial)[0] for trial in paid)
        cap = sum((Decimal(str(trial_exposure(spec, trial)[1])) for trial in paid), Decimal(0))
        if ((len(trials), len(paid), len(trials) - len(paid), calls, paid_calls, float(cap)) != counts or
                cap != Decimal(str(spec.campaign_max_estimated_cost_usd)) or
                spec.match.max_estimated_cost_usd != 0.25):
            raise ValueError('Exploratory schedule or guard arithmetic differs from approved limits')
        frozen = frozen_inputs(spec)
        if (set(frozen['inputs']) != {room.id for room in rooms()} or
                canonical_hash(frozen['analysis']) != canonical_hash(profile_analysis())):
            raise ValueError('Exploratory frozen inputs must cover all rooms and descriptive analysis')
        frozen_stages.append(frozen)
        specs[stage + '.json'] = value
        stages[stage] = {'spec_file': stage + '.json', 'spec_sha256': canonical_hash(value),
            'frozen_inputs_sha256': canonical_hash(frozen), 'trials': len(trials),
            'model_trials': len(paid), 'baseline_trials': len(trials) - len(paid),
            'assignments_per_room': 1, 'max_calls': calls, 'max_provider_attempts': paid_calls,
            'match_estimate_guard_usd': 0.25, 'campaign_estimate_guard_usd': float(cap),
            'baseline_provider_cost_usd': 0.0}
        if stage == 'pilot':
            pilot_spec = spec
    if canonical_hash(frozen_stages[0]) != canonical_hash(frozen_stages[1]):
        raise ValueError('Pilot and validation must freeze identical source/environment/inputs')
    frozen = frozen_stages[0]
    conservative = _envelope_summary(worksheet(pilot_spec))
    nominal = _envelope_summary(worksheet(pilot_spec, openai_input_rate=0.1))
    price_inputs = {'nominal_openai_input_per_million': 0.1,
        'safety_openai_input_per_million': 0.125, 'openai_output_per_million': 0.5,
        'gemini_input_per_million': 0.3, 'gemini_output_per_million': 2.5,
        'runtime_rate_basis': 'All OpenAI input priced at the default 30-minute cache-write rate; Gemini/output rates unchanged.',
        'actual_cache_activity': 'unknown', 'source_record_uses_nominal_rates': True,
        'runtime_uses_safety_rates': True}
    receipt = {'schema_version': 1, 'kind': 'offline_preparation_candidate',
        'profile_id': PROFILE_ID, 'evidence_class': 'exploratory', 'confirmatory_eligible': False,
        'spending_authorized': False, 'registration_created': False,
        'credential_resolution_performed': False, 'provider_clients_constructed': False,
        'sources': sources, 'source_record_sha256': canonical_hash(sources),
        'smoke_profile_sha256': canonical_hash(smoke), 'price_inputs': price_inputs,
        'price_inputs_sha256': canonical_hash(price_inputs),
        'source': frozen['source'], 'source_sha256': canonical_hash(frozen['source']),
        'environment': frozen['environment'], 'environment_sha256': frozen['environment']['sha256'],
        'catalog_sha256': frozen['catalog']['sha256'], 'frozen_inputs_sha256': canonical_hash(frozen),
        'analysis': profile_analysis(), 'gemini_role_by_room': dict(GEMINI_ROLE_BY_ROOM),
        'stages': stages,
        'limits': {'match_guard_usd': 0.25, 'full_five_arm_model_block_guard_usd': 1.25,
            'new_campaign_guards_usd': 11.25, 'prior_q_allowance_usd': 0.25,
            'combined_local_guard_allowance_usd': 11.5, 'user_combined_budget_usd': 20.0,
            'cost_is_estimate_not_billing_guarantee': True},
        'guard_feasibility': {'match_guard_usd': 0.25,
            'conservative_envelope': conservative, 'nominal_rate_comparison': nominal,
            'binding_possible': conservative['retained_quote_bound_usd'] > 0.25,
            'full_match_completion_demonstrated': False, 'pilot_cap_assessment_required': True,
            'binding_pilot_guard_blocks_validation': True,
            'interpretation': 'The fixed .25 local match guard can bind. Synthetic worst-case envelopes do not establish completion. Pilot must assess feasibility without increasing guards or automatically continuing.'},
        'pricing_limitations': [
            'Local guards and token quotes are estimates, never provider invoice ceilings or expected invoice claims.',
            'Safety rates cover the stated all-input-cache-write scenario; actual caching, provider usage, quota and backend revisions remain unknown.'],
        'superseded_large_proposal': {'status': 'superseded_for_this_profile',
            'qualification_spec_generated': False, 'formal_confirmatory_spec_generated': False,
            'historical_configs_changed': False},
        'operational_planning': {'status': 'not_started', 'time_projection': 'not_started',
            'storage_projection': 'not_started', 'provider_account_quota': 'unverified',
            'disk_free_check': 'not_started', 'required_initial_disk_gib': 5,
            'stop_new_trials_below_disk_gib': 2, 'launch_checkpoint': 'not_started',
            'heartbeat': 'not_started'},
        'remaining_gates': [
            'Freeze and review clean source and complete environment; obtain separate exact pilot spending approval.',
            'Assess pilot feasibility under the fixed .25 match and 3.75 campaign guards; binding guards prevent validation.',
            'Only a complete eligible matching pilot permits validation registration and a separate validation spending decision.',
            'Prior Q evidence is never pooled; this exploratory study cannot close original confirmation acceptance.']}
    return specs, receipt


def _build_luna_bundle():
    from parallax_relay.exploratory import LUNA_PROFILE_ID, luna_profile_spec, luna_profile_analysis
    sources, smoke = _exploratory_inputs()
    specs, stages, frozen_stages = {}, {}, []
    qualification_spec = None
    for stage, counts in (('qualification', (5, 5, 0, 864, 864, 1.25)),
                          ('validation', (120, 30, 90, 20736, 5184, 7.5))):
        spec = CampaignSpec.model_validate(luna_profile_spec(stage), strict=True)
        value = spec.model_dump(mode='json')
        trials = schedule(spec)
        paid = [trial for trial in trials if trial['team'] == 'models']
        calls = sum(trial_exposure(spec, trial)[0] for trial in trials)
        paid_calls = sum(trial_exposure(spec, trial)[0] for trial in paid)
        cap = sum((Decimal(str(trial_exposure(spec, trial)[1])) for trial in paid), Decimal(0))
        if ((len(trials), len(paid), len(trials) - len(paid), calls, paid_calls, float(cap)) != counts or
                cap != Decimal(str(spec.campaign_max_estimated_cost_usd)) or
                spec.match.max_estimated_cost_usd != 0.25):
            raise ValueError('Luna schedule or guard arithmetic differs from approved limits')
        frozen = frozen_inputs(spec)
        if (set(frozen['inputs']) != {room.id for room in rooms()} or
                canonical_hash(frozen['analysis']) != canonical_hash(luna_profile_analysis())):
            raise ValueError('Luna frozen inputs must cover all rooms and descriptive analysis')
        frozen_stages.append(frozen)
        specs[stage + '.json'] = value
        stages[stage] = {'spec_file': stage + '.json', 'spec_sha256': canonical_hash(value),
            'frozen_inputs_sha256': canonical_hash(frozen), 'trials': len(trials),
            'model_trials': len(paid), 'baseline_trials': len(trials) - len(paid),
            'assignments_per_room': 1, 'max_calls': calls, 'max_provider_attempts': paid_calls,
            'match_estimate_guard_usd': 0.25, 'campaign_estimate_guard_usd': float(cap),
            'baseline_provider_cost_usd': 0.0}
        if stage == 'qualification':
            qualification_spec = spec
    if canonical_hash(frozen_stages[0]) != canonical_hash(frozen_stages[1]):
        raise ValueError('Qualification and validation must freeze identical source/environment/inputs')
    frozen = frozen_stages[0]
    conservative = _envelope_summary(worksheet(qualification_spec))
    nominal = _envelope_summary(worksheet(qualification_spec, openai_input_rate=0.1))
    price_inputs = {'nominal_openai_input_per_million': 0.1,
        'safety_openai_input_per_million': 0.125, 'openai_output_per_million': 0.5,
        'runtime_rate_basis': 'All three OpenAI roles use the default 30-minute cache-write input rate.',
        'actual_cache_activity': 'unknown', 'source_record_uses_nominal_rates': True,
        'runtime_uses_safety_rates': True}
    prior_estimate = Decimal('1.044149250')
    receipt = {'schema_version': 1, 'kind': 'offline_preparation_candidate',
        'profile_id': LUNA_PROFILE_ID, 'evidence_class': 'exploratory', 'confirmatory_eligible': False,
        'spending_authorized': False, 'registration_created': False,
        'credential_resolution_performed': False, 'provider_clients_constructed': False,
        'sources': sources, 'source_record_sha256': canonical_hash(sources),
        'smoke_profile_sha256': canonical_hash(smoke), 'price_inputs': price_inputs,
        'price_inputs_sha256': canonical_hash(price_inputs),
        'source': frozen['source'], 'source_sha256': canonical_hash(frozen['source']),
        'environment': frozen['environment'], 'environment_sha256': frozen['environment']['sha256'],
        'catalog_sha256': frozen['catalog']['sha256'], 'frozen_inputs_sha256': canonical_hash(frozen),
        'analysis': luna_profile_analysis(), 'stages': stages,
        'limits': {'match_guard_usd': 0.25, 'full_five_arm_model_block_guard_usd': 1.25,
            'new_campaign_guards_usd': 8.75, 'prior_q_allowance_usd': 0.25,
            'prior_pilot_and_continuation_estimate_usd': str(prior_estimate),
            'prior_usage_completeness': 'unknown',
            'combined_local_guard_allowance_usd': float(prior_estimate + Decimal('9.00')),
            'user_combined_budget_usd': 20.0, 'cost_is_estimate_not_billing_guarantee': True},
        'guard_feasibility': {'match_guard_usd': 0.25,
            'conservative_envelope': conservative, 'nominal_rate_comparison': nominal,
            'binding_possible': conservative['retained_quote_bound_usd'] > 0.25,
            'full_match_completion_demonstrated': False, 'qualification_cap_assessment_required': True,
            'binding_qualification_guard_blocks_validation': True,
            'interpretation': 'The fixed .25 local match guard can bind. Qualification must assess all retained evidence and costs without increasing guards or automatically continuing.'},
        'pricing_limitations': [
            'Local guards and token quotes are estimates, never provider invoice ceilings or expected invoice claims.',
            'Prior pilot and continuation estimates retain unknown usage and all failed costs; the original mixed pilot remains incomplete.',
            'Safety rates cover the stated all-input-cache-write scenario; actual caching, provider usage, quota and backend revisions remain unknown.'],
        'operational_planning': {'status': 'not_started', 'time_projection': 'not_started',
            'storage_projection': 'not_started', 'provider_account_quota': 'unverified',
            'disk_free_check': 'not_started', 'required_initial_disk_gib': 5,
            'stop_new_trials_below_disk_gib': 2, 'launch_checkpoint': 'not_started',
            'heartbeat': 'not_started'},
        'remaining_gates': [
            'Freeze the reviewed evidence selection and source bridge, then register only the five-case qualification supplement.',
            'Obtain separate exact $1.25 and 864-request supplement approval before paid execution.',
            'Revalidate complete composite qualification and all artifact/accounting evidence before validation registration; there is no win threshold.',
            'Obtain separate $7.50 validation spending approval after qualification succeeds.',
            'Report retrospective exploratory qualification; the original mixed pilot is never repaired or pooled as complete.']}
    return specs, receipt


def build_bundle(profile=None):
    if profile is None:
        return _build_standard_bundle()
    if profile == 'exploratory-luna-under20-v1':
        return _build_luna_bundle()
    if profile != 'exploratory-under20-v1':
        raise ValueError('Unknown preparation profile')
    return _build_exploratory_bundle()


def write_bundle(out, profile=None):
    specs, receipt = build_bundle() if profile is None else build_bundle(profile=profile)
    out.mkdir(parents=True, exist_ok=False)
    for filename, data in {**specs, 'receipt.json': receipt}.items():
        path = out / filename
        path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        if canonical_hash(read_json(path)) != canonical_hash(data):
            raise ValueError('Candidate write/readback mismatch')
    if profile is None:
        check_bundle(out, require_clean=False)
    else:
        check_bundle(out, require_clean=False, profile=profile)
    return receipt


def check_bundle(bundle, require_clean=False, profile=None):
    specs, expected = build_bundle() if profile is None else build_bundle(profile=profile)
    if profile is not None and {path.name for path in bundle.iterdir()} != {*specs, 'receipt.json'}:
        raise ValueError('Exploratory bundle contains unexpected or missing files')
    receipt = read_json(bundle / 'receipt.json')
    if canonical_hash(receipt) != canonical_hash(expected):
        raise ValueError('Receipt differs from current source/environment/inputs or worksheet')
    for filename, value in specs.items():
        candidate = read_json(bundle / filename)
        # Validate the unnormalized input just as registration does, then compare
        # raw canonical hashes so 2/2.0 and True/1 cannot compare equal.
        CampaignSpec.model_validate(candidate, strict=True)
        if canonical_hash(candidate) != canonical_hash(value):
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
    for command in (prepare, check):
        command.add_argument('--profile', choices=['exploratory-under20-v1', 'exploratory-luna-under20-v1'])
    args = parser.parse_args(argv)
    try:
        receipt = (write_bundle(args.out, profile=args.profile) if args.command == 'prepare' else
                   check_bundle(args.bundle, args.require_clean, profile=args.profile))
        summary = {'kind': receipt['kind'], 'spending_authorized': False,
            'source': receipt['source'], 'receipt_sha256': canonical_hash(receipt),
            'guards_usd': {stage: row['campaign_estimate_guard_usd'] for stage, row in receipt['stages'].items()}}
        if args.profile is None:
            summary['nominal_configured_rate_comparison_usd'] = {
                stage: row['nominal_configured_rate_scenario']['campaign_guard_usd']
                for stage, row in receipt['stages'].items()}
        else:
            summary.update(profile_id=receipt['profile_id'], evidence_class=receipt['evidence_class'],
                           combined_local_guard_allowance_usd=receipt['limits']['combined_local_guard_allowance_usd'])
            assessment = ('qualification_cap_assessment_required' if args.profile == 'exploratory-luna-under20-v1'
                          else 'pilot_cap_assessment_required')
            summary[assessment] = receipt['guard_feasibility'][assessment]
        print(json.dumps(summary))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print('Preparation failed: existing destination, invalid/drifted inputs, receipt, or worksheet; inspect offline.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
