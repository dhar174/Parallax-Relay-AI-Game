"""Antigravity #39 reproductions and durable behavioral regressions."""
import contextlib
import io
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID

from pydantic import ValidationError

from parallax_relay.config import MatchSettings, Rates
from parallax_relay.protocol import AgentRequest, Observation, ROLES, ModelReply, Usage
from parallax_relay.provenance import (ProvenanceContext, RunProvenance, canonical_hash, read_provenance)
from parallax_relay.state import initial_world


class ControlsReviewTests(unittest.TestCase):
    def test_rehashed_notice_requires_exact_json_types(self):
        run=RunProvenance();run.begin(MatchSettings(),{},initial_world().snapshot())
        for key,value in (('version',True),('public_messages_available',1),('role_image_available',1.0)):
            data=run.snapshot();block=data['inputs']['schemas']
            block['value']['request_structure']['condition_notice'][key]=value
            block['sha256']=canonical_hash(block['value'])
            with self.subTest(key=key),self.assertRaises(ValueError):read_provenance({'provenance':data})

    def test_context_revalidates_nested_copies_and_all_numeric_settings_reject_booleans(self):
        bad=MatchSettings().model_copy(update={'condition':'disabled'})
        with self.assertRaises(ValidationError):ProvenanceContext(requested_settings=bad)
        context=ProvenanceContext().model_copy(update={'requested_settings':bad})
        with self.assertRaises(ValueError):RunProvenance(context)
        for name in ('max_turns','max_calls','max_attempts','timeout_seconds','max_output_tokens','history_turns',
                     'retry_delay_seconds','max_consecutive_failures','max_estimated_cost_usd','image_token_reserve'):
            for value in (True,False):
                with self.subTest(name=name,value=value),self.assertRaises(ValidationError):MatchSettings(**{name:value})

    def test_uniform_python_version_rejects_unicode_digits(self):
        run=RunProvenance(ProvenanceContext(mode='mock',policy='uniform',trial_id=UUID(int=1)))
        run.begin(MatchSettings(),{},initial_world().snapshot());data=run.snapshot();block=data['execution']
        block['value']['policy']['python_version']='３.１２.３'
        block['sha256']=canonical_hash(block['value'])
        with self.assertRaises(ValueError):read_provenance({'provenance':data})

    def test_boolean_rounds_are_rejected_before_condition_normalization(self):
        for arm, value in [('disabled', False), ('reduced', True), ('full', True), (None, True)]:
            with self.subTest(arm=arm), self.assertRaises(ValidationError):
                MatchSettings(condition=arm, communication_rounds=value)

    def test_unvalidated_settings_copy_never_binds_provenance(self):
        run = RunProvenance()
        bad = MatchSettings().model_copy(update={'condition': 'disabled'})
        with self.assertRaises(ValidationError):
            run.begin(bad, {}, initial_world().snapshot())
        self.assertFalse(run.bound)

    def test_fast_rejects_explicit_disabled_rounds_without_named_condition(self):
        from parallax_relay import play
        from parallax_relay.config import load_config
        cfg=load_config(Path('configs/three_models.toml')).model_copy(update={'match':MatchSettings(communication_rounds=0)})
        with patch.object(play,'load_config',return_value=cfg),patch.object(play,'_run') as run,contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(play.main(['--mock','--fast']),2)
            run.assert_not_called()

    def test_request_notice_matches_direct_image_flag(self):
        request = AgentRequest(Observation('SPECTRA', 0, '{}', b''), 'commit', include_image=False)
        self.assertFalse(json.loads(request.prompt_text())['condition_notice']['role_image_available'])

    def test_rehashed_boolean_rounds_and_policy_seeds_are_invalid(self):
        with patch('parallax_relay.policies.uniform_seed',return_value=0):
            run=RunProvenance(ProvenanceContext(mode='mock',policy='uniform',trial_id=UUID(int=1)))
            run.begin(MatchSettings(condition='disabled'),{},initial_world().snapshot())
            for kind in ('rounds','seed'):
                data=run.snapshot();block=data['execution']
                if kind=='rounds':block['value']['settings']['communication_rounds']=False
                else:block['value']['policy']['commitment_seeds']['PYRA'][0]=False
                block['sha256']=canonical_hash(block['value'])
                with self.subTest(kind=kind),self.assertRaises(ValueError):read_provenance({'provenance':data})

    def test_prerelease_and_vendor_python_versions_round_trip(self):
        for version in ('3.13.0rc1', '3.12.3+', '3.12.3+vendor-1', '3.14.0a2'):
            with self.subTest(version=version), patch('parallax_relay.policies.platform.python_version', return_value=version):
                run=RunProvenance(ProvenanceContext(mode='mock',policy='uniform',trial_id=UUID(int=1)))
                run.begin(MatchSettings(),{},initial_world().snapshot())
                self.assertEqual(read_provenance({'provenance':run.snapshot()}),run.snapshot())

    def test_rehashed_notice_and_request_version_contradictions_are_rejected(self):
        run=RunProvenance()
        run.begin(MatchSettings(),{},initial_world().snapshot())
        for kind in ('notice','version','prompt'):
            data=run.snapshot()
            if kind=='prompt':
                block=data['inputs']['prompt'];block['value']+=' tampered'
            else:
                block=data['inputs']['schemas']
                if kind=='notice':block['value']['request_structure']['condition_notice']={'tampered':True}
                else:block['value']['request_format_version']=1
            block['sha256']=canonical_hash(block['value'])
            with self.subTest(kind=kind),self.assertRaises(ValueError):read_provenance({'provenance':data})

    def test_image_reserve_difference_is_exact(self):
        from parallax_relay.budget import Budget
        request=AgentRequest(Observation('SPECTRA',0,'{}',b''),'commit')
        rates={r:Rates(input_per_million=1,output_per_million=1) for r in ROLES}
        a=Budget(MatchSettings(image_token_reserve=8192),rates).reserve_phase({'SPECTRA':request})['SPECTRA']
        b=Budget(MatchSettings(image_token_reserve=1),rates).reserve_phase({'SPECTRA':request})['SPECTRA']
        self.assertEqual(a.quote-b.quote,Decimal(8191)/Decimal(1000000))


class ControlsIntegrationReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_exhausted_withheld_phases_do_not_leak_fallbacks(self):
        from parallax_relay.orchestrator import run_match
        seen=[]
        class Bad:
            async def respond(self, request):
                seen.append(request)
                return ModelReply('PRIVATE_SENTINEL',Usage(0,0))
        result=await run_match({r:Bad() for r in ROLES},MatchSettings(condition='withheld',max_turns=2,
                              max_consecutive_failures=20,retry_delay_seconds=0))
        self.assertEqual(result.world.turn,2)
        self.assertTrue(any(m['fallback'] for p in result.phases for m in p.get('messages',[])))
        for request in seen:
            self.assertEqual(request.messages,())
            self.assertNotIn('PRIVATE_SENTINEL',request.prompt_text())
            self.assertNotIn('fallback',request.prompt_text())

    async def test_uniform_communications_do_not_advance_draws_and_no_images_keeps_pngs(self):
        from parallax_relay.policies import UniformAgent
        from parallax_relay.orchestrator import run_match
        from parallax_relay.recording import Recorder
        trial=UUID(int=1)
        agent=UniformAgent('SPECTRA',trial)
        for turn in (0,1):
            request=AgentRequest(Observation('SPECTRA',turn,'{}',b''),'commit')
            before=await agent.respond(request)
            for phase in ('broadcast','negotiate'):
                self.assertEqual(json.loads((await agent.respond(replace(request,phase=phase))).text)['message'],'')
            self.assertEqual(before,await agent.respond(request))
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'run'
            recorder=Recorder(out,{},context=ProvenanceContext(mode='mock',policy='uniform',trial_id=trial))
            await run_match({r:UniformAgent(r,trial) for r in ROLES},MatchSettings(condition='no_images',max_turns=2),recorder=recorder)
            for turn in range(2):
                for role in ROLES:
                    self.assertTrue((out/f'turn_{turn:02d}_{role.lower()}.png').read_bytes().startswith(b'\x89PNG'))
