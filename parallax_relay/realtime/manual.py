"""A human control slot, bound to one outstanding host request."""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import Future
from contextlib import suppress
from dataclasses import dataclass, field
from threading import Lock

from ..protocol import ModelReply, ReplyValidationError
from .wire import validate_actions


_RECEIPT_WAIT_SECONDS = 2.0


@dataclass
class _Submission:
    payload: str
    points: int
    receipt: Future[bool] = field(default_factory=Future)
    delivered: bool = False


@dataclass
class _Slot:
    window: int
    request_id: str
    intake: asyncio.Future[str]
    submission: _Submission | None = None


class ManualControls:
    def __init__(self, settings, emit):
        self.settings = settings
        self.emit = emit
        self._lock = Lock()
        self._slots: dict[str, _Slot] = {}
        self._receipts: dict[tuple[str, int, str], _Submission] = {}
        self._closed = False

    async def commit(self, request):
        slot = _Slot(request.window, request.request_id, asyncio.get_running_loop().create_future())
        with self._lock:
            if self._closed:
                raise asyncio.CancelledError
            previous = self._slots.get(request.role)
            if previous is not None:
                self._settle(previous, False)
            self._slots[request.role] = slot
        try:
            self.emit('manual_request', window=request.window, role=request.role,
                      request_id=request.request_id)
            return ModelReply(await slot.intake)
        except (Exception, asyncio.CancelledError):
            with self._lock:
                if self._slots.get(request.role) is slot:
                    self._slots.pop(request.role)
                    self._settle(slot, False)
            raise

    @staticmethod
    def _settle(slot, accepted):
        submission = slot.submission
        if submission is not None and not submission.receipt.done():
            submission.receipt.set_result(accepted and submission.delivered)

    def admitted(self, role, window, status):
        """Resolve the active submission once the coordinator decides its disposition."""
        with self._lock:
            slot = self._slots.get(role)
            if slot is not None and slot.window == window:
                del self._slots[role]
                self._settle(slot, status == 'ok')

    def close(self):
        """Release pending receipt waiters during session finalization."""
        with self._lock:
            self._closed = True
            slots = self._slots
            self._slots = {}
            for slot in slots.values():
                self._settle(slot, False)
        for slot in slots.values():
            with suppress(RuntimeError):
                slot.intake.get_loop().call_soon_threadsafe(slot.intake.cancel)

    def _deliver(self, slot, submission):
        # A thread may revoke queued delivery before the coordinator loop runs it.
        with self._lock:
            if not submission.receipt.done() and not slot.intake.done():
                slot.intake.set_result(submission.payload)
                submission.delivered = True

    def submit(self, data):
        if not isinstance(data, dict) or set(data) != {'window', 'role', 'request_id', 'actions'}:
            return {'ok': False, 'error': 'Expected a window, role, request ID and action list.'}
        role, window, request_id = data['role'], data['window'], data['request_id']
        if not isinstance(role, str) or type(window) is not int or not isinstance(request_id, str):
            return {'ok': False, 'error': 'Invalid role or window.'}
        try:
            points = validate_actions(data['actions'], self.settings)
        except (ValueError, ReplyValidationError) as exc:
            return {'ok': False, 'error': getattr(exc, 'detail', 'Invalid action plan.')}
        payload = json.dumps(dict(window=window, request_id=request_id, actions=data['actions'], notes=''),
                             sort_keys=True, separators=(',', ':'))
        key = (role, window, request_id)
        with self._lock:
            submission = self._receipts.get(key)
            duplicate = submission is not None
            slot = self._slots.get(role)
            if submission is not None:
                if submission.payload != payload:
                    return {'ok': False, 'error': 'A different plan was already submitted for this request.'}
            elif slot is None or (slot.window, slot.request_id) != (window, request_id):
                return {'ok': False, 'error': 'That request is closed.'}
            else:
                submission = self._receipts[key] = slot.submission = _Submission(payload, points)
                try:
                    slot.intake.get_loop().call_soon_threadsafe(self._deliver, slot, submission)
                except RuntimeError:
                    self._settle(slot, False)

        receipt = submission.receipt
        try:
            accepted = receipt.result(timeout=_RECEIPT_WAIT_SECONDS)
        except TimeoutError:
            with self._lock:
                if not receipt.done():
                    if submission.delivered:
                        return {'ok': False, 'error': 'The host has not confirmed this plan. Retry the same submission.'}
                    receipt.set_result(False)
                accepted = receipt.result()
        if not accepted:
            return {'ok': False, 'error': 'That request is closed.'}
        result = {'ok': True, 'points': submission.points}
        if duplicate:
            result['duplicate'] = True
        return result


class ManualAgent:
    def __init__(self, announcer, controls):
        self.announcer = announcer
        self.controls = controls

    async def respond(self, request):
        if request.phase == 'commit':
            return await self.controls.commit(request)
        return await self.announcer.respond(request)

    async def close(self):
        await self.announcer.close()
