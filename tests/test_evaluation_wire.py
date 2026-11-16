"""Exercise actual serialized requests, later turns and repairs in every arm."""
import base64
import json
import unittest

import httpx

from parallax_relay.conditions import CONDITIONS
from parallax_relay.config import MatchSettings
from parallax_relay.orchestrator import run_match
from parallax_relay.providers import HTTPAgent
from parallax_relay.protocol import ROLES


class EvaluationWireTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_provider_treatments_through_intercepted_http_with_retries(self):
        for provider in ('openai', 'anthropic', 'gemini'):
            for arm, condition in CONDITIONS.items():
                seen, attempts = [], {}
                def handle(request):
                    body = json.loads(request.content)
                    parts = (body['input'][0]['content'] if provider == 'openai' else
                             body['messages'][0]['content'] if provider == 'anthropic' else body['contents'][0]['parts'])
                    text = next(p['text'] for p in parts if 'text' in p)
                    prompt = json.loads(text)
                    seen.append((prompt, parts))
                    key = (prompt['role'], prompt['turn'], prompt['phase'])
                    attempts[key] = attempts.get(key, 0) + 1
                    if attempts[key] == 1:
                        answer = 'MALFORMED_PRIVATE_SENTINEL'
                    elif prompt['phase'] == 'commit':
                        answer = json.dumps({'turn': prompt['turn'], 'action': {'kind':'WAIT','direction':0,'steps':0},
                                             'notes':'OWN_NOTE_'+prompt['role']})
                    else:
                        answer = json.dumps({'turn': prompt['turn'], 'message':'MESSAGE_FROM_'+prompt['role']})
                    if provider == 'openai':
                        payload = {'status':'completed','output':[{'type':'message','status':'completed','role':'assistant',
                                    'content':[{'type':'output_text','text':answer}]}],
                                   'usage':{'input_tokens':10,'output_tokens':10}}
                    elif provider == 'anthropic':
                        payload = {'stop_reason':'end_turn','content':[{'type':'text','text':answer}],
                                   'usage':{'input_tokens':10,'output_tokens':10}}
                    else:
                        payload = {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':answer}]}}],
                                   'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':10}}
                    return httpx.Response(200,json=payload)
                async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                    result = await run_match({r:HTTPAgent(provider,'fake-model','fake-key',client=client) for r in ROLES},
                                             MatchSettings(condition=arm,max_turns=2,retry_delay_seconds=0))
                self.assertEqual(result.stop_reason,'turn_limit')
                self.assertEqual(len(seen),12*len(condition.phases))
                for prompt, parts in seen:
                    encoded=json.dumps(prompt)
                    self.assertNotIn('MALFORMED_PRIVATE_SENTINEL',encoded)
                    self.assertEqual(prompt['condition_notice'],condition.notice())
                    if not condition.deliver_messages:
                        self.assertEqual(prompt['public_messages'],[])
                        self.assertNotIn('MESSAGE_FROM_',encoded)
                        self.assertNotIn('fallback',encoded)
                    for role in ROLES:
                        if role != prompt['role']:
                            self.assertNotIn('OWN_NOTE_'+role,encoded)
                    images=[p for p in parts if p.get('type') in ('image','input_image') or 'inlineData' in p]
                    self.assertEqual(len(images),int(condition.include_image))
                    if images:
                        image=images[0]
                        data=(image['image_url'].split(',')[1] if provider=='openai' else
                              image['source']['data'] if provider=='anthropic' else image['inlineData']['data'])
                        self.assertTrue(base64.b64decode(data).startswith(b'\x89PNG'))
