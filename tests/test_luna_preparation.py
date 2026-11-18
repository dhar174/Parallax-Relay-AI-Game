"""All-Luna preparation is offline, exact, and distinct from the mixed pilot."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import prepare_campaign as prep

ROOT = Path(__file__).resolve().parent.parent
PROFILE = 'exploratory-luna-under20-v1'


class LunaPreparationTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_campaign.py'),
                               *map(str, args)], cwd=ROOT, capture_output=True, text=True)

    def test_cli_prepares_only_supplement_and_validation_with_exact_caps(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'candidate'
            result = self.command('prepare', '--profile', PROFILE, '--out', bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in bundle.iterdir()},
                             {'qualification.json', 'validation.json', 'receipt.json'})
            summary = json.loads(result.stdout)
            self.assertEqual(summary['profile_id'], PROFILE)
            self.assertEqual(summary['guards_usd'], {'qualification': 1.25, 'validation': 7.5})
            receipt = prep.read_json(bundle / 'receipt.json')
            self.assertEqual(receipt['limits']['new_campaign_guards_usd'], 8.75)
            self.assertEqual(receipt['limits']['prior_q_allowance_usd'], 0.25)
            self.assertEqual(receipt['limits']['prior_pilot_and_continuation_estimate_usd'], '1.044149250')
            self.assertEqual(receipt['limits']['combined_local_guard_allowance_usd'], 10.04414925)
            for stage, total, models, controls, calls, paid_calls, guard in (
                    ('qualification', 5, 5, 0, 864, 864, 1.25),
                    ('validation', 120, 30, 90, 20736, 5184, 7.5)):
                row = receipt['stages'][stage]
                self.assertEqual((row['trials'], row['model_trials'], row['baseline_trials'],
                                  row['max_calls'], row['max_provider_attempts'],
                                  row['campaign_estimate_guard_usd']),
                                 (total, models, controls, calls, paid_calls, guard))
                spec = prep.read_json(bundle / (stage + '.json'))
                self.assertEqual(spec['protocol_version'], 4)
                self.assertEqual({p['provider'] for p in spec['roster']}, {'openai'})
            self.assertEqual(self.command('check', '--profile', PROFILE, '--bundle', bundle).returncode, 0)
            self.assertEqual(self.command('check', '--profile', 'exploratory-under20-v1', '--bundle', bundle).returncode, 2)
            self.assertEqual(self.command('check', '--bundle', bundle).returncode, 2)
            self.assertEqual(self.command('prepare', '--profile', PROFILE, '--out', bundle).returncode, 2)

    def test_receipt_binds_all_rooms_and_keeps_qualification_descriptive(self):
        from parallax_relay.campaign import frozen_inputs
        from parallax_relay.campaign_models import CampaignSpec
        from parallax_relay.rooms import rooms
        specs, receipt = prep.build_bundle(profile=PROFILE)
        frozen = [frozen_inputs(CampaignSpec.model_validate(specs[name]))
                  for name in ('qualification.json', 'validation.json')]
        self.assertEqual(frozen[0], frozen[1])
        self.assertEqual(set(frozen[0]['inputs']), {room.id for room in rooms()})
        self.assertEqual(receipt['frozen_inputs_sha256'], prep.canonical_hash(frozen[0]))
        self.assertEqual(receipt['analysis']['version'], 4)
        self.assertEqual(receipt['analysis']['bootstrap_resamples'], 0)
        self.assertIsNone(receipt['analysis']['percentile'])
        self.assertFalse(receipt['confirmatory_eligible'])
        for field in ('spending_authorized', 'registration_created', 'credential_resolution_performed',
                      'provider_clients_constructed'):
            self.assertIs(receipt[field], False)
        guard = receipt['guard_feasibility']
        self.assertTrue(guard['qualification_cap_assessment_required'])
        self.assertTrue(guard['binding_qualification_guard_blocks_validation'])
        self.assertFalse(guard['full_match_completion_demonstrated'])
        self.assertGreater(guard['conservative_envelope']['retained_quote_bound_usd'], 0.25)
        self.assertTrue(receipt['limits']['cost_is_estimate_not_billing_guarantee'])
        self.assertEqual(receipt['price_inputs']['safety_openai_input_per_million'], 0.125)
        self.assertEqual(receipt['price_inputs']['openai_output_per_million'], 0.5)
        self.assertEqual(receipt['price_inputs_sha256'], prep.canonical_hash(receipt['price_inputs']))

    def test_no_credential_network_client_registration_or_execution_side_effects(self):
        from parallax_relay.config import GameConfig
        environment_get = os.environ.get
        environment_item = type(os.environ).__getitem__
        def public_get(name, default=None):
            if name.endswith('_API_KEY'):
                raise AssertionError('credential lookup')
            return environment_get(name, default)
        def public_item(environ, name):
            if name.endswith('_API_KEY'):
                raise AssertionError('credential lookup')
            return environment_item(environ, name)
        with patch('os.environ.get', side_effect=public_get), \
             patch.object(type(os.environ), '__getitem__', new=public_item), \
             patch.object(socket, 'socket', side_effect=AssertionError('socket')), \
             patch('httpx.AsyncClient', side_effect=AssertionError('client')), \
             patch('parallax_relay.providers.HTTPAgent', side_effect=AssertionError('agent')), \
             patch.object(GameConfig, 'resolve', side_effect=AssertionError('credentials')), \
             patch('parallax_relay.campaign.register', side_effect=AssertionError('registration')), \
             patch('parallax_relay.campaign.execute_trial', side_effect=AssertionError('execution')), \
             patch('parallax_relay.campaign.run_campaign', side_effect=AssertionError('run')):
            with tempfile.TemporaryDirectory() as temp:
                bundle = Path(temp) / 'candidate'
                prep.write_bundle(bundle, profile=PROFILE)
                prep.check_bundle(bundle, profile=PROFILE)

    def test_checker_rejects_rehashed_type_tamper_duplicates_and_extra_files(self):
        specs, receipt = prep.build_bundle(profile=PROFILE)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            originals = {name: json.dumps(value) for name, value in {**specs, 'receipt.json': receipt}.items()}
            for name, text in originals.items():
                (bundle / name).write_text(text)
            with patch.object(prep, 'build_bundle', return_value=(specs, receipt)):
                value = json.loads(originals['qualification.json'])
                value['match']['timeout_seconds'] = 60
                (bundle / 'qualification.json').write_text(json.dumps(value))
                changed_receipt = json.loads(originals['receipt.json'])
                changed_receipt['stages']['qualification']['spec_sha256'] = prep.canonical_hash(value)
                (bundle / 'receipt.json').write_text(json.dumps(changed_receipt))
                with self.assertRaises(ValueError):
                    prep.check_bundle(bundle, profile=PROFILE)
                (bundle / 'receipt.json').write_text(originals['receipt.json'])
                (bundle / 'qualification.json').write_text(originals['qualification.json'].replace(
                    '"protocol_version": 4', '"protocol_version": 3, "protocol_version": 4', 1))
                with self.assertRaisesRegex(ValueError, 'Duplicate'):
                    prep.check_bundle(bundle, profile=PROFILE)
                (bundle / 'qualification.json').write_text(originals['qualification.json'])
                (bundle / 'pilot.json').write_text('{}')
                with self.assertRaises(ValueError):
                    prep.check_bundle(bundle, profile=PROFILE)

    def test_source_price_drift_and_dirty_freeze_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            sources = prep.read_json(prep.SOURCES)
            sources['models']['openai/gpt-6-luna']['cache_write_input_per_million'] = 0.1
            changed = Path(temp) / 'sources.json'
            changed.write_text(json.dumps(sources))
            with patch.object(prep, 'SOURCES', changed), self.assertRaises(ValueError):
                prep.build_bundle(profile=PROFILE)
        with tempfile.TemporaryDirectory() as temp, patch('parallax_relay.campaign.collect_source',
                return_value={'status': 'dirty', 'revision': '0' * 40, 'reason': None}):
            bundle = Path(temp) / 'candidate'
            prep.write_bundle(bundle, profile=PROFILE)
            with self.assertRaisesRegex(ValueError, 'Clean source'):
                prep.check_bundle(bundle, require_clean=True, profile=PROFILE)


if __name__ == '__main__':
    unittest.main()
