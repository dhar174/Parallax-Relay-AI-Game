import tempfile
from pathlib import Path
import unittest
from parallax_relay.config import load_config, ConfigError, MatchSettings


class ConfigTests(unittest.TestCase):
    def test_non_utf8_toml_is_a_safe_configuration_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.toml'
            path.write_bytes(b'# SECRET_SENTINEL\xff')
            with self.assertRaises(ConfigError) as ctx:
                load_config(path)
            self.assertEqual(str(ctx.exception), 'Configuration file must use UTF-8 encoding')
            self.assertNotIn('SECRET_SENTINEL', str(ctx.exception))

    def test_malformed_toml_and_invalid_fields_remain_safe(self):
        original = Path('configs/three_models.toml').read_text(encoding='utf-8')
        cases = ('SECRET_SENTINEL = [',
                 original.replace('max_turns = 12', 'max_turns = "SECRET_SENTINEL"'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'invalid.toml'
            for text in cases:
                with self.subTest(text=text):
                    path.write_text(text, encoding='utf-8')
                    with self.assertRaises(ConfigError) as ctx:
                        load_config(path)
                    self.assertNotIn('SECRET_SENTINEL', str(ctx.exception))

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
            p=Path(tmp)/'cfg.toml'; p.write_text('[match]\nmax_callls=5\n', encoding='utf-8')
            with self.assertRaises(ConfigError): load_config(p)

    def test_invalid_bounds(self):
        for kw in ({'communication_rounds':3},{'max_turns':13},{'max_attempts':0},{'history_turns':-1},{'timeout_seconds':0}):
            with self.subTest(kw=kw), self.assertRaises(ValueError): MatchSettings(**kw)
