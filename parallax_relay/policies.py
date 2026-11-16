"""Declared offline controls, never hidden-state-aware game policies."""
from dataclasses import asdict
import hashlib
import json
import platform
import random
from uuid import UUID

from .agents import ScriptedAgent
from .protocol import AgentRequest, ModelReply, ROLES, Usage
from .state import Action


def canonical_actions(role: str) -> tuple[Action, ...]:
    if role not in ROLES:
        raise ValueError('Unknown role')
    common = (Action('WAIT'), Action('MOVE', -1, 1), Action('MOVE', -1, 2),
              Action('MOVE', 1, 1), Action('MOVE', 1, 2))
    extra = {'SPECTRA': ('COLLECT',), 'PYRA': ('VENT',), 'FLUX': ('REROUTE', 'COLLECT', 'UNLOCK')}
    return common + tuple(Action(kind) for kind in extra[role])


def uniform_seed(trial_id: UUID, role: str, turn: int) -> int:
    canonical_actions(role)
    if type(turn) is not int or turn < 0:
        raise ValueError('Invalid turn')
    key = json.dumps(['uniform-v1', str(UUID(str(trial_id))), role, turn], sort_keys=True,
                     separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf-8')
    return int.from_bytes(hashlib.sha256(key).digest()[:8], 'big')


class WaitAgent:
    def __init__(self, role: str):
        canonical_actions(role)
        self.role = role

    def action(self, request: AgentRequest) -> Action:
        return Action('WAIT')

    async def respond(self, request: AgentRequest) -> ModelReply:
        if request.role != self.role:
            raise ValueError('Role mismatch')
        payload = {'turn': request.turn}
        if request.phase == 'commit':
            payload.update(action=asdict(self.action(request)), notes='')
        else:
            payload['message'] = ''
        return ModelReply(json.dumps(payload), Usage(0, 0))

    async def close(self) -> None:
        pass


class UniformAgent(WaitAgent):
    def __init__(self, role: str, trial_id: UUID):
        super().__init__(role)
        self.trial_id = UUID(str(trial_id))

    def action(self, request: AgentRequest) -> Action:
        actions = canonical_actions(self.role)
        return actions[random.Random(uniform_seed(self.trial_id, self.role, request.turn)).randrange(len(actions))]


def make_policy(name: str, role: str, trial_id: UUID | None = None):
    if name == 'scripted':
        return ScriptedAgent(role)
    if name == 'wait':
        return WaitAgent(role)
    if name == 'uniform' and trial_id is not None:
        return UniformAgent(role, trial_id)
    raise ValueError('Unknown policy or missing uniform trial UUID')


def policy_identity(name: str, trial_id: UUID | None, max_turns: int) -> dict:
    identity = {'name': name, 'version': 1}
    if name == 'uniform':
        identity.update(derivation='sha256-canonical-json-first-8-bytes-big-endian/uniform-v1',
                        python_version=platform.python_version(), prng='random.Random.randrange',
                        trial_id=str(UUID(str(trial_id))),
                        commitment_seeds={r: [uniform_seed(trial_id, r, t) for t in range(max_turns)] for r in ROLES})
    return identity
