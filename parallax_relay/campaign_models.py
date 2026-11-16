"""Frozen protocol-v1 campaign specifications and preallocated schedules."""
from itertools import permutations
import random
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from .conditions import CONDITIONS, ConditionName
from .config import MatchSettings, Rates, Settings
from .protocol import ROLES
from .provenance import canonical_hash


class CampaignModel(Settings):
    provider: Literal['openai', 'anthropic', 'gemini']
    model: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')
    api_key_env: str = Field(pattern=r'^[A-Z_][A-Z0-9_]{0,127}$')
    pricing: Rates


class CampaignSpec(Settings):
    schema_version: Literal[1] = 1
    protocol_version: Literal[1] = 1
    stage: Literal['diagnostic', 'pilot', 'confirmatory'] = 'diagnostic'
    mode: Literal['offline', 'live'] = 'offline'
    policies: list[Literal['scripted', 'wait', 'uniform']] = Field(default_factory=lambda: ['scripted', 'wait', 'uniform'])
    roster: list[CampaignModel] = Field(default_factory=list)
    rooms: list[Literal['split_span']] = Field(default_factory=lambda: ['split_span'])
    conditions: list[ConditionName] = Field(default_factory=lambda: list(CONDITIONS))
    repetitions: int | None = Field(default=None, ge=1, le=1000, strict=True)
    match: MatchSettings = MatchSettings()
    campaign_max_calls: int = Field(ge=1, le=10**12, strict=True)
    campaign_max_estimated_cost_usd: float | None = Field(default=None, gt=0, strict=True)
    scheduler_seed: int = Field(default=0, ge=0, le=2**63-1, strict=True)
    min_trial_interval_seconds: float = Field(default=0, ge=0, le=3600, strict=True)
    rerun_of: UUID | None = None
    rerun_reason: Literal['infrastructure_recheck', 'manual_recheck'] | None = None

    @model_validator(mode='after')
    def coherent_design(self):
        for values in (self.policies, self.rooms, self.conditions):
            if len(set(values)) != len(values):
                raise ValueError('Duplicate campaign cells')
        if not self.rooms or not self.conditions:
            raise ValueError('Empty room or condition selection')
        if self.match.condition is not None:
            raise ValueError('Campaign conditions are selected by the schedule, not match.condition')
        if self.match.communication_rounds != 2:
            raise ValueError('Campaign phase schedules override rounds; leave communication_rounds at its default')
        if self.stage == 'diagnostic' and self.mode == 'offline' and 'uniform' not in self.policies and self.repeats > 1:
            raise ValueError('Deterministic controls run once; repetitions require a stochastic team')
        if self.mode == 'live':
            if len(self.roster) != 3:
                raise ValueError('Live roster must contain three entries')
            if self.match.max_estimated_cost_usd is None or self.campaign_max_estimated_cost_usd is None:
                raise ValueError('Live campaigns require per-match and campaign estimate guards')
        elif self.roster or not self.policies:
            raise ValueError('Offline campaigns need policies and no live roster')
        if self.mode == 'offline' and self.campaign_max_estimated_cost_usd is not None:
            raise ValueError('Unpriced offline policy costs remain null; omit the dollar guard')
        if self.stage != 'diagnostic':
            if set(self.policies) != {'scripted', 'wait', 'uniform'}:
                raise ValueError('Protocol cohorts require the prescribed baseline policies')
            if set(self.conditions) != set(CONDITIONS):
                raise ValueError('Protocol campaigns require all five arms')
            expected = 5 if self.stage == 'pilot' else 30
            if self.repetitions not in (None, expected):
                raise ValueError('Protocol repetition count is fixed')
        if bool(self.rerun_of) != bool(self.rerun_reason):
            raise ValueError('Reruns require both original trial UUID and reason')
        if self.rerun_of and (self.stage != 'diagnostic' or len(self.conditions) != 1 or
                              self.mode != 'offline' or len(self.policies) != 1 or self.repetitions not in (None, 1)):
            raise ValueError('Operational reruns must be single diagnostic offline trials')
        identities = {}
        for entry in self.roster:
            key = (entry.provider, entry.model)
            value = entry.model_dump()
            if key in identities and identities[key] != value:
                raise ValueError('Repeated model identities must use the same account-variable/pricing configuration')
            identities[key] = value
        return self

    @property
    def repeats(self) -> int:
        return self.repetitions or {'diagnostic': 1, 'pilot': 5, 'confirmatory': 30}[self.stage]


def assignments(spec: CampaignSpec) -> list[dict]:
    """Unique ordered assignments; repeated aliases do not multiply the design."""
    found = {}
    for permutation in permutations(spec.roster):
        value = {role: model.model_dump() for role, model in zip(ROLES, permutation)}
        key = canonical_hash({r: [p['provider'], p['model']] for r, p in value.items()})
        found[key] = {'assignment_id': key, 'players': value}
    return [found[key] for key in sorted(found)]


def schedule(spec: CampaignSpec) -> list[dict]:
    rng = random.Random(spec.scheduler_seed)
    groups = []
    if spec.mode == 'live':
        groups.extend({'team': 'models', **a} for a in assignments(spec))
    groups.extend({'team': p, 'assignment_id': p + '-v1', 'players': {}} for p in spec.policies)
    result = []
    for room in spec.rooms:
        for repetition in range(spec.repeats):
            block_groups = [g for g in groups if g['team'] in ('models', 'uniform') or repetition == 0]
            rng.shuffle(block_groups)
            for group in block_groups:
                block_id = str(uuid4())
                arms = list(spec.conditions)
                rng.shuffle(arms)
                for condition in arms:
                    result.append({'trial_id': str(uuid4()), 'block_id': block_id, 'room': room,
                                   'condition': condition, 'repetition': repetition, **group,
                                   'rerun_of': str(spec.rerun_of) if spec.rerun_of else None,
                                   'rerun_reason': spec.rerun_reason})
    if not result or len(result) > 100000:
        raise ValueError('Campaign schedule must contain 1–100000 trials')
    return result


def trial_settings(spec: CampaignSpec, trial: dict) -> MatchSettings:
    values = spec.match.model_dump()
    values.update(condition=trial['condition'], communication_rounds=CONDITIONS[trial['condition']].communication_rounds)
    if trial['team'] != 'models':
        values['max_estimated_cost_usd'] = None  # Only known built-in zero-usage policies.
    return MatchSettings.model_validate(values)


def trial_exposure(spec: CampaignSpec, trial: dict) -> tuple[int, float]:
    settings = trial_settings(spec, trial)
    calls = min(settings.max_calls, 3 * len(CONDITIONS[trial['condition']].phases) * settings.max_turns * settings.max_attempts)
    # The entire configured per-match estimate cap is reserved. It is not an
    # assertion about provider invoices or exact future request byte sizes.
    dollars = settings.max_estimated_cost_usd if trial['team'] == 'models' else 0
    return calls, dollars or 0
