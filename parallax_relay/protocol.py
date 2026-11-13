"""Provider-independent, immutable inputs and strict structured player outputs.

No WorldState reference belongs here. An agent is given values, never a pointer
back to the simulation, another agent's private context, or the spectator log.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .state import Action

ROLES = ('SPECTRA', 'PYRA', 'FLUX')
Phase = Literal['broadcast', 'negotiate', 'commit']
MAX_MESSAGE_CHARS = 400
MAX_NOTES_CHARS = 1000
MAX_REPLY_CHARS = 16384


@dataclass(frozen=True)
class Observation:
    role: str
    turn: int
    hud_json: str
    image_png: bytes

    @property
    def hud(self) -> dict:
        # Parse afresh so a consumer cannot mutate a shared observation.
        return json.loads(self.hud_json)


@dataclass(frozen=True)
class ChatMessage:
    role: str
    turn: int
    phase: str
    text: str
    fallback: bool = False


@dataclass(frozen=True)
class AgentRequest:
    observation: Observation
    phase: Phase
    messages: tuple[ChatMessage, ...] = ()
    history_json: str = '[]'
    private_notes: str = ''
    repair: str = ''
    max_output_tokens: int = 2048

    @property
    def role(self) -> str:
        return self.observation.role

    @property
    def turn(self) -> int:
        return self.observation.turn

    def prompt_text(self) -> str:
        return json.dumps({
            'role': self.role,
            'turn': self.turn,
            'phase': self.phase,
            'observation': self.observation.hud,
            'public_messages': [asdict(m) for m in self.messages],
            'your_recent_history': json.loads(self.history_json),
            'your_private_notes': self.private_notes,
            'format_repair': self.repair,
        }, ensure_ascii=True, separators=(',', ':'))


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int = 0
    reasoning_output_tokens: int = 0


@dataclass(frozen=True)
class ModelReply:
    text: str
    usage: Usage = Usage()
    status: Literal['ok', 'refusal', 'incomplete'] = 'ok'


class Agent(Protocol):
    async def respond(self, request: AgentRequest) -> ModelReply: ...
    async def close(self) -> None: ...


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class ActionReply(StrictModel):
    kind: Literal['MOVE', 'WAIT', 'VENT', 'REROUTE', 'COLLECT', 'UNLOCK']
    direction: int
    steps: int

    def to_engine(self) -> Action:
        # Gameplay legality is deliberately left to the engine, not repaired.
        return Action(self.kind, self.direction, self.steps)


class BroadcastReply(StrictModel):
    turn: int
    message: str = Field(max_length=MAX_MESSAGE_CHARS)


class CommitReply(StrictModel):
    turn: int
    action: ActionReply
    notes: str = Field(max_length=MAX_NOTES_CHARS)


class ReplyValidationError(ValueError):
    """Safe error: never includes untrusted response bodies or private values."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def parse_reply(text: str, phase: Phase, turn: int) -> BroadcastReply | CommitReply:
    if phase not in ('broadcast', 'negotiate', 'commit'):
        raise ValueError('Unknown phase')
    if not isinstance(text, str) or len(text) > MAX_REPLY_CHARS:
        raise ReplyValidationError('response_size')
    try:
        data = json.loads(text, object_pairs_hook=_unique_object)
        cls = CommitReply if phase == 'commit' else BroadcastReply
        result = cls.model_validate(data)
    except (ValueError, TypeError, ValidationError, RecursionError) as exc:
        raise ReplyValidationError('invalid_json_schema') from None
    if result.turn != turn:
        raise ReplyValidationError('stale_turn')
    return result


def response_schema(phase: Phase) -> dict:
    """Small common subset of the three providers' JSON Schema support.

    Length constraints are enforced locally; some providers do not support
    these schema keywords. All keys are required, including direction/steps.
    Non-MOVE zeros are enforced as engine legality, not schema validation.
    """
    if phase not in ('broadcast', 'negotiate', 'commit'):
        raise ValueError('Unknown phase')
    props = {'turn': {'type': 'integer', 'description': 'Echo the supplied zero-based turn.'}}
    if phase == 'commit':
        props.update({
            'action': {
                'type': 'object', 'additionalProperties': False,
                'properties': {
                    'kind': {'type': 'string', 'enum': ['MOVE', 'WAIT', 'VENT', 'REROUTE', 'COLLECT', 'UNLOCK']},
                    'direction': {'type': 'integer', 'description': 'MOVE: -1 or 1; otherwise 0.'},
                    'steps': {'type': 'integer', 'description': 'MOVE: 1 or 2; otherwise 0.'},
                },
                'required': ['kind', 'direction', 'steps'],
            },
            'notes': {'type': 'string', 'description': 'At most 1000 characters of factual notes for your next turn, not a reasoning transcript. Private. Empty allowed.'},
        })
    else:
        props['message'] = {'type': 'string', 'description': 'One public message, at most 400 characters. Empty allowed.'}
    return {'type': 'object', 'properties': props, 'required': list(props), 'additionalProperties': False}
