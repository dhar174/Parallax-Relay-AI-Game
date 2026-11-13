import base64
import json
import unittest
import httpx
from parallax_relay.protocol import AgentRequest
from parallax_relay.observations import observe
from parallax_relay.state import initial_world
from parallax_relay.providers import HTTPAgent, ProviderError


def response_for(provider, text='{"turn":0,"message":"hello"}'):
    if provider == 'openai':
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}], 'usage':{'input_tokens':100,'output_tokens':20,'input_tokens_details':{'cached_tokens':10}}}
    if provider == 'anthropic':
        return {'type':'message','stop_reason':'end_turn','content':[{'type':'text','text':text}], 'usage':{'input_tokens':80,'output_tokens':20,'cache_read_input_tokens':20}}
    return {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text}]}}], 'usageMetadata':{'promptTokenCount':100,'candidatesTokenCount':15,'thoughtsTokenCount':5}}


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def get_reply(self, provider, payload=None, status=200, request=None, headers=None):
        seen = []
        def handler(req):
            seen.append(req)
            return httpx.Response(status, json=payload if payload is not None else response_for(provider), headers=headers)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            agent = HTTPAgent(provider, 'test-model', 'SECRET_KEY', client=client)
            reply = await agent.respond(request or AgentRequest(observe(initial_world(),'SPECTRA'),'broadcast'))
        return reply, seen

    async def test_openai_request_contains_png_schema_and_no_server_history(self):
        reply, seen = await self.get_reply('openai')
        body = json.loads(seen[0].content)
        self.assertEqual(seen[0].url.path,'/v1/responses')
        self.assertEqual(seen[0].headers['authorization'],'Bearer SECRET_KEY')
        self.assertFalse(body['store'])
        self.assertTrue(body['text']['format']['strict'])
        self.assertEqual(body['text']['format']['type'],'json_schema')
        uri = body['input'][0]['content'][0]['image_url']
        self.assertEqual(base64.b64decode(uri.split(',')[1]), observe(initial_world(),'SPECTRA').image_png)
        self.assertNotIn('previous_response_id',body)
        self.assertEqual(reply.usage.input_tokens,100)

    async def test_anthropic_request_contains_schema_and_image(self):
        reply, seen = await self.get_reply('anthropic')
        body=json.loads(seen[0].content)
        self.assertEqual(seen[0].url.path,'/v1/messages')
        self.assertEqual(seen[0].headers['x-api-key'],'SECRET_KEY')
        self.assertEqual(seen[0].headers['anthropic-version'],'2026-10-21')
        self.assertEqual(body['output_config']['format']['type'],'json_schema')
        self.assertEqual(body['messages'][0]['content'][0]['source']['media_type'],'image/png')
        self.assertEqual(reply.usage.input_tokens,100)
        self.assertNotIn('temperature',body)

    async def test_gemini_request_and_thinking_usage(self):
        reply,seen=await self.get_reply('gemini')
        body=json.loads(seen[0].content)
        self.assertEqual(seen[0].url.path,'/v1beta/models/test-model:generateContent')
        self.assertEqual(seen[0].headers['x-goog-api-key'],'SECRET_KEY')
        self.assertEqual(seen[0].url.query,b'')
        self.assertEqual(body['contents'][0]['parts'][0]['inlineData']['mimeType'],'image/png')
        self.assertEqual(body['generationConfig']['responseMimeType'],'application/json')
        self.assertIn('responseJsonSchema',body['generationConfig'])
        self.assertEqual(reply.usage.output_tokens,20)
        self.assertEqual(reply.usage.reasoning_output_tokens,5)

    async def test_commit_is_structured_on_every_provider(self):
        request=AgentRequest(observe(initial_world(),'FLUX'),'commit',max_output_tokens=3072)
        for provider in ('openai','anthropic','gemini'):
            with self.subTest(provider=provider):
                _,seen=await self.get_reply(provider,request=request)
                body=json.loads(seen[0].content)
                schema = body['text']['format']['schema'] if provider=='openai' else body['output_config']['format']['schema'] if provider=='anthropic' else body['generationConfig']['responseJsonSchema']
                self.assertIn('action',schema['properties'])
                self.assertNotIn('tools',body)
                self.assertIn('3072',str(body))

    async def test_http_errors_are_sanitized_and_classified(self):
        for status,retryable in ((401,False),(403,False),(404,False),(400,False),(429,True),(503,True)):
            with self.subTest(status=status):
                with self.assertRaises(ProviderError) as ctx:
                    await self.get_reply('openai',{'error':{'message':'SECRET_KEY'}},status=status)
                self.assertEqual(ctx.exception.retryable,retryable)
                self.assertNotIn('SECRET_KEY',str(ctx.exception))
                self.assertEqual(ctx.exception.status_code,status)

    async def test_insufficient_quota_is_not_retried(self):
        with self.assertRaises(ProviderError) as ctx:
            await self.get_reply('openai',{'error':{'code':'insufficient_quota'}},status=429)
        self.assertFalse(ctx.exception.retryable)

    async def test_incomplete_is_not_a_valid_action(self):
        for provider in ('openai','anthropic','gemini'):
            payload=response_for(provider)
            if provider=='openai': payload['status']='incomplete'
            elif provider=='anthropic': payload['stop_reason']='max_tokens'
            else: payload['candidates'][0]['finishReason']='MAX_TOKENS'
            reply,_=await self.get_reply(provider,payload)
            self.assertEqual(reply.status,'incomplete')

    async def test_refusal_keeps_usage(self):
        payload=response_for('openai')
        payload['output'][0]['content']=[{'type':'refusal','refusal':'No'}]
        reply,_=await self.get_reply('openai',payload)
        self.assertEqual(reply.status,'refusal')
        self.assertEqual(reply.usage.output_tokens,20)

    async def test_missing_usage_remains_unknown(self):
        payload=response_for('gemini'); payload.pop('usageMetadata')
        reply,_=await self.get_reply('gemini',payload)
        self.assertIsNone(reply.usage.input_tokens)
        self.assertIsNone(reply.usage.output_tokens)

    async def test_thought_blocks_are_not_public_text(self):
        payload=response_for('gemini')
        payload['candidates'][0]['content']['parts'].insert(0,{'thought':True,'text':'PRIVATE_THOUGHT'})
        reply,_=await self.get_reply('gemini',payload)
        self.assertNotIn('PRIVATE_THOUGHT',reply.text)

    async def test_redirect_does_not_resend_secret(self):
        with self.assertRaises(ProviderError) as ctx:
            await self.get_reply('openai',{},status=307,headers={'location':'https://example.invalid/steal'})
        self.assertFalse(ctx.exception.retryable)

    def test_unknown_provider_and_model_path_rejected(self):
        for provider,model in [('other','model'),('gemini','../../steal')]:
            with self.assertRaises(ValueError): HTTPAgent(provider,model,'secret')
