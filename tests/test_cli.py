import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from parallax_relay.recording import Recorder
from parallax_relay.orchestrator import run_match
from parallax_relay.agents import ScriptedAgent
from parallax_relay.config import MatchSettings, ConfigError
from parallax_relay.protocol import ROLES, ModelReply, Usage
from parallax_relay.play import load_env_file
from parallax_relay.providers import ProviderError


class CLITests(unittest.TestCase):
    def test_non_utf8_toml_exits_safely_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'invalid.toml'
            config.write_bytes(b'# SECRET_SENTINEL\xff')
            out = Path(tmp) / 'not-created'
            proc = self.command('--mock', '--config', config, '--out', out)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertIn('UTF-8', proc.stderr)
            self.assertNotIn('SECRET_SENTINEL', proc.stdout + proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)
            self.assertFalse(out.exists())

    def command(self,*args):
        env=os.environ.copy()
        for name in ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','OPENAI_MODEL','ANTHROPIC_MODEL','GEMINI_MODEL'):
            env.pop(name,None)
        return subprocess.run([sys.executable,'-m','parallax_relay.play',*map(str,args)],capture_output=True,text=True,env=env,timeout=30)

    def test_mock_cli_no_keys_and_saves_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run'
            proc=self.command('--mock','--out',out)
            self.assertEqual(proc.returncode,0,proc.stderr)
            result=json.loads((out/'result.json').read_text())
            self.assertTrue(result['win'])
            self.assertEqual(result['budget']['calls_started'],63)
            self.assertTrue((out/'index.html').exists())
            self.assertEqual(len((out/'calls.jsonl').read_text().splitlines()),63)
            self.assertTrue((out/'final_spectator.png').exists())
            self.assertIn('mock', (out/'manifest.json').read_text())

    def test_live_missing_config_is_no_network_and_no_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'not-created'
            proc=self.command('--live','--env-file',Path(tmp)/'none.env','--out',out)
            self.assertEqual(proc.returncode,2)
            self.assertFalse(out.exists())

    def test_existing_output_directory_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'run';out.mkdir();(out/'keep.txt').write_text('keep')
            proc=self.command('--mock','--out',out)
            self.assertEqual(proc.returncode,2)
            self.assertEqual((out/'keep.txt').read_text(),'keep')

    def test_mode_required(self):
        self.assertEqual(self.command().returncode,2)

    def test_env_file_is_data_only_and_does_not_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env';p.write_text('# comment\nFOO="literal $(not_run)"\nBAR=new\n')
            env={'BAR':'existing'};load_env_file(p,env)
            self.assertEqual(env['FOO'],'literal $(not_run)')
            self.assertEqual(env['BAR'],'existing')

    def test_env_error_does_not_echo_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env';p.write_text('THIS IS SECRET_SENTINEL')
            with self.assertRaises(ConfigError) as ctx: load_env_file(p,{})
            self.assertNotIn('SECRET_SENTINEL',str(ctx.exception))

    def test_non_utf8_environment_file_is_safe_configuration_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env';p.write_bytes(b'OPENAI_API_KEY=SECRET_SENTINEL\xff')
            proc=self.command('--check','--env-file',p)
            self.assertEqual(proc.returncode,2)
            self.assertNotIn('SECRET_SENTINEL',proc.stderr)
            self.assertNotIn('Traceback',proc.stderr)

    def test_check_does_not_call_providers(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'.env'
            p.write_text('\n'.join(f'{provider}_{suffix}={"test-model" if suffix=="MODEL" else "KEY_SENTINEL"}'
                                   for provider in ('OPENAI','ANTHROPIC','GEMINI') for suffix in ('MODEL','API_KEY')))
            proc=self.command('--check','--env-file',p)
            self.assertEqual(proc.returncode,0,proc.stderr)
            self.assertNotIn('KEY_SENTINEL',proc.stdout+proc.stderr)
            self.assertIn('no API requests',proc.stdout)


class RecordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_run_is_preserved(self):
        class Broken(ScriptedAgent):
            async def respond(self,request): raise ProviderError('http_error',False,401)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'partial';rec=Recorder(out,{'mode':'mock'})
            agents={r:Broken(r) if r=='PYRA' else ScriptedAgent(r) for r in ROLES}
            result=await run_match(agents,recorder=rec)
            self.assertEqual(result.stop_reason,'provider_error')
            self.assertEqual(len((out/'calls.jsonl').read_text().splitlines()),3)
            self.assertTrue((out/'phases.jsonl').exists())
            self.assertTrue((out/'index.html').exists())
            self.assertEqual(json.loads((out/'result.json').read_text())['turns'],0)

    async def test_replay_escapes_model_html(self):
        evil='</script><script>globalThis.INJECTED=true</script>'
        class Talker(ScriptedAgent):
            async def respond(self,request):
                if request.phase!='commit': return ModelReply(json.dumps({'turn':request.turn,'message':evil}),Usage(0,0))
                return await super().respond(request)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'xss';rec=Recorder(out,{'mode':'mock'})
            await run_match({r:Talker(r) for r in ROLES},MatchSettings(max_turns=1),recorder=rec)
            html=(out/'index.html').read_text()
            self.assertNotIn(evil,html)
            self.assertIn('\\u003c/script',html)

    async def test_cancelled_calls_leave_partial_result(self):
        started=asyncio.Event()
        class Slow(ScriptedAgent):
            async def respond(self,request): started.set();await asyncio.sleep(20)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'cancel';rec=Recorder(out,{'mode':'mock'})
            task=asyncio.create_task(run_match({r:Slow(r) for r in ROLES},recorder=rec))
            await started.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            self.assertEqual(json.loads((out/'result.json').read_text())['stop_reason'],'cancelled')
            self.assertEqual(len((out/'calls.jsonl').read_text().splitlines()),3)
