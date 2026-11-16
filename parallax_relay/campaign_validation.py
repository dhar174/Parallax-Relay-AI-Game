"""Structural validation and explicit projections for campaign artifacts."""
from datetime import datetime
from decimal import Decimal
import json
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .conditions import CONDITIONS
from .money import amount, total, difference
from .budget import _price
from .config import Rates
from .protocol import Usage
from .protocol import ROLES
from .providers import provider_contract
from .provenance import _SourceInfo, _Fingerprint, _EnvironmentValue, _SchemaValue, _RoomValue, _APIContract

TRIAL_STOPS = frozenset({'victory','defeat','turn_limit','call_budget','spend_budget','provider_error',
                         'unreliable_agent','internal_error','local_error','cancelled','setup_failure'})
BUDGET_COUNTS = ('calls_started','max_calls','reported_input_tokens','reported_output_tokens','unknown_usage_calls',
                 'input_usage_calls','output_usage_calls','reported_cached_input_tokens','reported_reasoning_output_tokens',
                 'calls_reserved_total','calls_released','reserved_calls')
BUDGET_MONEY = ('estimated_cost_usd','known_usage_estimated_usd','retained_estimate_usd')


class BudgetRecord(BaseModel):
    model_config=ConfigDict(extra='ignore',strict=True,allow_inf_nan=False)
    calls_started: int=Field(ge=0)
    max_calls: int=Field(ge=1)
    reported_input_tokens: int=Field(ge=0)
    reported_output_tokens: int=Field(ge=0)
    unknown_usage_calls: int=Field(ge=0)
    input_usage_calls: int|None=Field(default=None,ge=0)
    output_usage_calls: int|None=Field(default=None,ge=0)
    reported_cached_input_tokens: int|None=Field(default=None,ge=0)
    reported_reasoning_output_tokens: int|None=Field(default=None,ge=0)
    calls_reserved_total: int|None=Field(default=None,ge=0)
    calls_released: int|None=Field(default=None,ge=0)
    reserved_calls: int|None=Field(default=None,ge=0)
    estimated_cost_usd: float|None
    known_usage_estimated_usd: float|None=None
    retained_estimate_usd: float|None=None

    @model_validator(mode='after')
    def consistent_counts(self):
        if self.calls_started>self.max_calls or self.unknown_usage_calls>self.calls_started:
            raise ValueError('Invalid attempt counts')
        if any(n is not None and n>self.calls_started for n in (self.input_usage_calls,self.output_usage_calls)):
            raise ValueError('Invalid usage coverage')
        if all(n is not None for n in (self.calls_reserved_total,self.calls_released,self.reserved_calls)):
            if self.calls_reserved_total-self.calls_released!=self.calls_started+self.reserved_calls:
                raise ValueError('Invalid reservation counts')
        return self


class TrialSummary(BaseModel):
    model_config=ConfigDict(extra='ignore',strict=True,allow_inf_nan=False)
    schema_version: int
    win: bool
    loss: bool
    completed: bool
    turns: int=Field(ge=0,le=12)
    energy: int=Field(ge=0)
    stop_reason: str
    scores: dict[str,int]|None
    budget: BudgetRecord

    @model_validator(mode='after')
    def consistent_outcome(self):
        if self.schema_version!=2 or self.stop_reason not in TRIAL_STOPS:
            raise ValueError('Invalid outcome version/status')
        if self.win and self.loss or self.completed!=(self.win or self.loss):
            raise ValueError('Contradictory terminal outcome')
        if (self.stop_reason=='victory' and not self.win or self.stop_reason=='defeat' and not self.loss or
            self.win and self.stop_reason not in {'victory','local_error','internal_error','cancelled'} or
            self.loss and self.stop_reason not in {'defeat','local_error','internal_error','cancelled'}):
            raise ValueError('Contradictory engine/execution outcome')
        if self.completed:
            if self.scores is None or set(self.scores)!=set(ROLES) or any(n<0 for n in self.scores.values()):
                raise ValueError('Invalid terminal scores')
        elif self.scores is not None:
            raise ValueError('Nonterminal scores must be unknown')
        return self


