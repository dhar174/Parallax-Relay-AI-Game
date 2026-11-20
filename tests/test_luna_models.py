"""Protocol 4 fixes a model-only supplement and all-Luna held-out design."""
from collections import Counter, UserDict
import copy
from types import MappingProxyType
import unittest

from parallax_relay import exploratory as profile
from parallax_relay.campaign_models import CampaignSpec, assignments, schedule, trial_exposure
from parallax_relay.provenance import canonical_hash


class LunaModelsTests(unittest.TestCase):
    def builder(self):
        builder = getattr(profile, 'luna_profile_spec', None)
        self.assertTrue(callable(builder), 'Missing all-Luna approved profile')
        return builder

    def test_schedules_only_missing_split_span_models_then_full_held_out_cohort(self):
        builder = self.builder()
        for stage, selected, total, paid, baselines, all_calls, paid_calls, cap in (
                ('qualification', ['split_span'], 5, 5, 0, 864, 864, 1.25),
                ('validation', ['ret_01', 'ret_02', 'ret_03', 'relay_01', 'relay_02', 'relay_03'],
                 120, 30, 90, 20736, 5184, 7.5)):
            with self.subTest(stage=stage):
                raw = builder(stage)
                spec = CampaignSpec.model_validate(raw, strict=True)
                self.assertEqual(raw, spec.model_dump(mode='json'))
                self.assertEqual((spec.schema_version, spec.protocol_version, spec.stage, spec.mode),
                                 (2, 4, stage, 'live'))
                self.assertEqual((spec.rooms, spec.repeats, spec.campaign_max_calls,
                                  spec.campaign_max_estimated_cost_usd), (selected, 1, all_calls, cap))
                self.assertEqual((spec.scheduler_seed, spec.min_trial_interval_seconds), (0, 1.0))
                self.assertEqual(spec.match.model_dump(), {
                    'room_id': 'split_span', 'communication_rounds': 2, 'condition': None,
                    'max_turns': 12, 'max_calls': 216, 'max_attempts': 2,
                    'timeout_seconds': 60.0, 'max_output_tokens': 4096, 'history_turns': 4,
                    'retry_delay_seconds': 0.5, 'max_consecutive_failures': 3,
                    'max_estimated_cost_usd': 0.25, 'image_token_reserve': 8192})
                self.assertEqual(len(assignments(spec)), 1)
                self.assertEqual([entry.model_dump() for entry in spec.roster], [
                    {'provider': 'openai', 'model': 'gpt-6-luna', 'api_key_env': 'OPENAI_API_KEY',
                     'pricing': {'input_per_million': 0.125, 'output_per_million': 0.5}}] * 3)
                trials = schedule(spec)
                self.assertEqual(len(trials), total)
                self.assertEqual(sum(t['team'] == 'models' for t in trials), paid)
                self.assertEqual(sum(t['team'] != 'models' for t in trials), baselines)
                self.assertEqual(sum(trial_exposure(spec, t)[0] for t in trials), all_calls)
                self.assertEqual(sum(trial_exposure(spec, t)[0] for t in trials if t['team'] == 'models'), paid_calls)
                self.assertEqual(sum(trial_exposure(spec, t)[1] for t in trials), cap)
                for room in selected:
                    self.assertEqual(Counter(t['condition'] for t in trials if t['room'] == room and
                                             t['team'] == 'models'),
                                     dict.fromkeys(('full', 'reduced', 'disabled', 'withheld', 'no_images'), 1))
                self.assertEqual({t['repetition'] for t in trials}, {0})
                raw['roster'][0]['pricing']['input_per_million'] = 99
                self.assertEqual(builder(stage)['roster'][0]['pricing']['input_per_million'], 0.125)

    def test_exact_raw_profile_rejects_type_coercions_and_design_drift(self):
        builder = self.builder()
        for stage in ('qualification', 'validation'):
            original = builder(stage)
            mutations = [
                lambda v: v.update(protocol_version='4'),
                lambda v: v.update(protocol_version=4.0),
                lambda v: v.update(schema_version=True),
                lambda v: v.update(stage='pilot'),
                lambda v: v.update(mode='offline'),
                lambda v: v.update(repetitions=True),
                lambda v: v.update(repetitions=2),
                lambda v: v.update(campaign_max_calls=True),
                lambda v: v.update(campaign_max_calls=v['campaign_max_calls'] + 1),
                lambda v: v.update(campaign_max_estimated_cost_usd=str(v['campaign_max_estimated_cost_usd'])),
                lambda v: v.update(min_trial_interval_seconds=1),
                lambda v: v.update(scheduler_seed=False),
                lambda v: v['match'].update(timeout_seconds=60),
                lambda v: v['match'].update(max_turns=12.0),
                lambda v: v['match'].update(max_calls=217),
                lambda v: v['match'].update(max_estimated_cost_usd=0.5),
                lambda v: v['roster'][2].update(provider='gemini'),
                lambda v: v['roster'][0].update(api_key_env='OTHER_KEY'),
                lambda v: v['roster'][1]['pricing'].update(output_per_million='0.5'),
                lambda v: v['roster'][0]['pricing'].update(input_per_million=0.1),
                lambda v: v['conditions'].reverse(),
                lambda v: v['conditions'].pop(),
                lambda v: v.update(rooms=['dev_01']),
                lambda v: v.update(policies=['scripted']),
                lambda v: v.pop('repetitions'),
                lambda v: v.update(extra='tampered'),
            ]
            for field in ('policies', 'rooms', 'conditions', 'roster'):
                mutations.append(lambda v, field=field: v.update({field: tuple(v[field])}))
            for index, mutate in enumerate(mutations):
                value = copy.deepcopy(original)
                mutate(value)
                with self.subTest(stage=stage, mutation=index), self.assertRaises(ValueError):
                    CampaignSpec.model_validate(value)
        for stage in ('pilot', 'diagnostic', 'confirmatory', '', None, True, 4, ['validation']):
            with self.subTest(stage=stage), self.assertRaises((ValueError, TypeError)):
                builder(stage)

    def test_luna_analysis_and_exact_discriminators_preserve_legacy_profiles(self):
        self.builder()
        analysis = getattr(profile, 'luna_profile_analysis', None)
        self.assertTrue(callable(analysis))
        self.assertEqual(analysis(), {
            'version': 4, 'profile_id': 'exploratory-luna-under20-v1', 'evidence_class': 'exploratory',
            'method': 'descriptive_per_room', 'bootstrap_resamples': 0, 'seed': 0,
            'percentile': None, 'prng': None, 'concurrency': 1, 'primary_contrast': ['full', 'disabled']})
        self.assertEqual(profile.LUNA_PROFILE_ID, 'exploratory-luna-under20-v1')
        for value, old, luna, descriptive in ((1, False, False, False), (2, False, False, False),
                (3, True, False, True), (4, False, True, True), (True, False, False, False),
                (3.0, False, False, False), (4.0, False, False, False), ('4', False, False, False)):
            raw = {'protocol_version': value}
            with self.subTest(version=value):
                self.assertEqual(profile.is_exploratory(raw), old)
                self.assertEqual(profile.is_luna(raw), luna)
                self.assertEqual(profile.is_descriptive(raw), descriptive)
        for stage, digest in (
                ('pilot', '7c0f2f048446e576b086b4b92041e7eefc3e75b9d08db8b27d3959b403cd2482'),
                ('validation', '94795f5dff4e49a9017329000ae049edddce67d92952b6386296b0a9eeddbaaf')):
            self.assertEqual(canonical_hash(CampaignSpec.model_validate(profile.profile_spec(stage)).model_dump(mode='json')), digest)
        self.assertEqual(canonical_hash(profile.profile_analysis()),
                         'cf1c733f5849ef11bd966c3f3a57c2131011bb0cd7d7a5d7b25bddea8d8b7718')
        validated = CampaignSpec.model_validate(self.builder()('qualification'))
        self.assertTrue(profile.is_luna(validated))
        self.assertTrue(profile.is_descriptive(validated))
        self.assertFalse(profile.is_exploratory(validated))

    def test_qualification_stage_cannot_expand_legacy_protocols(self):
        for version in (1, 2, 3):
            with self.subTest(version=version), self.assertRaises(ValueError):
                CampaignSpec.model_validate({'protocol_version': version, 'stage': 'qualification',
                                             'rooms': ['split_span'], 'campaign_max_calls': 864})

    def test_luna_rejects_top_level_python_mapping_subclasses_before_copying(self):
        class PythonMapping(dict):
            pass
        for mapping_type in (PythonMapping, UserDict, MappingProxyType):
            for discriminator in (4, 4.0):
                value = self.builder()('qualification')
                value['protocol_version'] = discriminator
                raw = mapping_type(value)
                with self.subTest(mapping_type=mapping_type, discriminator=discriminator), self.assertRaises(ValueError):
                    CampaignSpec.model_validate(raw)


if __name__ == '__main__':
    unittest.main()
