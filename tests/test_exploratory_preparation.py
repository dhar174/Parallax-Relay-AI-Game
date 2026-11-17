"""Offline exploratory candidates preserve the approved monetary boundaries."""
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
PROFILE = 'exploratory-under20-v1'


class ExploratoryPreparationTests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/prepare_campaign.py'),
                               *map(str, args)], cwd=ROOT, capture_output=True, text=True)

    def test_real_cli_profile_counts_caps_and_explicit_checker_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp) / 'candidate'
            result = self.command('prepare', '--profile', PROFILE, '--out', bundle)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({p.name for p in bundle.iterdir()}, {'pilot.json', 'validation.json', 'receipt.json'})
            summary = json.loads(result.stdout)
            self.assertEqual(summary['profile_id'], PROFILE)
            self.assertEqual(summary['guards_usd'], {'pilot': 3.75, 'validation': 7.5})
            receipt = json.loads((bundle / 'receipt.json').read_text())
            self.assertFalse(receipt['spending_authorized'])
            self.assertFalse(receipt['registration_created'])
            self.assertFalse(receipt['confirmatory_eligible'])
            self.assertEqual(receipt['limits']['new_campaign_guards_usd'], 11.25)
            self.assertEqual(receipt['limits']['prior_q_allowance_usd'], 0.25)
            self.assertEqual(receipt['limits']['combined_local_guard_allowance_usd'], 11.5)
            for stage, total, paid, baselines, calls, attempts, cap in (
                    ('pilot', 60, 15, 45, 10368, 2592, 3.75),
                    ('validation', 120, 30, 90, 20736, 5184, 7.5)):
                row = receipt['stages'][stage]
                self.assertEqual((row['trials'], row['model_trials'], row['baseline_trials'], row['max_calls'],
                                  row['max_provider_attempts'], row['campaign_estimate_guard_usd']),
                                 (total, paid, baselines, calls, attempts, cap))
                spec = json.loads((bundle / (stage + '.json')).read_text())
                self.assertEqual(spec['protocol_version'], 3)
                self.assertEqual(spec['match']['max_estimated_cost_usd'], 0.25)
                self.assertEqual(spec['repetitions'], 1)
                self.assertEqual(spec['roster'][0]['pricing']['input_per_million'], 0.125)
            self.assertEqual(self.command('check', '--profile', PROFILE, '--bundle', bundle).returncode, 0)
            self.assertNotEqual(self.command('check', '--bundle', bundle).returncode, 0)
            self.assertNotEqual(self.command('prepare', '--profile', PROFILE, '--out', bundle).returncode, 0)
            self.assertNotEqual(self.command('prepare', '--profile', 'unknown', '--out', Path(temp) / 'unknown').returncode, 0)

    def test_receipt_freezes_all_rooms_and_assesses_binding_guard_without_invoice_claim(self):
        specs, receipt = prep.build_bundle(profile=PROFILE)
        from parallax_relay.campaign import frozen_inputs
        from parallax_relay.campaign_models import CampaignSpec
        from parallax_relay.rooms import rooms
        frozen = [frozen_inputs(CampaignSpec.model_validate(specs[name]))
                  for name in ('pilot.json', 'validation.json')]
        self.assertEqual(set(frozen[0]['inputs']), {room.id for room in rooms()})
        self.assertEqual(frozen[0], frozen[1])
        self.assertEqual(receipt['frozen_inputs_sha256'], prep.canonical_hash(frozen[0]))
        self.assertEqual(receipt['source_sha256'], prep.canonical_hash(frozen[0]['source']))
        self.assertEqual(receipt['environment_sha256'], frozen[0]['environment']['sha256'])
        guard = receipt['guard_feasibility']
        self.assertEqual(guard['match_guard_usd'], 0.25)
        self.assertGreater(guard['conservative_envelope']['retained_quote_bound_usd'], 0.25)
        self.assertTrue(guard['binding_possible'])
        self.assertTrue(guard['pilot_cap_assessment_required'])
        self.assertFalse(guard['full_match_completion_demonstrated'])
        self.assertTrue(receipt['limits']['cost_is_estimate_not_billing_guarantee'])
        self.assertEqual(receipt['price_inputs']['nominal_openai_input_per_million'], 0.1)
        self.assertEqual(receipt['price_inputs']['safety_openai_input_per_million'], 0.125)
        self.assertEqual(receipt['price_inputs_sha256'], prep.canonical_hash(receipt['price_inputs']))
        self.assertIn('superseded_large_proposal', receipt)

    def test_no_socket_client_credentials_registration_or_execution(self):
        from parallax_relay.config import GameConfig
        public_environment_get = os.environ.get
        public_environment_item = type(os.environ).__getitem__
        def public_item(environ, name):
            if name in ('OPENAI_API_KEY', 'GEMINI_API_KEY'):
                raise AssertionError('credential lookup')
            return public_environment_item(environ, name)
        def public_get(name, default=None):
            if name in ('OPENAI_API_KEY', 'GEMINI_API_KEY'):
                raise AssertionError('credential lookup')
            return public_environment_get(name, default)
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
                self.assertEqual({p.name for p in bundle.iterdir()}, {'pilot.json', 'validation.json', 'receipt.json'})

    def test_duplicate_type_tamper_extra_file_and_profile_mismatch_rejected(self):
        specs, receipt = prep.build_bundle(profile=PROFILE)
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            originals = {name: json.dumps(value, indent=2) for name, value in {**specs, 'receipt.json': receipt}.items()}
            for name, value in originals.items():
                (bundle / name).write_text(value)
            with patch.object(prep, 'build_bundle', return_value=(specs, receipt)):
                for filename, keys, replacement in (
                        ('pilot.json', ('match', 'max_turns'), 12.0),
                        ('validation.json', ('repetitions',), True),
                        ('pilot.json', ('campaign_max_estimated_cost_usd',), 4.0),
                        ('receipt.json', ('profile_id',), 'other'),
                        ('receipt.json', ('limits', 'prior_q_allowance_usd'), 0.0),
                        ('receipt.json', ('stages', 'pilot', 'trials'), 60.0)):
                    with self.subTest(filename=filename, keys=keys):
                        data = json.loads(originals[filename])
                        target = data
                        for key in keys[:-1]:
                            target = target[key]
                        target[keys[-1]] = replacement
                        (bundle / filename).write_text(json.dumps(data))
                        with self.assertRaises(ValueError):
                            prep.check_bundle(bundle, profile=PROFILE)
                        (bundle / filename).write_text(originals[filename])
                for filename in originals:
                    (bundle / filename).write_text(originals[filename].replace('"schema_version": 2', '"schema_version": 1, "schema_version": 2', 1)
                        if filename != 'receipt.json' else originals[filename].replace('"schema_version": 1', '"schema_version": 0, "schema_version": 1', 1))
                    with self.assertRaises(ValueError):
                        prep.check_bundle(bundle, profile=PROFILE)
                    (bundle / filename).write_text(originals[filename])
                (bundle / 'qualification.json').write_text('{}')
                with self.assertRaises(ValueError):
                    prep.check_bundle(bundle, profile=PROFILE)

    def test_profile_inputs_reject_price_type_and_key_binding_drift(self):
        for attribute, path, keys, value in (
                ('SOURCES', prep.SOURCES, ('models', 'openai/gpt-6-luna', 'cache_write_input_per_million'), 0.1),
                ('PROFILE', prep.PROFILE, ('schema_version',), True),
                ('PROFILE', prep.PROFILE, ('config', 'match', 'max_attempts'), 2.0),
                ('PROFILE', prep.PROFILE, ('config', 'players', 'SPECTRA', 'api_key_env'), 'OTHER_KEY')):
            with self.subTest(keys=keys), tempfile.TemporaryDirectory() as temp:
                data = prep.read_json(path)
                target = data
                for key in keys[:-1]:
                    target = target[key]
                target[keys[-1]] = value
                changed = Path(temp) / 'input.json'
                changed.write_text(json.dumps(data))
                with patch.object(prep, attribute, changed), self.assertRaises(ValueError):
                    prep.build_bundle(profile=PROFILE)

    def test_readback_rejects_duplicates_and_nonfinite_json(self):
        original_write = Path.write_text
        def ambiguous(path, content, *args, **kwargs):
            if path.name == 'pilot.json':
                content = content.replace('"protocol_version": 3', '"protocol_version": 2, "protocol_version": 3', 1)
            return original_write(path, content, *args, **kwargs)
        with tempfile.TemporaryDirectory() as temp, patch.object(Path, 'write_text', new=ambiguous):
            with self.assertRaises(ValueError):
                prep.write_bundle(Path(temp) / 'candidate', profile=PROFILE)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'nan.json'
            path.write_text('{"value":NaN}')
            with self.assertRaises(ValueError):
                prep.read_json(path)

    def test_clean_check_and_changed_environment_are_enforced(self):
        with tempfile.TemporaryDirectory() as temp, patch('parallax_relay.campaign.collect_source',
                return_value={'status': 'dirty', 'revision': '0' * 40, 'reason': None}):
            bundle = Path(temp) / 'candidate'
            prep.write_bundle(bundle, profile=PROFILE)
            with self.assertRaisesRegex(ValueError, 'Clean source'):
                prep.check_bundle(bundle, require_clean=True, profile=PROFILE)
            with patch('parallax_relay.campaign.collect_environment', return_value={'sha256': '0' * 64, 'value': {'status': 'complete'}}):
                with self.assertRaises(ValueError):
                    prep.check_bundle(bundle, profile=PROFILE)


if __name__ == '__main__':
    unittest.main()