def validate_summary(value) -> TrialSummary:
    summary=TrialSummary.model_validate(value)
    for key in BUDGET_COUNTS:
        if key in value['budget'] and type(value['budget'][key]) is not int:
            raise ValueError('Invalid budget count')
    amounts={key:amount(value['budget'],key) for key in BUDGET_MONEY}
    if all(v is not None for v in amounts.values()):
        # Legacy floats carry only their recorded precision; exact annotations
        # are compared exactly, while numeric-only summaries tolerate their ULPs.
        delta=difference(amounts['estimated_cost_usd'],total((amounts['known_usage_estimated_usd'],amounts['retained_estimate_usd'])))
        if all(key+'_decimal' in value['budget'] for key in BUDGET_MONEY):
            if delta:raise ValueError('Inconsistent exact cost components')
        elif abs(delta)>max(abs(amounts['estimated_cost_usd'])*Decimal('1e-14'),Decimal('1e-18')):
            raise ValueError('Inconsistent cost components')
    return summary


def utc(value):
    if not isinstance(value,str) or not value.endswith('Z'):
        raise ValueError('Invalid UTC timestamp')
    datetime.fromisoformat(value.replace('Z','+00:00'))


def validate_frozen(value,spec):
    required={'source','environment','inputs','provider_contracts','sampling','known_model_revisions','analysis'}
    if not isinstance(value,dict) or not required<=set(value):raise ValueError('Incomplete frozen identity')
    source=_SourceInfo.model_validate(value['source'])
    env=_Fingerprint.model_validate(value['environment']);_EnvironmentValue.model_validate(env.value)
    if spec.stage!='diagnostic' and (source.status!='clean' or env.value['status']!='complete'):
        raise ValueError('Ineligible frozen identity')
    if not isinstance(value['inputs'],dict) or set(value['inputs'])!=set(spec.conditions):raise ValueError('Invalid frozen arms')
    for arm,inputs in value['inputs'].items():
        if not isinstance(inputs,dict) or not {'prompt','schemas','room'}<=set(inputs):raise ValueError('Missing input identity')
        fingerprints={k:_Fingerprint.model_validate(inputs[k]) for k in ('prompt','schemas','room')}
        _SchemaValue.model_validate(fingerprints['schemas'].value);_RoomValue.model_validate(fingerprints['room'].value)
        notice=CONDITIONS[arm].notice();schema=fingerprints['schemas'].value
        if (schema['request_format_version']!=2 or schema['request_structure'].get('condition_notice')!=notice or
            not isinstance(fingerprints['prompt'].value,str) or not fingerprints['prompt'].value.endswith('\n'+json.dumps(notice,sort_keys=True))):
            raise ValueError('Contradictory frozen condition')
    contracts=value['provider_contracts']
    if not isinstance(contracts,dict) or set(contracts)!={p.provider for p in spec.roster}:raise ValueError('Invalid API identities')
    for provider,contract in contracts.items():
        _APIContract.model_validate(contract);expected=provider_contract(provider)
        if any(contract[k]!=expected[k] for k in ('endpoint','family','namespace')):raise ValueError('Invalid API identity')
        header=contract.get('version_header')
        if provider=='anthropic':
            if not isinstance(header,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',header):raise ValueError('Invalid API version')
        elif header is not None:raise ValueError('Invalid API version')
    analysis=value['analysis']
    expected={'version':1,'bootstrap_resamples':10000,'seed':0,'percentile':'Hyndman-Fan-7',
              'prng':'random.Random','concurrency':1,'primary_contrast':['full','disabled']}
    if (value['sampling']!='provider_default' or value['known_model_revisions'] is not None or
        not isinstance(analysis,dict) or any(analysis.get(k)!=v for k,v in expected.items()) or
        any(type(analysis.get(k)) is not int for k in ('version','bootstrap_resamples','seed','concurrency'))):
        raise ValueError('Invalid frozen analysis')


def equal_money(record,key,expected):
    actual=amount(record,key)
    if actual is None or expected is None:return actual is expected
    if key+'_decimal' in record:return actual==expected
    return float(actual)==float(expected)


def cross_artifacts(data,trial,settings):
    issues=[];result=data.get('result');calls=data.get('calls');phases=data.get('phases');replay=data.get('replay')
    if not result:return issues
    if result['turns']>settings.max_turns:issues.append('result_turn_limit_mismatch')
    world=data.get('final_state');p=data.get('provenance')
    if world and world['energy']!=result['energy']:issues.append('world_energy_mismatch')
    if p and p['lifecycle']['stop_reason']!=result['stop_reason']:issues.append('lifecycle_stop_mismatch')
    if replay is not None:
        if any(type(t.get('turn')) is not int or t['turn']!=i+1 for i,t in enumerate(replay)):
            issues.append('replay_turn_sequence_mismatch')
        if replay and world and replay[-1].get('state_after')!=world:issues.append('last_checkpoint_mismatch')
    if phases is not None:
        keys=[]
        for phase in phases:
            turn=phase.get('turn')
            if type(turn) is not int or not 0<=turn<settings.max_turns:issues.append('phase_turn_range_mismatch')
            else:keys.append((turn,phase['phase']))
        if len(keys)!=len(set(keys)):issues.append('duplicate_phase')
        if replay is not None:
            from .conditions import resolve_condition
            needed={(t,phase) for t in range(result['turns']) for phase in resolve_condition(settings).phases}
            if not needed<=set(keys):issues.append('resolved_phase_missing')
    if calls is None:return issues
    counts={'reported_input_tokens':0,'reported_output_tokens':0,'unknown_usage_calls':0,
            'input_usage_calls':0,'output_usage_calls':0,'reported_cached_input_tokens':0,'reported_reasoning_output_tokens':0}
    settlements={'complete_usage':[],'retained_estimate':[]};call_keys=[]
    for call in calls:
        call_keys.append((call['role'],call['turn'],call['phase'],call['attempt']))
        usage=call.get('usage')
        if usage is not None and not isinstance(usage,dict):issues.append('usage_shape_mismatch');continue
        usage=usage or {}
        for key in ('input_tokens','output_tokens','cached_input_tokens','reasoning_output_tokens'):
            value=usage.get(key)
            if value is not None and (type(value) is not int or value<0):issues.append('usage_shape_mismatch')
        if 'usage_shape_mismatch' in issues:continue
        inp,out=usage.get('input_tokens'),usage.get('output_tokens')
        known=inp is not None and out is not None
        counts['reported_input_tokens']+=inp or 0;counts['reported_output_tokens']+=out or 0
        counts['unknown_usage_calls']+=int(not known)
        counts['input_usage_calls']+=int(inp is not None);counts['output_usage_calls']+=int(out is not None)
        counts['reported_cached_input_tokens']+=usage.get('cached_input_tokens') or 0
        counts['reported_reasoning_output_tokens']+=usage.get('reasoning_output_tokens') or 0
        basis='complete_usage' if known else 'retained_estimate'
        if call['settlement_basis']!=basis:issues.append('settlement_basis_mismatch')
        settled=amount(call,'settled_amount_usd');quote=amount(call,'reservation_quote_usd')
        expected=(None if trial['team']!='models' else
                  _price(Usage(inp,out),Rates.model_validate(trial['players'][call['role']]['pricing'])) if known else quote)
        if not equal_money(call,'settled_amount_usd',expected):issues.append('attempt_settlement_mismatch')
        if settled is not None:settlements[basis].append(settled)
    if len(call_keys)!=len(set(call_keys)):issues.append('duplicate_attempt')
    if not 'usage_shape_mismatch' in issues:
        if any(key in result['budget'] and result['budget'][key]!=value for key,value in counts.items()):issues.append('usage_totals_mismatch')
    full=amount(result['budget'],'estimated_cost_usd')
    if full is None and any(amount(c,'settled_amount_usd') is not None for c in calls):issues.append('unpriced_settlement_mismatch')
    if full is not None:
        for key,basis in (('known_usage_estimated_usd','complete_usage'),('retained_estimate_usd','retained_estimate')):
            if not equal_money(result['budget'],key,total(settlements[basis])):issues.append('cost_component_mismatch')
    return sorted(set(issues))
