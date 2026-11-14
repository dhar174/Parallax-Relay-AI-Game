"""Non-secret identity and canonicalization, independent of provider access."""
import copy
import importlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from types import SimpleNamespace

from parallax_relay.config import MatchSettings, Rates
from parallax_relay.state import initial_world


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        path = Path('parallax_relay/provenance.py')
        self.assertTrue(path.is_file(), 'Versioned provenance is missing')
        self.p = importlib.import_module('parallax_relay.provenance')

    def test_canonical_hash_orders_objects_but_preserves_effective_values(self):
        self.assertEqual(self.p.canonical_hash({'b': [2], 'a': '鏡'}),
                         self.p.canonical_hash(json.loads('{"a":"\\u93e1","b":[2]}')))
        self.assertNotEqual(self.p.canonical_hash({'a': 1}), self.p.canonical_hash({'a': 2}))
        with self.assertRaises(ValueError): self.p.canonical_hash({'a': float('nan')})

    def test_execution_uses_actual_settings_prices_and_no_credential_fields(self):
        context = self.p.ProvenanceContext(
            mode='mock', experiment_id=uuid4(), trial_id=uuid4(),
            players={'SPECTRA': self.p.PlayerIdentity(provider='mock', model='scripted-fixture')},
            requested_settings=MatchSettings(max_estimated_cost_usd=0.001))
        run = self.p.RunProvenance(context)
        settings = MatchSettings(max_turns=1)
        rates = {'SPECTRA': Rates(input_per_million=1, output_per_million=2)}
        run.begin(settings, rates, initial_world().snapshot())
        data = run.snapshot()
        config = data['execution']['value']
        self.assertEqual(config['settings'], settings.model_dump())
        self.assertEqual(config['pricing']['SPECTRA'], rates['SPECTRA'].model_dump())
        self.assertIsNone(config['pricing']['FLUX'])
        self.assertEqual(data['requested_settings']['max_estimated_cost_usd'], 0.001)
        self.assertEqual(data['players']['FLUX']['provider'], 'unknown')
        self.assertIsNone(data['players']['FLUX']['model_revision'])
        self.assertEqual(data['schema_version'], 1)
        self.assertEqual(self.p.read_provenance({'schema_version': 2, 'provenance': data}), data)
        with self.assertRaises(ValueError):
            self.p.ProvenanceContext(api_key='SECRET_SENTINEL')
        before = copy.deepcopy(data)
        rates.clear()
        data['execution']['value']['settings']['max_turns'] = 12
        self.assertEqual(run.snapshot(), before)

    def test_input_hashes_cover_prompt_schemas_room_constants_and_initial_state(self):
        state = initial_world().snapshot()
        original = self.p.input_identities(state)
        with patch.object(self.p.prompts, 'SYSTEM_RULES', 'Changed rules'):
            self.assertNotEqual(original['prompt'], self.p.input_identities(state)['prompt'])
        with patch.object(self.p.protocol, 'MAX_REPLY_CHARS', 17):
            self.assertNotEqual(original['schemas'], self.p.input_identities(state)['schemas'])
        with patch.object(self.p.state, 'ARTIFACT', 8):
            self.assertNotEqual(original['room'], self.p.input_identities(state)['room'])
        state['energy'] = 1
        self.assertNotEqual(original['room'], self.p.input_identities(state)['room'])

    def test_git_clean_dirty_unavailable_and_unrelated_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                                      text=True, encoding='utf-8', errors='replace', check=True).stdout.strip()
            self.assertEqual(self.p.collect_source(root)['status'], 'unavailable')
            git('init', '-q'); git('config', 'user.email', 'test@example.invalid')
            git('config', 'user.name', 'Offline test')
            (root / '.gitignore').write_text('.env\n', encoding='utf-8')
            git('add', '.gitignore'); git('commit', '-qm', 'Fixture')
            clean = self.p.collect_source(root)
            self.assertEqual(clean['status'], 'clean')
            self.assertEqual(clean['revision'], git('rev-parse', 'HEAD'))
            (root / '.env').write_text('SECRET_SENTINEL', encoding='utf-8')
            self.assertEqual(self.p.collect_source(root), clean)
            (root / 'changed').write_text('changed', encoding='utf-8')
            self.assertEqual(self.p.collect_source(root)['status'], 'dirty')
            archive = root / 'archive'; archive.mkdir()
            self.assertEqual(self.p.collect_source(archive)['status'], 'unavailable')
        for error in [FileNotFoundError('SECRET_SENTINEL'), subprocess.TimeoutExpired('git', 1)]:
            with patch.object(self.p.subprocess, 'run', side_effect=error):
                data = self.p.collect_source(Path.cwd())
            self.assertEqual(data['status'], 'unavailable')
            self.assertNotIn('SECRET_SENTINEL', json.dumps(data))

    def test_environment_never_serializes_installation_urls_or_errors(self):
        class Distribution:
            metadata = {'Name': 'example', 'Description': 'SECRET_SENTINEL'}
            version = '1.2.3'
            def read_text(self, name): raise AssertionError('Must not read direct_url.json')
        with patch.object(self.p.metadata, 'distributions', return_value=[Distribution()]):
            data = self.p.collect_environment()
        self.assertEqual(data['value']['packages'], [{'name': 'example', 'version': '1.2.3'}])
        self.assertNotIn('SECRET_SENTINEL', json.dumps(data))
        with patch.object(self.p.metadata, 'distributions', side_effect=OSError('SECRET_SENTINEL')):
            unavailable = self.p.collect_environment()
        self.assertEqual(unavailable['value']['status'], 'unavailable')
        self.assertNotIn('SECRET_SENTINEL', json.dumps(unavailable))

    def test_reader_accepts_legacy_and_rejects_unknown_corrupt_records_safely(self):
        self.assertIsNone(self.p.read_provenance({'schema_version': 2}))
        for data in [None, {'schema_version': 2, 'password': 'SECRET_SENTINEL'},
                     {'schema_version': 1, 'run_id': 'SECRET_SENTINEL'}]:
            with self.subTest(data=data), self.assertRaises(self.p.ProvenanceError) as ctx:
                self.p.read_provenance({'provenance': data})
            self.assertNotIn('SECRET_SENTINEL', str(ctx.exception))
        run = self.p.RunProvenance()
        run.begin(MatchSettings(), {}, initial_world().snapshot())
        bad = run.snapshot()
        bad['execution']['value']['settings']['max_turns'] = 1
        with self.assertRaises(self.p.ProvenanceError): self.p.read_provenance({'provenance': bad})

    def test_reader_rejects_structurally_invalid_known_version(self):
        run = self.p.RunProvenance()
        run.begin(MatchSettings(), {}, initial_world().snapshot())
        original = run.snapshot()
        for field, value in [('source', {}), ('players', {}), ('inputs', {}),
                             ('environment', self.p._fingerprint({}))]:
            with self.subTest(field=field):
                data = copy.deepcopy(original); data[field] = value
                with self.assertRaises(self.p.ProvenanceError): self.p.read_provenance({'provenance': data})
        original['lifecycle']['stage'] = 'ended'
        with self.assertRaises(self.p.ProvenanceError): self.p.read_provenance({'provenance': original})

    def test_monotonic_duration_and_original_end_survive_clock_and_outcome_changes(self):
        times = ['2026-11-14T12:00:00Z', '2026-11-14T12:00:01Z', '2026-11-14T11:00:00Z']
        with patch.object(self.p, '_utc_now', side_effect=times), \
             patch.object(self.p, 'monotonic', side_effect=[10.0, 12.0]):
            run = self.p.RunProvenance()
            run.begin(MatchSettings(), {}, initial_world().snapshot())
            run.end(SimpleNamespace(stop_reason='victory'))
            run.end(SimpleNamespace(stop_reason='local_error'))
        data = run.snapshot()
        self.assertEqual(data['lifecycle']['elapsed_seconds'], 2.0)
        self.assertEqual(data['lifecycle']['ended_at'], times[-1])
        self.assertEqual(data['lifecycle']['execution_stop_reason'], 'victory')
        self.assertEqual(data['lifecycle']['stop_reason'], 'local_error')
        self.assertEqual(self.p.read_provenance({'provenance': data}), data)

    def test_historical_fixture_remains_legacy_readable(self):
        manifest = json.loads(Path('example_run/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['schema_version'], 2)
        self.assertIsNone(self.p.read_provenance(manifest))
