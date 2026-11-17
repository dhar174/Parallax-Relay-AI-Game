"""The under-$20 protocol is fixed, balanced by room, and entirely offline here."""
from collections import Counter, defaultdict
import copy
import importlib.util
import json
import unittest

from parallax_relay.campaign_models import CampaignSpec, assignments, schedule, trial_exposure
from parallax_relay.provenance import canonical_hash


ARMS = {'full', 'reduced', 'disabled', 'withheld', 'no_images'}
ROOM_ROLE = {
    'split_span': 'FLUX', 'dev_01': 'SPECTRA', 'dev_02': 'PYRA',
    'ret_01': 'FLUX', 'ret_02': 'SPECTRA', 'ret_03': 'PYRA',
    'relay_01': 'FLUX', 'relay_02': 'SPECTRA', 'relay_03': 'PYRA',
}


def exploratory(test):
    test.assertIsNotNone(importlib.util.find_spec('parallax_relay.exploratory'),
                         'The exploratory profile must be available')
    from parallax_relay import exploratory as profile
    return profile


class ExploratoryModelsTests(unittest.TestCase):
    def test_profile_is_a_fresh_full_validated_spec_with_explicit_safety_prices(self):
        profile = exploratory(self)
        for stage, rooms, calls, cap in (
            ('pilot', ['split_span', 'dev_01', 'dev_02'], 10368, 3.75),
            ('validation', ['ret_01', 'ret_02', 'ret_03', 'relay_01', 'relay_02', 'relay_03'], 20736, 7.5),
        ):
            with self.subTest(stage=stage):
                raw = profile.profile_spec(stage)
                spec = CampaignSpec.model_validate(json.loads(json.dumps(raw)), strict=True)
                self.assertEqual(raw, spec.model_dump(mode='json'))
                self.assertEqual((spec.schema_version, spec.protocol_version, spec.stage, spec.mode), (2, 3, stage, 'live'))
                self.assertEqual((spec.rooms, spec.repeats, spec.campaign_max_calls, spec.campaign_max_estimated_cost_usd),
                                 (rooms, 1, calls, cap))
                self.assertEqual((spec.scheduler_seed, spec.min_trial_interval_seconds), (0, 1.0))
                self.assertEqual(spec.match.model_dump(), {
                    'room_id': 'split_span', 'communication_rounds': 2, 'condition': None,
                    'max_turns': 12, 'max_calls': 216, 'max_attempts': 2,
                    'timeout_seconds': 60.0, 'max_output_tokens': 4096,
                    'history_turns': 4, 'retry_delay_seconds': 0.5,
                    'max_consecutive_failures': 3, 'max_estimated_cost_usd': 0.25,
                    'image_token_reserve': 8192})
                self.assertEqual([entry.model_dump() for entry in spec.roster], [
                    {'provider': 'openai', 'model': 'gpt-6-luna', 'api_key_env': 'OPENAI_API_KEY',
                     'pricing': {'input_per_million': 0.125, 'output_per_million': 0.5}},
                    {'provider': 'openai', 'model': 'gpt-6-luna', 'api_key_env': 'OPENAI_API_KEY',
                     'pricing': {'input_per_million': 0.125, 'output_per_million': 0.5}},
                    {'provider': 'gemini', 'model': 'gemini-3.5-flash-lite', 'api_key_env': 'GEMINI_API_KEY',
                     'pricing': {'input_per_million': 0.3, 'output_per_million': 2.5}},
                ])
                self.assertTrue(profile.is_exploratory(spec))
                raw['roster'][0]['pricing']['input_per_million'] = 99
                self.assertEqual(profile.profile_spec(stage)['roster'][0]['pricing']['input_per_million'], 0.125)

    def test_analysis_declares_descriptive_nonconfirmatory_method(self):
        profile = exploratory(self)
        expected = {'version': 3, 'profile_id': 'exploratory-under20-v1',
                    'evidence_class': 'exploratory', 'method': 'descriptive_per_room',
                    'bootstrap_resamples': 0, 'seed': 0, 'percentile': None,
                    'prng': None, 'concurrency': 1, 'primary_contrast': ['full', 'disabled']}
        self.assertEqual(profile.PROFILE_ID, 'exploratory-under20-v1')
        analysis = profile.profile_analysis()
        self.assertEqual(analysis, expected)
        analysis['primary_contrast'].reverse()
        self.assertEqual(profile.profile_analysis(), expected)
        self.assertFalse(profile.is_exploratory(CampaignSpec.model_validate({'schema_version': 1, 'campaign_max_calls': 1000})))
        self.assertFalse(profile.is_exploratory(CampaignSpec.model_validate({'schema_version': 2, 'campaign_max_calls': 1000})))

    def test_profile_rejects_unsupported_or_nonstring_stages(self):
        profile = exploratory(self)
        for stage in ('diagnostic', 'confirmatory', 'Pilot', '', None, True, 3, ['pilot']):
            with self.subTest(stage=stage), self.assertRaises((ValueError, TypeError)):
                profile.profile_spec(stage)

    def test_schedule_uses_one_fixed_assignment_per_room_for_all_arms(self):
        profile = exploratory(self)
        self.assertEqual(dict(profile.GEMINI_ROLE_BY_ROOM), ROOM_ROLE)
        for stage, count, model_count, provider_calls, total_calls, money in (
            ('pilot', 60, 15, 2592, 10368, 3.75),
            ('validation', 120, 30, 5184, 20736, 7.5),
        ):
            with self.subTest(stage=stage):
                spec = CampaignSpec.model_validate(profile.profile_spec(stage), strict=True)
                self.assertEqual(len(assignments(spec)), 3)
                trials = schedule(spec)
                self.assertEqual(len(trials), count)
                self.assertEqual(Counter(t['team'] for t in trials), {
                    'models': model_count, 'scripted': model_count,
                    'wait': model_count, 'uniform': model_count})
                by_room_team = defaultdict(list)
                blocks = defaultdict(list)
                for trial in trials:
                    by_room_team[trial['room'], trial['team']].append(trial)
                    blocks[trial['block_id']].append(trial)
                    self.assertEqual(trial['repetition'], 0)
                    self.assertEqual(trial['split'], 'development' if stage == 'pilot' else 'held_out')
                    if trial['team'] == 'models':
                        self.assertEqual(list(trial['players']), ['SPECTRA', 'PYRA', 'FLUX'])
                        providers = {role: entry['provider'] for role, entry in trial['players'].items()}
                        self.assertEqual([role for role, provider in providers.items() if provider == 'gemini'],
                                         [ROOM_ROLE[trial['room']]])
                        self.assertEqual(list(providers.values()).count('openai'), 2)
                    else:
                        self.assertEqual(trial['players'], {})
                        self.assertEqual(trial_exposure(spec, trial)[1], 0)
                for room in spec.rooms:
                    for team in ('models', 'scripted', 'wait', 'uniform'):
                        group = by_room_team[room, team]
                        self.assertEqual({t['condition'] for t in group}, ARMS)
                        self.assertEqual(len({t['block_id'] for t in group}), 1)
                        self.assertEqual(len({t['assignment_id'] for t in group}), 1)
                self.assertTrue(all(len(block) == 5 for block in blocks.values()))
                self.assertEqual(sum(trial_exposure(spec, t)[0] for t in trials if t['team'] == 'models'), provider_calls)
                self.assertEqual(sum(trial_exposure(spec, t)[0] for t in trials), total_calls)
                self.assertEqual(sum(trial_exposure(spec, t)[1] for t in trials), money)
                self.assertEqual({sum(trial_exposure(spec, t)[1] for t in block)
                                  for block in blocks.values() if block[0]['team'] == 'models'}, {1.25})

    def test_profile_rejects_tampered_settings_roster_prices_caps_and_types(self):
        profile = exploratory(self)
        mutations = [
            ('mode', lambda v: v.update(mode='offline')),
            ('protocol type', lambda v: v.update(protocol_version='3')),
            ('stage', lambda v: v.update(stage='confirmatory')),
            ('missing room', lambda v: v['rooms'].pop()),
            ('reordered room', lambda v: v['rooms'].reverse()),
            ('arm', lambda v: v['conditions'].pop()),
            ('baseline', lambda v: v['policies'].pop()),
            ('repetitions', lambda v: v.update(repetitions=2)),
            ('repetition type', lambda v: v.update(repetitions=True)),
            ('seed', lambda v: v.update(scheduler_seed=1)),
            ('seed type', lambda v: v.update(scheduler_seed=False)),
            ('interval', lambda v: v.update(min_trial_interval_seconds=0.0)),
            ('match guard raised', lambda v: v['match'].update(max_estimated_cost_usd=0.5)),
            ('match guard lowered', lambda v: v['match'].update(max_estimated_cost_usd=0.1)),
            ('money cap raised', lambda v: v.update(campaign_max_estimated_cost_usd=10.0)),
            ('money cap lowered', lambda v: v.update(campaign_max_estimated_cost_usd=1.0)),
            ('money cap string', lambda v: v.update(campaign_max_estimated_cost_usd='3.75')),
            ('calls raised', lambda v: v.update(campaign_max_calls=10369)),
            ('calls lowered', lambda v: v.update(campaign_max_calls=10367)),
            ('calls bool', lambda v: v.update(campaign_max_calls=True)),
            ('input price nominal', lambda v: v['roster'][0]['pricing'].update(input_per_million=0.1)),
            ('input price type', lambda v: v['roster'][0]['pricing'].update(input_per_million='0.125')),
            ('output price', lambda v: v['roster'][2]['pricing'].update(output_per_million=1.0)),
            ('price bool', lambda v: v['roster'][2]['pricing'].update(output_per_million=True)),
            ('model', lambda v: v['roster'][2].update(model='other-model')),
            ('key binding', lambda v: v['roster'][1].update(api_key_env='OTHER_KEY')),
            ('turns', lambda v: v['match'].update(max_turns=11)),
            ('attempts', lambda v: v['match'].update(max_attempts=1)),
            ('timeout', lambda v: v['match'].update(timeout_seconds=61.0)),
            ('output allowance', lambda v: v['match'].update(max_output_tokens=2048)),
            ('history', lambda v: v['match'].update(history_turns=3)),
            ('image reserve', lambda v: v['match'].update(image_token_reserve=4096)),
            ('extra key', lambda v: v.update(extra='tampered')),
            ('missing fixed field', lambda v: v.pop('repetitions')),
        ]
        for name, mutate in mutations:
            value = profile.profile_spec('pilot')
            mutate(value)
            with self.subTest(name=name), self.assertRaises(ValueError):
                CampaignSpec.model_validate(value)
        for stage in ('diagnostic', 'confirmatory'):
            value = profile.profile_spec('pilot')
            value['stage'] = stage
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                CampaignSpec.model_validate(value)
        for version in (1, 2):
            value = {'schema_version': version, 'protocol_version': version, 'stage': 'validation', 'campaign_max_calls': 1000}
            with self.subTest(protocol=version), self.assertRaises(ValueError):
                CampaignSpec.model_validate(value)

    def test_existing_protocol_schedule_counts_and_canonical_dumps_are_unchanged(self):
        # Baseline hashes were recorded from the unmodified locked interpreter.
        expected = {
            (1, 'diagnostic', 'offline'): (15, 'd86f153c2e71942bb611a2ec1a4b29aa0d9b688af04c793136017a6eb7fe35b6'),
            (1, 'diagnostic', 'live'): (30, '78cab954f1b554d65b783346f76b1f6ae063920837281ae2d946c87c3fe3c368'),
            (1, 'pilot', 'offline'): (35, '74bf59073e292165a4c5e2a44f63edf3986519f4d8c6692f2531468f23eb9034'),
            (1, 'pilot', 'live'): (110, 'ca8c4fb4f8b446d4032a0e9422500ed3b1b7c147d8ebba5665af4cb5b9a67ad6'),
            (1, 'confirmatory', 'offline'): (160, 'be7ce7eba0ea7e07db2aba498688cc9c2fadad4849af7648e8a769978a866721'),
            (1, 'confirmatory', 'live'): (610, 'ce1afd7c5c86d612d4ed82391310df16f3ea2d83b6d3b539af076d21677045bb'),
            (2, 'diagnostic', 'offline'): (45, 'e43d2eebd8df92289c2152baf7e5723c8e0621475edfde1d01e289f355e65089'),
            (2, 'diagnostic', 'live'): (90, '50ed2fa55c63ea96a5c5a1b4d0a146b7085271379d943e912b5a58504826482d'),
            (2, 'pilot', 'offline'): (105, '5f20431c43c13ca67de9b1ace68ac195a06f96b10dc71fce535b0fcc93ef7704'),
            (2, 'pilot', 'live'): (330, '9860d8b6ec1fe2a66686d0fad2f5a7457f1dca05bac26159d84ef67d117bfb31'),
            (2, 'confirmatory', 'offline'): (960, 'e59ec0001f4d62423ddbf1a2d81acfb9f60119935064943494ff6b75cb6b3381'),
            (2, 'confirmatory', 'live'): (3660, '244242de11a8b32ade4675e00c711e4ffa08a578a70e5ef5dd2763b522e75084'),
        }
        a = {'provider': 'openai', 'model': 'legacy-a', 'api_key_env': 'OPENAI_API_KEY',
             'pricing': {'input_per_million': 0.1, 'output_per_million': 0.5}}
        b = {'provider': 'gemini', 'model': 'legacy-b', 'api_key_env': 'GEMINI_API_KEY',
             'pricing': {'input_per_million': 0.3, 'output_per_million': 2.5}}
        for (version, stage, mode), (count, digest) in expected.items():
            raw = {'schema_version': version, 'stage': stage, 'mode': mode, 'campaign_max_calls': 1000000}
            if mode == 'live':
                raw.update(roster=[copy.deepcopy(a), copy.deepcopy(a), copy.deepcopy(b)],
                           match={'max_estimated_cost_usd': 1.0}, campaign_max_estimated_cost_usd=100.0)
            with self.subTest(protocol=version, stage=stage, mode=mode):
                spec = CampaignSpec.model_validate(raw)
                self.assertEqual(len(schedule(spec)), count)
                self.assertEqual(canonical_hash(spec.model_dump(mode='json')), digest)


if __name__ == '__main__':
    unittest.main()
