"""Regression coverage for source availability and internally consistent readers."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from parallax_relay import provenance as p
from parallax_relay.config import MatchSettings
from parallax_relay.providers import provider_contract
from parallax_relay.state import initial_world


class SourceReviewTests(unittest.TestCase):
    def test_status_failure_retains_verified_revision(self):
        root, revision = Path.cwd(), 'a' * 40
        identity = SimpleNamespace(returncode=0, stdout=f'{root}\n{revision}\n')
        cases = [
            (SimpleNamespace(returncode=1, stdout=''), 'status_unavailable'),
            (subprocess.TimeoutExpired('git', 1), 'git_timeout'),
            (OSError('SECRET_SENTINEL'), 'status_unavailable'),
        ]
        for failure, reason in cases:
            with self.subTest(reason=reason, failure=type(failure).__name__), \
                 patch.object(p.subprocess, 'run', side_effect=[identity, failure]):
                self.assertEqual(p.collect_source(root), {
                    'status': 'unavailable', 'revision': revision, 'reason': reason})

    def test_git_overrides_cannot_redirect_or_configure_source_probes(self):
        root, revision = Path.cwd(), 'b' * 40
        overrides = {key: 'SECRET_SENTINEL' for key in (
            'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
            'GIT_CONFIG_PARAMETERS', 'GIT_CONFIG_COUNT', 'GIT_CONFIG_KEY_0',
            'GIT_CONFIG_VALUE_0', 'GIT_OBJECT_DIRECTORY', 'GIT_CEILING_DIRECTORIES')}
        def probe(args, *, env, **kwargs):
            # These arguments determine which tree/config Git actually observes.
            self.assertEqual({k: v for k, v in env.items() if k.startswith('GIT_')},
                             {'GIT_OPTIONAL_LOCKS': '0'})
            self.assertIn('core.fsmonitor=', args)
            self.assertEqual(args[args.index('-C') + 1], str(root))
            return SimpleNamespace(returncode=0, stdout=(
                f'{root}\n{revision}\n' if 'rev-parse' in args else ''))
        with patch.dict(os.environ, overrides), patch.object(p.subprocess, 'run', side_effect=probe):
            self.assertEqual(p.collect_source(root), {
                'status': 'clean', 'revision': revision, 'reason': None})

    def test_unrelated_parent_has_explicit_reason(self):
        root = Path.cwd()
        identity = SimpleNamespace(returncode=0, stdout=f'{root.parent}\n{"c" * 40}\n')
        with patch.object(p.subprocess, 'run', return_value=identity):
            self.assertEqual(p.collect_source(root), {
                'status': 'unavailable', 'revision': None, 'reason': 'not_project_root'})

    def test_partial_inventory_retains_safe_packages(self):
        good = SimpleNamespace(metadata={'Name': 'Safe_Package'}, version='1.2.3')
        bad = SimpleNamespace(metadata={'Name': 'SECRET_SENTINEL invalid name'}, version='1.0')
        def interrupted():
            yield good
            raise OSError('SECRET_SENTINEL')
        for distributions in ([good, bad], interrupted()):
            with self.subTest(distributions=type(distributions).__name__), \
                 patch.object(p.metadata, 'distributions', return_value=distributions):
                data = p.collect_environment()
                self.assertEqual(data['value']['status'], 'partial')
                self.assertEqual(data['value']['packages'], [{'name': 'safe-package', 'version': '1.2.3'}])
                self.assertNotIn('SECRET_SENTINEL', json.dumps(data))

    def test_provider_contract_describes_each_wire_family(self):
        expected = {
            'openai': ('https://api.openai.com/v1/responses', 'responses', 'v1', None),
            'anthropic': ('https://api.anthropic.com/v1/messages', 'messages', 'v1', '2026-10-21'),
            'gemini': ('https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                       'generateContent', 'v1beta', None),
        }
        for provider, values in expected.items():
            with self.subTest(provider=provider):
                self.assertEqual(provider_contract(provider), dict(zip(
                    ('endpoint', 'family', 'namespace', 'version_header'), values)))
        for provider in ('mock', 'unknown', 'SECRET_SENTINEL'):
            self.assertIsNone(provider_contract(provider))


class ReaderReviewTests(unittest.TestCase):
    def setUp(self):
        self.run = p.RunProvenance(p.ProvenanceContext(players={
            'SPECTRA': p.PlayerIdentity(provider='openai', model='test-model')}))
        self.initialized = self.run.snapshot()
        self.run.begin(MatchSettings(), {}, initial_world().snapshot())
        self.running = self.run.snapshot()

    def assert_invalid(self, data):
        with self.assertRaises(p.ProvenanceError) as error:
            p.read_provenance({'provenance': data})
        self.assertEqual(str(error.exception), 'Unsupported or invalid provenance record')

    def test_top_level_player_must_match_fingerprinted_player(self):
        data = copy.deepcopy(self.running)
        data['players']['SPECTRA'] = copy.deepcopy(data['players']['PYRA'])
        self.assert_invalid(data)

    def test_player_consistency_is_checked_even_when_both_copies_match(self):
        cases = [
            ('PYRA', 'identity_source', 'declared'),
            ('PYRA', 'sampling', 'provider_default'),
            ('PYRA', 'api_contract', {'endpoint': 'SECRET_SENTINEL'}),
            ('SPECTRA', 'identity_source', 'unavailable'),
            ('SPECTRA', 'sampling', 'not_applicable'),
            ('SPECTRA', 'api_contract', None),
            ('SPECTRA', 'api_contract', {}),
            ('SPECTRA', 'model_revision', 'unverified-revision'),
        ]
        for role, field, value in cases:
            with self.subTest(role=role, field=field, value=value):
                data = copy.deepcopy(self.running)
                data['players'][role][field] = value
                data['execution']['value']['players'] = copy.deepcopy(data['players'])
                data['execution']['sha256'] = p.canonical_hash(data['execution']['value'])
                self.assert_invalid(data)

    def test_api_contract_rejects_mismatched_provider_and_invalid_version(self):
        for field, value in [('endpoint', 'https://example.invalid/'), ('family', 'messages'),
                             ('namespace', 'v1beta'), ('version_header', 'SECRET_SENTINEL')]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.running)
                data['players']['SPECTRA']['api_contract'][field] = value
                data['execution']['value']['players'] = copy.deepcopy(data['players'])
                data['execution']['sha256'] = p.canonical_hash(data['execution']['value'])
                self.assert_invalid(data)

    def test_historical_contract_versions_and_additive_player_fields_survive(self):
        run = p.RunProvenance(p.ProvenanceContext(players={
            'SPECTRA': p.PlayerIdentity(provider='anthropic', model='test-model')}))
        run.begin(MatchSettings(), {}, initial_world().snapshot())
        data = run.snapshot()
        for players in (data['players'], data['execution']['value']['players']):
            players['SPECTRA']['api_contract']['version_header'] = '2025-01-01'
        data['players']['SPECTRA']['extension'] = 'top-level annotation'
        data['execution']['value']['players']['SPECTRA']['api_contract']['extension'] = True
        data['execution']['sha256'] = p.canonical_hash(data['execution']['value'])
        self.assertEqual(p.read_provenance({'provenance': data}), data)

    def test_impossible_world_values_rejected_with_matching_hash(self):
        cases = [
            (('turn',), -1), (('energy',), -1), (('coolant',), -1), (('motor_heat',), -1),
            (('robots', 'SPECTRA', 'damage'), -1), (('robots', 'SPECTRA', 'x'), -1),
            (('robots', 'SPECTRA', 'x'), 13), (('robots', 'SPECTRA', 'role'), 'PYRA'),
            (('win',), True),
        ]
        for path, value in cases:
            with self.subTest(path=path):
                data = copy.deepcopy(self.running)
                room = data['inputs']['room']
                target = room['value']['initial_state']
                if path == ('win',): target['loss'] = True
                for key in path[:-1]: target = target[key]
                target[path[-1]] = value
                room['sha256'] = p.canonical_hash(room['value'])
                self.assert_invalid(data)

    def test_snapshot_bounds_use_recorded_width(self):
        data = json.loads(Path('tests/fixtures/legacy_provenance_v2.json').read_text())['provenance']
        room = data['inputs']['room']
        room['value']['constants']['WIDTH'] = 20
        room['value']['initial_state']['robots']['SPECTRA']['x'] = 19
        room['sha256'] = p.canonical_hash(room['value'])
        self.assertEqual(p.read_provenance({'provenance': data}), data)

    def test_initialized_and_external_records_have_no_execution_payload(self):
        for stage in ('initialized', 'external_result'):
            for field in ('execution', 'inputs'):
                with self.subTest(stage=stage, field=field):
                    data = copy.deepcopy(self.initialized)
                    data['lifecycle']['stage'] = stage
                    if stage == 'external_result':
                        data['lifecycle'].update(execution_stop_reason='victory', stop_reason='victory')
                    data[field] = copy.deepcopy(self.running[field])
                    self.assert_invalid(data)

    def test_lifecycle_rejects_impossible_stop_reasons(self):
        cases = [
            (self.initialized, {'stop_reason': 'victory'}),
            (self.initialized, {'execution_stop_reason': 'victory'}),
            (self.initialized, {'stage': 'external_result'}),
            (self.running, {'execution_stop_reason': 'victory'}),
            (self.running, {'stop_reason': 'victory'}),
        ]
        for original, changes in cases:
            with self.subTest(changes=changes):
                data = copy.deepcopy(original)
                data['lifecycle'].update(changes)
                self.assert_invalid(data)

    def test_schema_boolean_and_non_utc_timestamps_fail_safely(self):
        data = copy.deepcopy(self.running)
        data['schema_version'] = True
        self.assert_invalid(data)
        for timestamp in ('2026-11-14T12:00:00', '2026-11-14T12:00:00+01:00'):
            for field in ('created_at', 'started_at'):
                with self.subTest(field=field, timestamp=timestamp):
                    data = copy.deepcopy(self.running)
                    data['lifecycle'][field] = timestamp
                    self.assert_invalid(data)

    def test_guarded_pricing_and_communication_mismatch_rejected(self):
        for field, value in [('settings', {'max_estimated_cost_usd': 1.0}),
                             ('conditions', {'arm': 'reduced'})]:
            with self.subTest(field=field):
                data = copy.deepcopy(self.running)
                data['execution']['value'][field].update(value)
                data['execution']['sha256'] = p.canonical_hash(data['execution']['value'])
                self.assert_invalid(data)
