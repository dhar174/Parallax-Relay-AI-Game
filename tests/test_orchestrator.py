import asyncio
import json
import unittest
from dataclasses import replace
from parallax_relay.orchestrator import run_match
from parallax_relay.agents import ScriptedAgent
from parallax_relay.protocol import ModelReply, Usage, ROLES
from parallax_relay.config import MatchSettings
from parallax_relay.providers import ProviderError


def reply(request, action='WAIT', notes='', message='hello'):
    payload={'turn':request.turn}
    if request.phase=='commit': payload.update(action={'kind':action,'direction':0,'steps':0},notes=notes)
    else: payload['message']=message
    return ModelReply(json.dumps(payload),Usage(20,10))


class Spy:
    def __init__(self, fn=None): self.requests=[]; self.fn=fn
    async def respond(self, request):
        self.requests.append(request)
        if self.fn: return await self.fn(request)
        return reply(request)
    async def close(self): pass


class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_scripted_agent_wins_through_real_driver(self):
        result=await run_match({r:ScriptedAgent(r) for r in ROLES})
        self.assertEqual(result.stop_reason,'victory')
        self.assertEqual(result.world.turn,7)
        self.assertEqual(result.summary()['scores'],dict.fromkeys(ROLES,100))
        self.assertEqual(result.budget['calls_started'],63)

    async def test_fast_mode_has_two_phases(self):
        result=await run_match({r:ScriptedAgent(r) for r in ROLES},MatchSettings(communication_rounds=1))
        self.assertEqual(result.budget['calls_started'],42)
        self.assertTrue(result.world.win)

    async def test_calls_are_concurrent_and_have_phase_barriers(self):
        started={}; gates={}; seen=[]
        async def fn(req):
            seen.append(req)
            started[req.phase]=started.get(req.phase,0)+1
            gate=gates.setdefault(req.phase,asyncio.Event())
            if started[req.phase]==3: gate.set()
            await asyncio.wait_for(gate.wait(),0.5)
            if req.role=='PYRA': await asyncio.sleep(0.005)
            return reply(req,message=req.role+' '+req.phase)
        result=await run_match({r:Spy(fn) for r in ROLES}, MatchSettings(max_turns=1,max_attempts=1))
        self.assertEqual(result.world.turn,1)
        self.assertEqual(started,{'broadcast':3,'negotiate':3,'commit':3})
        for req in seen:
            self.assertEqual(len(req.messages),{'broadcast':0,'negotiate':3,'commit':6}[req.phase])
            self.assertTrue(all(m.phase != req.phase for m in req.messages))

    async def test_private_notes_and_histories_do_not_cross_roles(self):
        async def fn(req): return reply(req,notes='PRIVATE_'+req.role)
        agents={r:Spy(fn) for r in ROLES}
        result=await run_match(agents,MatchSettings(max_turns=2,history_turns=1))
        self.assertEqual(result.world.turn,2)
        for role,agent in agents.items():
            second=next(r for r in agent.requests if r.turn==1)
            self.assertEqual(second.private_notes,'PRIVATE_'+role)
            self.assertEqual(len(json.loads(second.history_json)),1)
            for other in ROLES:
                if other != role: self.assertNotIn('PRIVATE_'+other,second.prompt_text())

    async def test_zero_history_retains_only_bounded_private_notes(self):
        async def fn(req): return reply(req,notes='remember')
        agents={r:Spy(fn) for r in ROLES}
        await run_match(agents,MatchSettings(max_turns=2,history_turns=0))
        self.assertTrue(all(r.history_json=='[]' for a in agents.values() for r in a.requests))

    async def test_malformed_reply_gets_one_repair_not_shared_raw_text(self):
        count={}
        async def fn(req):
            key=(req.role,req.phase); count[key]=count.get(key,0)+1
            if req.role=='SPECTRA' and req.phase=='commit' and count[key]==1:
                return ModelReply('MALFORMED_PRIVATE_SENTINEL',Usage(10,10))
            return reply(req)
        agents={r:Spy(fn) for r in ROLES}
        result=await run_match(agents,MatchSettings(max_turns=1,retry_delay_seconds=0))
        self.assertEqual(result.world.turn,1)
        self.assertEqual(count[('SPECTRA','commit')],2)
        self.assertTrue(agents['SPECTRA'].requests[-1].repair)
        self.assertNotIn('MALFORMED_PRIVATE_SENTINEL',json.dumps(result.calls))

    async def test_schema_valid_illegal_action_consumes_turn_without_retry(self):
        async def fn(req): return reply(req,action='VENT')
        agents={r:Spy(fn) for r in ROLES}
        result=await run_match(agents,MatchSettings(max_turns=1))
        self.assertEqual(result.world.turn,1)
        self.assertEqual(len(agents['SPECTRA'].requests),3)
        self.assertIn('SPECTRA: VENT invalid',str(result.world.events))

    async def test_action_timeout_falls_back_to_wait(self):
        async def fn(req):
            if req.role=='SPECTRA' and req.phase=='commit': await asyncio.sleep(1)
            return reply(req)
        result=await run_match({r:Spy(fn) for r in ROLES},MatchSettings(max_turns=1,max_attempts=1,timeout_seconds=0.02))
        self.assertEqual(result.world.turn,1)
        self.assertEqual(result.records[0]['sealed_actions']['SPECTRA']['kind'],'WAIT')
        self.assertEqual(result.records[0]['fallbacks']['SPECTRA'],'timeout')

    async def test_refusal_does_not_retry(self):
        async def fn(req): return ModelReply('',Usage(1,1),'refusal') if req.role=='SPECTRA' and req.phase=='commit' else reply(req)
        agents={r:Spy(fn) for r in ROLES}
        result=await run_match(agents,MatchSettings(max_turns=1))
        self.assertEqual(len(agents['SPECTRA'].requests),3)
        self.assertEqual(result.records[0]['fallbacks']['SPECTRA'],'refusal')

    async def test_fatal_provider_error_aborts_without_state_transition(self):
        async def fn(req): raise ProviderError('http_error',False,401)
        agents={r:Spy(fn if r=='PYRA' else None) for r in ROLES}
        result=await run_match(agents,MatchSettings(max_turns=1))
        self.assertEqual(result.stop_reason,'provider_error')
        self.assertEqual(result.world.turn,0)
        self.assertEqual(result.budget['calls_started'],3)

    async def test_unexpected_exception_message_not_logged(self):
        async def fn(req): raise RuntimeError('API_SECRET_SENTINEL')
        result=await run_match({r:Spy(fn) for r in ROLES},MatchSettings(max_turns=1))
        self.assertEqual(result.stop_reason,'internal_error')
        self.assertNotIn('API_SECRET_SENTINEL',json.dumps(result.calls))

    async def test_call_budget_blocks_entire_phase(self):
        agents={r:Spy() for r in ROLES}
        result=await run_match(agents,MatchSettings(max_calls=5))
        self.assertEqual(result.stop_reason,'call_budget')
        self.assertTrue(all(not a.requests for a in agents.values()))
        self.assertEqual(result.world.turn,0)

    async def test_repeated_failure_circuit_breaker(self):
        async def fn(req): return ModelReply('bad json')
        result=await run_match({r:Spy(fn) for r in ROLES},MatchSettings(max_attempts=1))
        self.assertEqual(result.stop_reason,'unreliable_agent')
        self.assertEqual(result.world.turn,0)

    async def test_two_player_configuration_rejected_not_silently_broken(self):
        with self.assertRaises(ValueError): await run_match({'SPECTRA':Spy(),'PYRA':Spy()})
