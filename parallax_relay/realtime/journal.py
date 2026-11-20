"""Durable local event journal and deterministic physics recording.

Public event projection is the caller's responsibility. The spectator can
read released programs. Private observations and accounting have their own file.
"""
from __future__ import annotations

import hashlib
import bisect
from collections import deque
import heapq
import json
import os
from pathlib import Path
import threading
import uuid
from typing import Any

VERSION = 2
POSE_CAPACITY = 256
EVENT_PAGE_SIZE = 256


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _detach(value: Any) -> Any:
    return json.loads(_bytes(value))


def _state(world: Any) -> Any:
    # The public snapshot intentionally omits recovery and control latches.
    return world.replay_state()


def _write_new(path: Path, content: bytes) -> None:
    with path.open('xb') as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


class Journal:
    """A fresh single-run journal. Failed writes permanently stop publication."""

    def __init__(self, out: Path, *, run_id: str | None = None):
        if run_id is None:
            run_id = str(uuid.uuid4())
        try:
            if type(run_id) is not str or str(uuid.UUID(run_id)) != run_id:
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError('run_id must be a canonical UUID string') from None
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=False)
        self.run_id = run_id
        self.tick = 0
        self.window = 0
        self._seq = 0
        self._semantic: list[dict[str, Any]] = []
        self._semantic_seqs: list[int] = []
        self._poses: deque[dict[str, Any]] = deque()
        self._pinned: list[dict[str, Any]] = []
        self._pinned_seqs: list[int] = []
        self._dropped_pose_through = 0
        self._lock = threading.RLock()
        self._failed = False
        self._started = False
        self._finished = False
        self._programs_digest: str | None = None
        self._recorded_tick = 0
        _write_new(self.out / 'manifest.json', _bytes({'version': VERSION, 'run_id': self.run_id}) + b'\n')
        for name in ('events.jsonl', 'private.jsonl', 'simulation.jsonl'):
            _write_new(self.out / name, b'')
        (self.out / 'feeds').mkdir()

    def _append(self, name: str, record: dict[str, Any]) -> None:
        if self._failed:
            raise RuntimeError('journal is unavailable after a write failure')
        try:
            line = _bytes(record) + b'\n'
            with (self.out / name).open('ab') as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            self._failed = True
            raise

    def emit(self, kind: str, **data: Any) -> dict[str, Any]:
        """Persist a caller-projected public event before advertising it."""
        with self._lock:
            if not isinstance(kind, str) or not kind:
                raise ValueError('kind must be a nonempty string')
            if {'run_id', 'seq', 'kind'} & data.keys():
                raise ValueError('reserved event field')
            tick = data.pop('tick', self.tick)
            window = data.pop('window', self.window)
            if type(tick) is not int or tick < 0 or type(window) is not int or window < 0:
                raise ValueError('tick and window must be nonnegative integers')
            record = {'run_id': self.run_id, 'seq': self._seq + 1,
                      'kind': kind, 'tick': tick, 'window': window, **data}
            # Round-trip freezes mutable caller data and validates JSON before writing.
            record = json.loads(_bytes(record))
            self._append('events.jsonl', record)
            self.tick, self.window = tick, window
            self._seq += 1
            if kind == 'state':
                self._poses.append(record)
                if len(self._poses) > POSE_CAPACITY:
                    removed = self._poses.popleft()
                    self._dropped_pose_through = removed['seq']
            else:
                # The state immediately preceding a consequence is useful for
                # reconstructing the contact even after ordinary poses age out.
                if kind == 'consequence' and self._poses:
                    pose = self._poses[-1]
                    if not self._pinned_seqs or pose['seq'] > self._pinned_seqs[-1]:
                        self._pinned.append(pose)
                        self._pinned_seqs.append(pose['seq'])
                self._semantic.append(record)
                self._semantic_seqs.append(record['seq'])
        return _detach(record)

    def events(self, after: int = 0, limit: int = EVENT_PAGE_SIZE) -> dict[str, Any]:
        """Return a bounded page. Seq gaps indicate superseded pose samples.

        Cursor is the last delivered sequence, not the current watermark. A
        reset indicates lost pose continuity, never missing semantic events.
        Continue using cursor while has_more; do not clear the transcript.
        """
        if type(after) is not int or type(limit) is not int or not 1 <= limit <= EVENT_PAGE_SIZE:
            raise ValueError('invalid cursor or page limit')
        with self._lock:
            watermark = self._seq
            invalid = after < 0 or after > watermark
            start = 0 if invalid else after
            reset = invalid or start < self._dropped_pose_through
            semantic_idx = bisect.bisect_right(self._semantic_seqs, start)
            pinned_idx = bisect.bisect_right(self._pinned_seqs, start)
            # Capture at most one page from each ordered source, under the lock.
            # JSON serialization and all copying of nested data occur later.
            semantic = self._semantic[semantic_idx:semantic_idx + limit + 1]
            pinned = self._pinned[pinned_idx:pinned_idx + limit + 1]
            poses = [item for item in self._poses if item['seq'] > start][:limit + 1]
            run_id = self.run_id
        rows = []
        previous = None
        for item in heapq.merge(semantic, pinned, poses, key=lambda e: e['seq']):
            if item['seq'] != previous:
                rows.append(item)
                previous = item['seq']
                if len(rows) > limit:
                    break
        has_more = len(rows) > limit
        rows = rows[:limit]
        cursor = rows[-1]['seq'] if rows else start
        return {'run_id': run_id, 'cursor': cursor, 'watermark': watermark,
                'reset': reset, 'has_more': has_more, 'events': _detach(rows)}

    def private(self, kind: str, **data: Any) -> None:
        with self._lock:
            self._append('private.jsonl', {'version': VERSION, 'run_id': self.run_id,
                                          'kind': kind, 'tick': self.tick,
                                          'window': self.window, 'data': data})

    @staticmethod
    def _feed_name(role: str, window: int) -> str:
        if role not in ('SPECTRA', 'PYRA', 'FLUX') or type(window) is not int or window < 0:
            raise ValueError('invalid feed identity')
        return f'{window}-{role}.png'

    def store_feed(self, role: str, window: int, png: bytes) -> None:
        with self._lock:
            if self._failed:
                raise RuntimeError('journal is unavailable after a write failure')
            if not isinstance(png, bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('feed must be PNG bytes')
            path = self.out / 'feeds' / self._feed_name(role, window)
            try:
                _write_new(path, png)
            except Exception:
                self._failed = True
                raise

    def feed(self, role: str, window: int) -> bytes | None:
        with self._lock:
            path = self.out / 'feeds' / self._feed_name(role, window)
            try:
                return path.read_bytes()
            except FileNotFoundError:
                return None

    def record_initial(self, world: Any) -> None:
        with self._lock:
            if self._started or world.tick != 0:
                raise ValueError('initial world must be recorded once at tick zero')
            self._append('simulation.jsonl', {'version': VERSION, 'run_id': self.run_id,
                                              'type': 'initial', 'tick': 0,
                                              'state_hash': _digest(_state(world))})
            self._started = True

    def record_tick(self, world: Any, programs: dict[str, Any], offset: int) -> None:
        """Persist inputs and state hash for exactly one already-resolved tick."""
        with self._lock:
            if not self._started or self._finished or world.tick != self._recorded_tick + 1:
                raise ValueError('simulation ticks must be recorded once in order')
            if type(offset) is not int or offset < 0:
                raise ValueError('invalid program offset')
            digest = _digest(programs)
            record: dict[str, Any] = {'version': VERSION, 'run_id': self.run_id,
                                      'type': 'tick', 'tick': world.tick,
                                      'offset': offset, 'programs_hash': digest,
                                      'state_hash': _digest(_state(world))}
            if digest != self._programs_digest:
                record['programs'] = programs
            self._append('simulation.jsonl', record)
            self._programs_digest = digest
            self._recorded_tick = world.tick
            self.tick = world.tick

    def finish(self, reason: str) -> None:
        with self._lock:
            if not self._started or self._finished or not isinstance(reason, str) or not reason:
                raise ValueError('invalid simulation finish')
            self._append('simulation.jsonl', {'version': VERSION, 'run_id': self.run_id,
                                              'type': 'finish', 'tick': self._recorded_tick,
                                              'reason': reason})
            self._finished = True


def replay(out: Path) -> dict[str, Any]:
    """Re-run every recorded physics tick; reject partial or mismatched runs."""
    from .physics import initial_world, step

    out = Path(out)
    manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
    version = manifest.get('version')
    declared_run_id = manifest.get('run_id')
    if type(version) is not int or version not in (1, VERSION) or not isinstance(declared_run_id, str):
        raise ValueError('unsupported or invalid recording manifest')
    if version == VERSION:
        try:
            if str(uuid.UUID(declared_run_id)) != declared_run_id:
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError('invalid recording identity') from None
    raw = (out / 'simulation.jsonl').read_bytes()
    if not raw.endswith(b'\n'):
        raise ValueError('incomplete simulation journal')
    records = [json.loads(line) for line in raw.splitlines()]
    if version == VERSION:
        if any(type(row) is not dict or row.get('version') != VERSION or
               row.get('run_id') != declared_run_id for row in records):
            raise ValueError('simulation identity mismatch')
        private_path = out / 'private.jsonl'
        if private_path.exists():
            private_raw = private_path.read_bytes()
            if private_raw and not private_raw.endswith(b'\n'):
                raise ValueError('incomplete private journal')
            private_rows = [json.loads(line) for line in private_raw.splitlines()]
            if any(type(row) is not dict or row.get('version') != VERSION or
                   row.get('run_id') != declared_run_id for row in private_rows):
                raise ValueError('private journal identity mismatch')
        result_path = out / 'result.json'
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if type(result) is not dict or result.get('run_id') != declared_run_id:
                raise ValueError('result identity mismatch')
    if not records or records[0].get('type') != 'initial' or records[0].get('tick') != 0:
        raise ValueError('missing initial simulation state')
    world = initial_world()
    if _digest(_state(world)) != records[0].get('state_hash'):
        raise ValueError('initial state mismatch')
    programs = None
    program_hash = None
    finished = False
    for index, record in enumerate(records[1:], 1):
        if record.get('type') == 'finish':
            if index != len(records) - 1 or record.get('tick') != world.tick or not record.get('reason'):
                raise ValueError('invalid finish record')
            finished = True
            continue
        if record.get('type') != 'tick' or record.get('tick') != world.tick + 1:
            raise ValueError('invalid tick sequence')
        if 'programs' in record:
            programs = record['programs']
            program_hash = _digest(programs)
        if programs is None or program_hash != record.get('programs_hash'):
            raise ValueError('invalid programs reference')
        offset = record.get('offset')
        if type(offset) is not int or offset < 0:
            raise ValueError('invalid tick offset')
        step(world, programs, offset)
        if _digest(_state(world)) != record.get('state_hash'):
            raise ValueError(f'simulation mismatch at tick {world.tick}')
    if not finished:
        raise ValueError('recording has no finish marker')
    return {'run_id': declared_run_id if version == VERSION else None,
            'declared_run_id': declared_run_id, 'identity_status': 'bound' if version == VERSION else 'unknown',
            'record_version': version, 'ticks': world.tick,
            'reason': records[-1]['reason'], 'state': world.snapshot()}
