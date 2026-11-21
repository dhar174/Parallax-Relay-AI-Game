"""Explicitly synthetic, offline-only provider wire fixture.

The transport reconstructs a role request exclusively from the serialized wire
body, including its transmitted PNG, then invokes the local reactive controller.
No credential lookup or network transport is used.
"""
from __future__ import annotations

from asyncio import sleep
import base64
from dataclasses import replace
import json
import math
from pathlib import Path

import httpx

from ..protocol import Observation, Phase, ROLES
from ..providers import HTTPAgent
from .players import ReactiveAgent
from .wire import PHASES, make_request


FIXTURE_ROSTER = {
    'SPECTRA': ('openai', 'gpt-6-luna'),
    'PYRA': ('openai', 'gpt-6-luna'),
    'FLUX': ('gemini', 'gemini-3.5-flash-lite'),
}


def historical_delays(scale: float = 1.0) -> tuple[dict[Phase, float], ...]:
    """Return the sanitized November 15 samples by phase in roster order.

    Scale is explicit so tests can replay the relative timing without a long wait.
    The same delay applies to each attempt in a role and phase.
    """
    if not math.isfinite(scale) or scale < 0:
        raise ValueError('scale must be finite and nonnegative')
    path = Path(__file__).resolve().parents[2] / 'docs' / 'verification' / '2026-11-15-slice7-live-retry-summary.json'
    rows = json.loads(path.read_text(encoding='utf-8'))['attempts']
    result = []
    for role in ROLES:
        samples = {}
        for phase in PHASES:
            matches = [row for row in rows if row['role'] == role and row['phase'] == phase and row['status'] == 'ok']
            if len(matches) != 1:
                raise ValueError('historical trace is incomplete or ambiguous')
            samples[phase] = float(matches[0]['latency_seconds']) * scale
        result.append(samples)
    return tuple(result)


class _FixtureAgent(HTTPAgent):
    source = 'test_fixture_http'

    def __init__(self, role, provider, model, settings, delays):
        self.role = role
        self._fixture_settings = settings
        self._delays = delays
        self._calls = 0
        self._controller = ReactiveAgent(role)
        client = httpx.AsyncClient(transport=httpx.MockTransport(self._handle), follow_redirects=False)
        super().__init__(provider, model, 'offline-fixture-only', client=client)

    async def close(self):
        await self._client.aclose()
        await self._controller.close()

    async def _handle(self, http_request):
        body = json.loads(http_request.content)
        if self.provider == 'openai':
            parts = body['input'][0]['content']
            image_url = next(part['image_url'] for part in parts if part['type'] == 'input_image')
            prefix = 'data:image/png;base64,'
            if not image_url.startswith(prefix):
                raise ValueError('fixture requires a transmitted PNG')
            image = base64.b64decode(image_url[len(prefix):], validate=True)
            text = next(part['text'] for part in parts if part['type'] == 'input_text')
        else:
            parts = body['contents'][0]['parts']
            inline = next(part['inlineData'] for part in parts if 'inlineData' in part)
            if inline['mimeType'] != 'image/png':
                raise ValueError('fixture requires a transmitted PNG')
            image = base64.b64decode(inline['data'], validate=True)
            text = next(part['text'] for part in parts if 'text' in part)
        payload = json.loads(text)
        if payload['role'] != self.role or payload['observation']['role'] != self.role:
            raise ValueError('fixture role mismatch')
        obs = Observation(self.role, payload['window'], json.dumps(payload['observation']), image)
        request = make_request(obs, payload['phase'], payload['public_messages'],
                               payload['your_recent_history'], payload['your_private_notes'],
                               payload['window'], payload['request_id'], self._fixture_settings)
        request = replace(request, repair=payload['format_repair'])
        # Reject mismatched settings instead of silently inventing controller inputs.
        if json.loads(request.prompt_text()) != payload:
            raise ValueError('fixture request does not round-trip')
        if isinstance(self._delays, dict):
            delay = self._delays[request.phase]
        else:
            delay = self._delays[self._calls % len(self._delays)]
            self._calls += 1
        if delay:
            await sleep(delay)
        reply = await self._controller.respond(request)
        if self.provider == 'openai':
            response = {'status': 'completed', 'output': [{'type': 'message', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': reply.text}]}],
                        'usage': {'input_tokens': 256, 'output_tokens': 64}}
        else:
            response = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': reply.text}]}}],
                        'usageMetadata': {'promptTokenCount': 256, 'candidatesTokenCount': 64}}
        return httpx.Response(200, json=response)


def fixture_agents(settings, delays=(0.0, 0.0, 0.0)):
    """Build independent OpenAI/OpenAI/Gemini mock HTTP clients, in roster order.

    Each delay schedule may be a number of seconds, a nonempty cyclic sequence
    of per-call seconds, or a dictionary of seconds for every phase.
    The agents own and close their injected async clients.
    """
    if len(delays) != len(ROLES):
        raise ValueError('one delay per role is required')
    schedules = []
    for value in delays:
        if isinstance(value, dict):
            if value.keys() != set(PHASES):
                raise ValueError('fixture delay schedule must cover every phase')
            schedule = value.copy()
            seconds = schedule.values()
        else:
            schedule = tuple(value) if isinstance(value, (list, tuple)) else (value,)
            seconds = schedule
        if not seconds or any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in seconds):
            raise ValueError('fixture delays must be finite and nonnegative')
        schedules.append(schedule)
    return {role: _FixtureAgent(role, *FIXTURE_ROSTER[role], settings, schedule)
            for role, schedule in zip(ROLES, schedules)}
