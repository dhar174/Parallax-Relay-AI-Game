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
from .config import MatchSettings, Rates, Settings
from .conditions import resolve_condition
from .policies import policy_identity
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
    policy: Literal['scripted', 'wait', 'uniform'] | None = None

    @model_validator(mode='after')
    def policy_trial(self):
        if self.policy == 'uniform' and self.trial_id is None:
            raise ValueError('Uniform policy requires a trial UUID')
        if self.policy is not None and self.mode != 'mock':
            raise ValueError('Offline policy requires mock identity')
        return self

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
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}
    env['GIT_OPTIONAL_LOCKS'] = '0'
    def git(*args):
        return subprocess.run(['git', '-c', 'core.fsmonitor=', '-C', str(root), *args], env=env,
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
        unavailable = {**unavailable, 'revision': lines[1]}
        status = git('status', '--porcelain=v1', '--untracked-files=normal')
        if status.returncode:
            return {**unavailable, 'revision': lines[1], 'reason': 'status_unavailable'}
        return {'status': 'dirty' if status.stdout else 'clean', 'revision': lines[1], 'reason': None}
    except subprocess.TimeoutExpired:
        return {**unavailable, 'reason': 'git_timeout'}
    except (OSError, ValueError):
        return {**unavailable, 'reason': 'status_unavailable'} if unavailable['revision'] else unavailable


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


def input_identities(initial_snapshot: dict, settings: MatchSettings | None = None) -> dict:
    condition = resolve_condition(settings or MatchSettings())
    request = protocol.AgentRequest(protocol.Observation('SPECTRA', 0, '{}', b''), 'commit',
                                    include_image=condition.include_image, condition=condition.name)
    return {
        'prompt': _fingerprint(prompts.SYSTEM_RULES + '\n' + json.dumps(condition.notice(), sort_keys=True)),
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
        self._policy, self._trial_id = context.policy, context.trial_id
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
            'schema_version': 2, 'run_id': str(uuid4()),
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
        settings = MatchSettings.model_validate(settings.model_dump())
        config = {'mode': self._mode, 'settings': settings.model_dump(),
                  'pricing': {r: rates[r].model_dump() if rates.get(r) is not None else None
                              for r in protocol.ROLES},
                  'players': self._data['players'],
                  'conditions': {'arm': resolve_condition(settings).name,
                                 **resolve_condition(settings).notice()},
                  'policy': policy_identity(self._policy, self._trial_id, settings.max_turns) if self._policy else None}
        # Publish a complete binding only after every fallible input collector
        # succeeds. Failed setup must not look like an external/partial match.
        execution = _fingerprint(config)
        inputs = input_identities(initial_snapshot, settings)
        tick, started_at = monotonic(), _utc_now()
        self._data['execution'], self._data['inputs'] = execution, inputs
        self._tick = tick
        self._data['lifecycle'].update(stage='running', started_at=started_at)
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
        life = self._data['lifecycle']
        if life['stage'] != 'initialized':
            life['stop_reason'] = result.stop_reason

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
        if self.stage == 'initialized' and (self.execution_stop_reason is not None or self.stop_reason is not None):
            raise ValueError('Unexpected stop metadata')
        if self.stage == 'external_result' and (self.execution_stop_reason is None or self.stop_reason is None):
            raise ValueError('Missing external outcome')
        if self.stage == 'running' and (self.execution_stop_reason is not None or
                self.stop_reason not in (None, 'local_error', 'internal_error', 'cancelled')):
            # A failed end hook leaves timing unknown; recovery still records
            # the interruption. It cannot certify a successful execution end.
            raise ValueError('Unexpected running outcome')
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


class _PythonIdentity(_RecordModel):
    implementation: str
    version: str


class _OSIdentity(_RecordModel):
    system: str
    release: str
    machine: str


class _EnvironmentValue(_RecordModel):
    status: Literal['complete', 'partial', 'unavailable']
    python: _PythonIdentity
    os: _OSIdentity
    packages: list[_Distribution]


class _APIContract(_RecordModel):
    endpoint: str
    family: str
    namespace: str
    version_header: str | None = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class _PlayerRecord(_RecordModel):
    provider: Literal['openai', 'anthropic', 'gemini', 'mock', 'unknown']
    model: str | None = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
    identity_source: Literal['declared', 'unavailable']
    model_revision: None
    api_contract: _APIContract | None
    sampling: Literal['provider_default', 'not_applicable', 'unavailable']
    seed: None

    @model_validator(mode='after')
    def consistent_identity(self):
        known = self.provider != 'unknown'
        contract = provider_contract(self.provider)
        sampling = ('provider_default' if contract else
                    'not_applicable' if self.provider == 'mock' else 'unavailable')
        if self.identity_source != ('declared' if known else 'unavailable') or self.sampling != sampling:
            raise ValueError('Inconsistent player identity')
        if contract is None:
            if self.api_contract is not None:
                raise ValueError('Unexpected API contract')
        else:
            if self.api_contract is None or any(
                    getattr(self.api_contract, key) != contract[key]
                    for key in ('endpoint', 'family', 'namespace')):
                raise ValueError('Inconsistent API contract')
            # Historical records retain their recorded Anthropic version, not
            # the current checkout's version header.
            if (self.api_contract.version_header is not None) != (self.provider == 'anthropic'):
                raise ValueError('Inconsistent API version')
        return self


def _complete_config(model, value):
    # Snapshot fields must be present; defaults would conceal missing identity.
    # Ignore additive extensions without removing them from the returned record.
    if not isinstance(value, dict) or not set(model.model_fields) <= set(value):
        raise ValueError('Incomplete configuration snapshot')
    return model.model_validate({k: value[k] for k in model.model_fields}, strict=True)


def _require_roles(value):
    if set(value) != set(protocol.ROLES):
        raise ValueError('Missing role identities')
    return value


class _LegacyMatchSettings(Settings):
    """Frozen provenance-v1 contract; do not extend with current defaults."""
    communication_rounds: Literal[1, 2] = 2
    max_turns: int = Field(default=12, ge=1, le=12)
    max_calls: int = Field(default=216, ge=1, le=10000)
    max_attempts: int = Field(default=2, ge=1, le=3)
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_output_tokens: int = Field(default=2048, ge=256, le=16384)
    history_turns: int = Field(default=4, ge=0, le=12)
    retry_delay_seconds: float = Field(default=0.5, ge=0, le=30)
    max_consecutive_failures: int = Field(default=3, ge=1, le=20)
    max_estimated_cost_usd: float | None = Field(default=None, gt=0)
    image_token_reserve: int = Field(default=8192, ge=1, le=1000000)


class _Conditions(_RecordModel):
    communication: Literal['full', 'reduced']
    observations: Literal['role_png_and_hud']


class _ExecutionValue(_RecordModel):
    mode: Literal['mock', 'live', 'programmatic']
    settings: dict
    pricing: dict[str, dict | None]
    players: dict[str, _PlayerRecord]
    conditions: _Conditions

    @model_validator(mode='after')
    def valid_configuration(self):
        settings = _complete_config(_LegacyMatchSettings, self.settings)
        _require_roles(self.players)
        for rate in _require_roles(self.pricing).values():
            if rate is not None:
                _complete_config(Rates, rate)
            elif settings.max_estimated_cost_usd is not None:
                raise ValueError('Missing guarded pricing')
        if self.conditions.communication != ('full' if settings.communication_rounds == 2 else 'reduced'):
            raise ValueError('Inconsistent communication condition')
        return self


class _ConditionsV2(_RecordModel):
    arm: Literal['full', 'reduced', 'disabled', 'withheld', 'no_images']
    version: Literal[1]
    phases: list[Literal['broadcast', 'negotiate', 'commit']]
    public_messages_available: bool
    role_image_available: bool


class _ExecutionValueV2(_RecordModel):
    mode: Literal['mock', 'live', 'programmatic']
    settings: dict
    pricing: dict[str, dict | None]
    players: dict[str, _PlayerRecord]
    conditions: _ConditionsV2
    policy: dict | None

    @model_validator(mode='after')
    def valid_configuration(self):
        settings = _complete_config(MatchSettings, self.settings)
        _require_roles(self.players)
        for rate in _require_roles(self.pricing).values():
            if rate is not None:
                _complete_config(Rates, rate)
            elif settings.max_estimated_cost_usd is not None:
                raise ValueError('Missing guarded pricing')
        condition = resolve_condition(settings)
        if self.conditions.model_dump() != {'arm': condition.name, **condition.notice()}:
            raise ValueError('Inconsistent condition')
        if self.policy is not None:
            name = self.policy.get('name')
            if name not in ('scripted', 'wait', 'uniform') or self.mode != 'mock':
                raise ValueError('Invalid policy identity')
            expected = policy_identity(name, self.policy.get('trial_id'), settings.max_turns)
            if name == 'uniform':
                recorded_python = self.policy.get('python_version')
                if not isinstance(recorded_python, str) or not re.fullmatch(r'\d+\.\d+\.\d+[A-Za-z0-9.+_-]{0,80}', recorded_python):
                    raise ValueError('Invalid policy Python version')
                expected['python_version'] = recorded_python
                seeds = self.policy.get('commitment_seeds')
                if (not isinstance(seeds, dict) or set(seeds) != set(protocol.ROLES) or
                    any(not isinstance(values, list) or len(values) != settings.max_turns or
                        any(type(seed) is not int or not 0 <= seed < 2**64 for seed in values) for values in seeds.values())):
                    raise ValueError('Invalid commitment seeds')
            if type(self.policy.get('version')) is not int or self.policy != expected:
                raise ValueError('Inconsistent policy identity')
        return self


class _RequestStructure(_RecordModel):
    role: str
    turn: int
    phase: str
    observation: dict
    public_messages: list
    your_recent_history: list
    your_private_notes: str
    format_repair: str


class _SchemaValue(_RecordModel):
    request_format_version: int = Field(ge=1)
    request_structure: _RequestStructure
    wire: dict[str, dict]
    local: dict[str, dict]
    max_reply_chars: int = Field(ge=1)

    @model_validator(mode='after')
    def required_contracts(self):
        if not {'broadcast', 'negotiate', 'commit'} <= set(self.wire) or not {'broadcast', 'commit'} <= set(self.local):
            raise ValueError('Missing reply contracts')
        return self


class _RoomValue(_RecordModel):
    id: str
    version: int = Field(ge=1)
    constants: dict[str, int]
    gap: list[int]
    objectives: dict[str, str]
    initial_state: dict

    @model_validator(mode='after')
    def required_definition(self):
        if not {'WIDTH', 'MAX_TURNS', 'EXIT', 'ARTIFACT', 'ENERGY_CELL', 'MOTOR'} <= set(self.constants):
            raise ValueError('Missing room constants')
        _require_roles(self.objectives)
        # Validate the recorded snapshot, without requiring it to equal this
        # checkout's room values or constructing/mutating an engine world.
        world = _WorldSnapshot.model_validate(self.initial_state)
        width = self.constants['WIDTH']
        if width <= 0 or any(robot.x >= width for robot in world.robots.values()):
            raise ValueError('Invalid recorded coordinates')
        return self


class _RobotSnapshot(_RecordModel):
    role: str
    x: int = Field(ge=0)
    damage: int = Field(ge=0)


class _WorldSnapshot(_RecordModel):
    turn: int = Field(ge=0)
    robots: dict[str, _RobotSnapshot]
    energy: int = Field(ge=0)
    coolant: int = Field(ge=0)
    motor_heat: int = Field(ge=0)
    bridge_extended: bool
    exit_unlocked: bool
    shard_collected: bool
    cell_collected: bool
    win: bool
    loss: bool
    events: list[str]

    @field_validator('robots')
    @classmethod
    def robot_roles(cls, value):
        _require_roles(value)
        if any(role != robot.role for role, robot in value.items()):
            raise ValueError('Inconsistent robot role')
        return value

    @model_validator(mode='after')
    def exclusive_outcome(self):
        if self.win and self.loss:
            raise ValueError('Contradictory world outcome')
        return self


class ProvenanceRecord(_RecordModel):
    schema_version: Literal[1, 2]
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
        _require_roles(self.players)
        _EnvironmentValue.model_validate(self.environment.value)
        if self.requested_settings is not None:
            _complete_config(_LegacyMatchSettings if self.schema_version == 1 else MatchSettings, self.requested_settings)
        if self.lifecycle.stage in ('running', 'ended'):
            if self.execution is None or self.inputs is None or not {'prompt', 'schemas', 'room'} <= set(self.inputs):
                raise ValueError('Missing execution identity')
        elif self.execution is not None or self.inputs is not None:
            raise ValueError('Unexpected execution identity')
        if self.execution is not None:
            execution = (_ExecutionValue if self.schema_version == 1 else _ExecutionValueV2).model_validate(self.execution.value)
            if self.players != execution.players:
                raise ValueError('Contradictory player identities')
            if self.schema_version == 2 and execution.policy is not None and execution.policy['name'] == 'uniform':
                if execution.policy['trial_id'] != str(self.trial_id):
                    raise ValueError('Contradictory trial identity')
        if self.inputs is not None:
            if not {'prompt', 'schemas', 'room'} <= set(self.inputs):
                raise ValueError('Missing input identity')
            if not isinstance(self.inputs['prompt'].value, str):
                raise ValueError('Invalid prompt identity')
            _SchemaValue.model_validate(self.inputs['schemas'].value)
            _RoomValue.model_validate(self.inputs['room'].value)
            if self.schema_version == 2 and self.execution is not None:
                notice = execution.conditions.model_dump(exclude={'arm'})
                schemas = self.inputs['schemas'].value
                if (schemas['request_format_version'] != 2 or
                        schemas['request_structure'].get('condition_notice') != notice or
                        not self.inputs['prompt'].value.endswith('\n' + json.dumps(notice, sort_keys=True))):
                    raise ValueError('Contradictory condition notice or request version')
        return self


def read_provenance(manifest: dict) -> dict | None:
    """Legacy records return None; unsupported/corrupt records fail safely."""
    if isinstance(manifest, dict) and 'provenance' not in manifest:
        return None
    try:
        value = manifest['provenance']
        if type(value['schema_version']) is not int or value['schema_version'] not in (1, 2):
            raise ValueError()
        encoded = json.dumps(value, allow_nan=False)
        ProvenanceRecord.model_validate_json(encoded)
        return json.loads(encoded)
    except (ValueError, TypeError, KeyError, RecursionError):
        raise ProvenanceError('Unsupported or invalid provenance record') from None
