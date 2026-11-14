"""Versioned spectator provenance. Never inspect agents, credentials, or raw config."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import prompts, protocol, state
from .config import MatchSettings
from .providers import provider_contract

ROOT = Path(__file__).resolve().parent.parent


class ProvenanceError(ValueError):
    """Only fixed messages belong in public provenance errors."""


class PlayerIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    provider: Literal['openai', 'anthropic', 'gemini', 'mock', 'unknown'] = 'unknown'
    model: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


class ProvenanceContext(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    mode: Literal['mock', 'live', 'programmatic'] = 'programmatic'
    experiment_id: UUID | None = None
    trial_id: UUID | None = None
    players: dict[str, PlayerIdentity] = Field(default_factory=dict)
    requested_settings: MatchSettings | None = None

    @field_validator('players')
    @classmethod
    def known_roles(cls, value):
        if not set(value) <= set(protocol.ROLES):
            raise ValueError('Unknown role')
        return value


def canonical_hash(value) -> str:
    data = json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _fingerprint(value) -> dict:
    return {'value': deepcopy(value), 'sha256': canonical_hash(value)}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def collect_source(root: Path) -> dict:
    unavailable = {'status': 'unavailable', 'revision': None, 'reason': 'git_unavailable'}
    # Honor the package root, not caller overrides pointing Git at another tree.
    env = {k: v for k, v in os.environ.items()
           if k not in {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR'}}
    env['GIT_OPTIONAL_LOCKS'] = '0'
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], env=env,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=1)
    try:
        identity = git('rev-parse', '--show-toplevel', 'HEAD')
        lines = identity.stdout.splitlines()
        if identity.returncode or len(lines) != 2:
            return unavailable
        if Path(lines[0]).resolve() != root.resolve():
            return {**unavailable, 'reason': 'not_project_root'}
        if not re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', lines[1]):
            return unavailable
        status = git('status', '--porcelain=v1', '--untracked-files=normal')
        if status.returncode:
            return {**unavailable, 'revision': lines[1], 'reason': 'status_unavailable'}
        return {'status': 'dirty' if status.stdout else 'clean', 'revision': lines[1], 'reason': None}
    except subprocess.TimeoutExpired:
        return {**unavailable, 'reason': 'git_timeout'}
    except (OSError, ValueError):
        return unavailable


def collect_environment() -> dict:
    packages, status = [], 'complete'
    try:
        for dist in metadata.distributions():
            try:
                name, version = dist.metadata.get('Name'), dist.version
                if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', name):
                    raise ValueError()
                if not isinstance(version, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.!+_-]{0,127}', version):
                    raise ValueError()
                packages.append({'name': re.sub(r'[-_.]+', '-', name).lower(), 'version': version})
            except Exception:
                status = 'partial'
    except Exception:
        status = 'partial' if packages else 'unavailable'
    return _fingerprint({
        'status': status,
        'python': {'implementation': platform.python_implementation(), 'version': platform.python_version()},
        'os': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()},
        'packages': sorted(packages, key=lambda p: (p['name'], p['version'])),
    })


def input_identities(initial_snapshot: dict) -> dict:
    request = protocol.AgentRequest(protocol.Observation('SPECTRA', 0, '{}', b''), 'commit')
    return {
        'prompt': _fingerprint(prompts.SYSTEM_RULES),
        'schemas': _fingerprint({
            'request_format_version': protocol.REQUEST_FORMAT_VERSION,
            'request_structure': json.loads(request.prompt_text()),
            'wire': {p: protocol.response_schema(p) for p in ('broadcast', 'negotiate', 'commit')},
            'local': {'broadcast': protocol.BroadcastReply.model_json_schema(),
                      'commit': protocol.CommitReply.model_json_schema()},
            'max_reply_chars': protocol.MAX_REPLY_CHARS,
        }),
        'room': _fingerprint({
            'id': 'split_span', 'version': 1,
            'constants': {name: getattr(state, name) for name in
                          ('WIDTH', 'MAX_TURNS', 'EXIT', 'ARTIFACT', 'ENERGY_CELL', 'MOTOR')},
            'gap': sorted(state.GAP), 'objectives': dict(state.PRIVATE_GOALS),
            'initial_state': initial_snapshot,
        }),
    }


class RunProvenance:
    """One Recorder's execution identity; recovery may refresh only its outcome."""
    def __init__(self, context: ProvenanceContext | None = None, *, root: Path = ROOT):
        if context is not None and not isinstance(context, ProvenanceContext):
            raise ProvenanceError('Invalid provenance context')
        context = context or ProvenanceContext()
        self.bound = False
        self._tick = None
        self._mode = context.mode
        players = {}
        for role in protocol.ROLES:
            identity = context.players.get(role, PlayerIdentity())
            known = identity.provider != 'unknown'
            players[role] = {
                **identity.model_dump(), 'identity_source': 'declared' if known else 'unavailable',
                'model_revision': None, 'api_contract': provider_contract(identity.provider),
                'sampling': 'provider_default' if identity.provider in ('openai', 'anthropic', 'gemini')
                            else 'not_applicable' if identity.provider == 'mock' else 'unavailable',
                'seed': None,
            }
        self._data = {
            'schema_version': 1, 'run_id': str(uuid4()),
            'experiment_id': str(context.experiment_id) if context.experiment_id else None,
            'trial_id': str(context.trial_id) if context.trial_id else None,
            'source': collect_source(root), 'environment': collect_environment(), 'players': players,
            'requested_settings': context.requested_settings.model_dump() if context.requested_settings else None,
            'execution': None, 'inputs': None,
            'lifecycle': {'stage': 'initialized', 'created_at': _utc_now(), 'started_at': None,
                          'ended_at': None, 'elapsed_seconds': None,
                          'execution_stop_reason': None, 'stop_reason': None},
        }

    def begin(self, settings, rates, initial_snapshot):
        if self.bound:
            raise ProvenanceError('Recorder already bound to a match')
        config = {'mode': self._mode, 'settings': settings.model_dump(),
                  'pricing': {r: rates[r].model_dump() if rates.get(r) is not None else None
                              for r in protocol.ROLES},
                  'players': self._data['players'],
                  'conditions': {'communication': 'full' if settings.communication_rounds == 2 else 'reduced',
                                 'observations': 'role_png_and_hud'}}
        self._data['execution'] = _fingerprint(config)
        self._data['inputs'] = input_identities(initial_snapshot)
        self._tick = monotonic()
        self._data['lifecycle'].update(stage='running', started_at=_utc_now())
        self.bound = True

    def end(self, result):
        life = self._data['lifecycle']
        if life['stage'] == 'running':
            life.update(stage='ended', ended_at=_utc_now(),
                        elapsed_seconds=max(0.0, monotonic() - self._tick))
        elif life['stage'] == 'initialized':
            life['stage'] = 'external_result'
            self.bound = True
        if life['execution_stop_reason'] is None:
            life['execution_stop_reason'] = result.stop_reason
        life['stop_reason'] = result.stop_reason

    def refresh(self, result):
        self._data['lifecycle']['stop_reason'] = result.stop_reason

    def snapshot(self):
        return deepcopy(self._data)


