import json
import sys
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from parallax_relay.config import ConfigError
from parallax_relay.realtime.settings import Settings, describe_profile, load_profile, make_live_agents
from parallax_relay.realtime.supervise import supervise_command


class SettingsTests(unittest.TestCase):
    def test_profile_is_offline_and_has_proposed_limits(self):
        with patch('parallax_relay.realtime.settings.HTTPAgent', side_effect=AssertionError('network client')):
            profile = load_profile('dev-bridge-live-v1')
            description = describe_profile(profile)
        settings = profile.settings
        self.assertEqual((settings.max_windows, settings.window_ticks, settings.tick_rate, settings.action_points), (4, 120, 60, 8))
        self.assertEqual(settings.max_commands, 4)
        self.assertEqual((settings.max_calls, settings.max_attempts, settings.timeout_seconds, settings.wall_seconds), (36, 1, 20, 240))
        self.assertEqual((settings.communication_rounds, settings.clock_mode), (2, 'freeze'))
        self.assertEqual((settings.max_output_tokens, settings.image_token_reserve, settings.max_estimated_cost_usd), (4096, 8192, 1))
        self.assertEqual(profile.players['FLUX'].model, 'gemini-3.5-flash-lite')
        self.assertNotIn('api_key_env', json.dumps(description))
        self.assertTrue(description['prices_require_revalidation'])

    def test_invalid_values_and_unknown_profile(self):
        for values in ({'max_calls': 0}, {'wall_seconds': float('nan')}, {'max_attempts': True}, {'clock_mode': 'x'}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                Settings(**values)
        with self.assertRaises(ConfigError):
            load_profile('../not-a-profile')

    def test_offline_timing_defaults_by_mode(self):
        for mode, expected in (
            ('reactive', (1, 10.0)),
            ('manual', (2, 120.0)),
            ('baseline', (2, 5.0)),
            ('test', (2, 5.0)),
        ):
            with self.subTest(mode=mode):
                settings = Settings.offline(mode)
                self.assertEqual((settings.communication_rounds, settings.phase_timeout_seconds), expected)
                self.assertEqual(settings.clock_mode, 'freeze')
                self.assertIsNone(settings.max_estimated_cost_usd)

    def test_live_factory_requires_local_credentials_and_separate_clients(self):
        profile = load_profile('dev-bridge-live-v1')
        with self.assertRaises(ConfigError):
            make_live_agents(profile, {})
        with patch('parallax_relay.realtime.settings.HTTPAgent') as agent:
            result = make_live_agents(profile, {'OPENAI_API_KEY': 'dummy-a', 'GEMINI_API_KEY': 'dummy-b'})
            self.assertEqual(set(result), {'SPECTRA', 'PYRA', 'FLUX'})
            self.assertEqual(agent.call_count, 3)

    def test_supervisor_distinguishes_success_failure_and_timeout(self):
        ok = supervise_command([sys.executable, '-c', 'pass'], timeout_seconds=5)
        failed = supervise_command([sys.executable, '-c', 'raise SystemExit(7)'], timeout_seconds=5)
        timeout = supervise_command([sys.executable, '-c', 'import time; time.sleep(10)'], timeout_seconds=0.2, cleanup_seconds=1)
        self.assertEqual((ok.status, ok.exit_code), ('completed', 0))
        self.assertEqual((failed.status, failed.exit_code), ('child_failed', 7))
        self.assertEqual((timeout.status, timeout.exit_code), ('wall_timeout', 124))


if __name__ == '__main__':
    unittest.main()
