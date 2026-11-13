import tempfile
from pathlib import Path
import unittest
from parallax_relay.config import load_config, ConfigError, MatchSettings


class ConfigTests(unittest.TestCase):
    def test_default_example_has_main_three(self):
        cfg=load_config(Path('configs/three_models.toml'))
        self.assertEqual({v.provider for v in cfg.players.values()},{'openai','anthropic','gemini'})
        self.assertEqual(cfg.match.communication_rounds,2)

    def test_missing_credentials_fail_before_calls(self):
        cfg=load_config(Path('configs/three_models.toml'))
        with self.assertRaises(ConfigError) as ctx: cfg.resolve({})
        self.assertIn('OPENAI_API_KEY',str(ctx.exception))
        self.assertIn('GEMINI_MODEL',str(ctx.exception))

    def test_resolved_config_repr_does_not_show_key(self):
        cfg=load_config(Path('configs/three_models.toml'))
        env={key:('secret_SENTINEL' if key.endswith('_API_KEY') else 'test-model') for key in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','OPENAI_MODEL','ANTHROPIC_MODEL','GEMINI_MODEL']}
        resolved=cfg.resolve(env)
        self.assertNotIn('secret_SENTINEL',repr(resolved))
        self.assertEqual(resolved['SPECTRA'].model,'test-model')

    def test_unknown_settings_do_not_silently_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'cfg.toml'; p.write_text('[match]\nmax_callls=5\n')
            with self.assertRaises(ConfigError): load_config(p)

    def test_invalid_bounds(self):
        for kw in ({'communication_rounds':3},{'max_turns':13},{'max_attempts':0},{'history_turns':-1},{'timeout_seconds':0}):
            with self.subTest(kw=kw), self.assertRaises(ValueError): MatchSettings(**kw)
