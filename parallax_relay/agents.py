"""Offline scripted fixture. This is NOT an LLM or a reasoning benchmark."""
import json
from dataclasses import asdict
from .protocol import AgentRequest, ModelReply, Usage, ROLES
from .scripted import PLAN, FIRST_BROADCAST
from .state import Action


class ScriptedAgent:
    def __init__(self, role: str):
        if role not in ROLES:
            raise ValueError('Unknown role')
        self.role = role

    async def respond(self, request: AgentRequest) -> ModelReply:
        if request.role != self.role:
            raise ValueError('Role mismatch')
        action = PLAN[request.turn][self.role] if request.turn < len(PLAN) else Action('WAIT')
        payload = {'turn': request.turn}
        if request.phase == 'commit':
            payload.update(action=asdict(action), notes=f'Scripted test fixture. Next plan index: {request.turn + 1}.')
        elif request.phase == 'broadcast':
            payload['message'] = FIRST_BROADCAST[self.role] if request.turn == 0 else f'Test fixture: proposing {action.kind} this round.'
        else:
            payload['message'] = f'Test fixture: received {len(request.messages)} messages; committing to {action.kind}.'
        # Zero usage, not synthetic paid tokens; mock mode cannot spend money.
        return ModelReply(json.dumps(payload), Usage(0, 0))

    async def close(self) -> None:
        pass