class _RecordModel(BaseModel):
    model_config = ConfigDict(extra='ignore', strict=True)


class _Fingerprint(_RecordModel):
    value: dict | str
    sha256: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def valid_hash(self):
        if canonical_hash(self.value) != self.sha256:
            raise ValueError('Fingerprint mismatch')
        return self


class _Lifecycle(_RecordModel):
    stage: Literal['initialized', 'running', 'ended', 'external_result']
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    elapsed_seconds: float | None = Field(ge=0)
    execution_stop_reason: str | None
    stop_reason: str | None

    @field_validator('created_at', 'started_at', 'ended_at')
    @classmethod
    def utc(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset().total_seconds() != 0):
            raise ValueError('UTC required')
        return value

    @model_validator(mode='after')
    def consistent_stage(self):
        if self.stage in ('initialized', 'external_result'):
            if any(x is not None for x in (self.started_at, self.ended_at, self.elapsed_seconds)):
                raise ValueError('Unexpected execution times')
        elif self.started_at is None:
            raise ValueError('Missing start time')
        if self.stage == 'ended' and any(x is None for x in
                (self.ended_at, self.elapsed_seconds, self.execution_stop_reason, self.stop_reason)):
            raise ValueError('Missing end metadata')
        if self.stage == 'running' and (self.ended_at is not None or self.elapsed_seconds is not None):
            raise ValueError('Unexpected end metadata')
        return self


class _SourceInfo(_RecordModel):
    status: Literal['clean', 'dirty', 'unavailable']
    revision: str | None = Field(pattern=r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')
    reason: Literal['git_unavailable', 'not_project_root', 'status_unavailable', 'git_timeout'] | None

    @model_validator(mode='after')
    def consistent_status(self):
        if self.status != 'unavailable' and (self.revision is None or self.reason is not None):
            raise ValueError('Missing source identity')
        if self.status == 'unavailable' and self.reason is None:
            raise ValueError('Missing availability reason')
        return self


class _Distribution(_RecordModel):
    name: str
    version: str


class _EnvironmentValue(_RecordModel):
    status: Literal['complete', 'partial', 'unavailable']
    python: dict[str, str]
    os: dict[str, str]
    packages: list[_Distribution]


class _PlayerRecord(_RecordModel):
    provider: str
    model: str | None
    identity_source: Literal['declared', 'unavailable']
    model_revision: str | None
    api_contract: dict | None
    sampling: Literal['provider_default', 'not_applicable', 'unavailable']
    seed: None


class ProvenanceRecord(_RecordModel):
    schema_version: Literal[1]
    run_id: UUID
    experiment_id: UUID | None
    trial_id: UUID | None
    source: _SourceInfo
    environment: _Fingerprint
    players: dict[str, _PlayerRecord]
    requested_settings: dict | None
    execution: _Fingerprint | None
    inputs: dict[str, _Fingerprint] | None
    lifecycle: _Lifecycle

    @model_validator(mode='after')
    def required_structure(self):
        if set(self.players) != set(protocol.ROLES):
            raise ValueError('Missing role identities')
        _EnvironmentValue.model_validate(self.environment.value)
        if self.lifecycle.stage in ('running', 'ended'):
            if self.execution is None or self.inputs is None or not {'prompt', 'schemas', 'room'} <= set(self.inputs):
                raise ValueError('Missing execution identity')
        if self.execution is not None:
            config = self.execution.value
            if not isinstance(config, dict) or not {'mode', 'settings', 'pricing', 'players', 'conditions'} <= set(config):
                raise ValueError('Missing effective configuration')
        return self


def read_provenance(manifest: dict) -> dict | None:
    """Legacy records return None; unsupported/corrupt records fail safely."""
    if isinstance(manifest, dict) and 'provenance' not in manifest:
        return None
    try:
        value = manifest['provenance']
        if type(value['schema_version']) is not int or value['schema_version'] != 1:
            raise ValueError()
        encoded = json.dumps(value, allow_nan=False)
        ProvenanceRecord.model_validate_json(encoded)
        return json.loads(encoded)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ProvenanceError('Unsupported or invalid provenance record') from None
