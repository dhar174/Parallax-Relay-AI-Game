"""Offline, retrospective all-Luna qualification on a trusted locked host.

Hash-bound local evidence is checked again at use. This is consistency checking,
not provider billing, model-backend attestation, or a Python security sandbox.
"""
from __future__ import annotations

import argparse
import ast
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess

from PIL import Image

from .conditions import CONDITIONS
from .protocol import ROLES
from .provenance import ROOT, canonical_hash, collect_source, collect_environment, GIT_PROCESS_ENV_KEYS

ORIGIN_REVISION = 'e263f3fa9f98110465ae0a8c1f358fb734ca45dd'
SELECTION_PATH = ROOT / 'configs/luna_qualification_selection_v1.json'
PROFILE_ID = 'exploratory-luna-under20-v1'
NATIVE_JSON = ('manifest.json','result.json','final_state.json')
NATIVE_JSONL = ('calls.jsonl','phases.jsonl','replay.jsonl')
BRIDGE_MODULES = frozenset({'parallax_relay/campaign.py','parallax_relay/campaign_models.py',
    'parallax_relay/campaign_analysis.py','parallax_relay/campaign_validation.py',
    'parallax_relay/exploratory.py','parallax_relay/room_execution.py',
    'parallax_relay/qualification.py','scripts/prepare_campaign.py'})


def strict_loads(raw: str):
    def pairs(items):
        value={}
        for key,item in items:
            if key in value:raise ValueError('Duplicate JSON key')
            value[key]=item
        return value
    def nonfinite(_):raise ValueError('Nonfinite JSON value')
    def finite_float(raw):
        value=float(raw)
        if not math.isfinite(value):raise ValueError('Nonfinite JSON value')
        return value
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=nonfinite,parse_float=finite_float)


def load(path: Path):
    return strict_loads(path.read_text(encoding='utf-8'))


def strict_jsonl(path: Path) -> list[dict]:
    values=[strict_loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(type(value) is not dict for value in values):raise ValueError('Invalid JSONL row')
    return values


def file_hash(path: Path) -> str:
    if path.is_symlink() or not path.is_file():raise ValueError('Missing regular evidence file')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same(a,b):
    return type(a) is type(b) and canonical_hash(a)==canonical_hash(b)


def _cell(value):
    if (type(value) is not dict or set(value)!={'room','team','condition','repetition'} or
        type(value['repetition']) is not int or value['repetition']!=0 or
        any(type(value[k]) is not str for k in ('room','team','condition'))):
        raise ValueError('Invalid qualification cell')
    return tuple(value[k] for k in ('room','team','condition','repetition'))


def validate_selection_shape(value: dict) -> None:
    expected={(room,team,arm,0) for room in ('split_span','dev_01','dev_02')
              for team in ('models','scripted','wait','uniform') for arm in CONDITIONS}
    missing={('split_span','models',arm,0) for arm in CONDITIONS}
    if (type(value.get('schema_version')) is not int or value['schema_version']!=1 or
        value.get('profile_id')!=PROFILE_ID or type(value.get('selected')) is not list or
        type(value.get('missing')) is not list):raise ValueError('Invalid qualification selection')
    cells=[_cell(row['cell']) for row in value['selected']]
    absent=[_cell(row) for row in value['missing']]
    identities=[(row['origin'],row['trial_id']) for row in value['selected']]
    if (len(cells)!=55 or len(set(cells))!=55 or set(cells)!=expected-missing or
        len(absent)!=5 or set(absent)!=missing or len(set(identities))!=55):
        raise ValueError('Qualification requires exact 55 reused and five missing cells')


def native_inventory(path: Path, turns: int) -> dict[str,str]:
    if type(turns) is not int or not 0<=turns<=12 or path.is_symlink():
        raise ValueError('Invalid native inventory')
    expected={*NATIVE_JSON,*NATIVE_JSONL,'index.html','final_spectator.png',
        *(f'turn_{turn:02d}_{role}.png' for turn in range(turns)
          for role in ('spectra','pyra','flux','spectator'))}
    if {p.name for p in path.iterdir()}!=expected:raise ValueError('Native file inventory mismatch')
    result={name:file_hash(path/name) for name in sorted(expected)}
    records={name.removesuffix('.json'):load(path/name) for name in NATIVE_JSON}
    records.update({name.removesuffix('.jsonl'):strict_jsonl(path/name) for name in NATIVE_JSONL})
    # Use the exact unchanged recorder template and native payload. Merely
    # hashing a newly produced viewer would certify empty or truncated HTML.
    payload={'manifest':records['manifest'],'result':records['result'],'records':records['replay'],
             'calls':records['calls'],'phases':records['phases'],'final_state':records['final_state']}
    encoded=json.dumps(payload,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=Path(__file__).with_name('replay_template.html').read_text(encoding='utf-8')
    if (path/'index.html').read_bytes()!=template.replace('__REPLAY_DATA__',encoded).encode('utf-8'):
        raise ValueError('Native viewer does not match its complete native payload')
    for name in expected:
        if name.endswith('.png'):
            try:
                with Image.open(path/name) as im:
                    if im.format!='PNG':raise ValueError('Invalid native image')
                    im.verify()
                with Image.open(path/name) as im:im.load()
            except (OSError,SyntaxError,Image.DecompressionBombError):
                raise ValueError('Invalid native PNG') from None
    return result


def eligible_row(row: dict) -> bool:
    counts=('reserved_calls','calls_reserved_total','calls_started','calls_released','fallbacks')
    return bool(row.get('launched') is True and row.get('artifact_available') is True and
        row.get('artifact_issues')==[] and row.get('cleanup_status')=='ok' and
        row.get('stop_reason') in ('victory','defeat','turn_limit') and
        (row['stop_reason']!='turn_limit' or type(row.get('turns')) is int and row['turns']==12) and
        row.get('recording_stop_reason')==row['stop_reason']==row.get('execution_stop_reason') and
        type(row.get('operational_success')) is bool and
        all(type(row.get(k)) is int and row[k]>=0 for k in counts) and
        row['reserved_calls']==0 and row['fallbacks']==0 and
        row['calls_reserved_total']-row['calls_released']==row['calls_started'])


def _contained(base: Path, relative: str) -> Path:
    if type(relative) is not str or Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('Invalid evidence location')
    path=base/relative
    if not path.resolve().is_relative_to(base.resolve()):raise ValueError('Evidence escaped its root')
    return path


def _files(base: Path, expected: dict) -> None:
    if type(expected) is not dict or not expected:raise ValueError('Missing evidence digests')
    for relative,digest in expected.items():
        path=_contained(base,relative)
        if file_hash(path)!=digest:raise ValueError('Evidence digest changed')
        if path.suffix=='.json':load(path)
        if path.suffix=='.jsonl':strict_jsonl(path)


def _phase_integrity(data: dict, trial: dict) -> None:
    required={(turn,phase) for turn in range(data['result']['turns'])
              for phase in CONDITIONS[trial['condition']].phases}
    if {(p['turn'],p['phase']) for p in data['phases']}!=required:
        raise ValueError('Unresolved or excess role phase')
    if any(p['statuses']!={r:'ok' for r in ROLES} for p in data['phases']):
        raise ValueError('Unresolved role phase')
    groups={}
    for call in data['calls']:
        groups.setdefault((call['turn'],call['phase'],call['role']),[]).append(call)
    if set(groups)!={(turn,phase,role) for turn,phase in required for role in ROLES}:
        raise ValueError('Missing or excess role attempts')
    for calls in groups.values():
        if ([c['attempt'] for c in calls]!=list(range(1,len(calls)+1)) or
            calls[-1]['status']!='ok' or any(c['status']=='ok' for c in calls[:-1])):
            raise ValueError('Unresolved or contradictory attempts')
        recoverable={'timeout','network_error','invalid_provider_response','incomplete',
                     'invalid_json_schema','stale_turn','response_size','response_failed','http_error'}
        for call in calls[:-1]:
            if call['status'] not in recoverable:
                raise ValueError('Impossible or unknown retry attempt')
            http=call.get('http_status')
            if call['status']=='http_error' and (type(http) is not int or not (
                    http in (408,409,429) or 500<=http<=599)):
                raise ValueError('Non-retryable HTTP attempt')


def _origin(root: Path, origin: dict) -> tuple[dict,dict]:
    from .campaign import read_registration
    from .campaign_analysis import analyze
    _files(root,origin['files'])
    campaign=_contained(root,origin['campaign'])
    registration=read_registration(campaign)
    if registration['sha256']!=origin['registration_sha256']:raise ValueError('Origin registration changed')
    report=analyze(campaign)
    saved=load(_contained(root,origin['report'])/'report.json')
    if (saved['registration_sha256']!=registration['sha256'] or
        not _same(saved['trials'],report['trials']) or report['anomalies'] or
        report['campaign_accounting']['reservation_balance_calls']!=0 or
        Decimal(report['campaign_accounting']['reservation_balance_estimated_usd_decimal'])!=0 or
        report['campaign_accounting']['launched_without_finished_receipt']!=0 or
        report['campaign_stop'] is None):raise ValueError('Origin accounting or native report mismatch')
    return registration,report


def audit_selection(selection_path: Path, evidence_root: Path, *, frozen: dict|None=None) -> dict:
    """Check immutable selection, original parents and every selected native file."""
    from .campaign_models import CampaignSpec
    from .campaign_analysis import _artifacts
    from .exploratory import luna_profile_spec
    selection=load(selection_path)
    # The committed selection is the authority; a rehashed replacement cannot
    # change trial choices or discard failures.
    if not _same(selection,load(SELECTION_PATH)):raise ValueError('Unapproved qualification selection')
    validate_selection_shape(selection)
    _files(evidence_root,selection['history_files'])
    origins={key:_origin(evidence_root,origin) for key,origin in selection['origins'].items()}
    expected_match=luna_profile_spec('qualification')['match']
    selected=[]
    for item in selection['selected']:
        origin=selection['origins'][item['origin']]
        reg,report=origins[item['origin']]
        spec=CampaignSpec.model_validate(reg['spec'])
        trial=next((t for t in reg['schedule'] if t['trial_id']==item['trial_id']),None)
        row=next((r for r in report['trials'] if r['trial_id']==item['trial_id']),None)
        if (trial is None or row is None or _cell(item['cell'])!=_cell({k:trial[k] for k in item['cell']}) or
            not eligible_row(row) or not _same(spec.match.model_dump(),expected_match) or
            reg['frozen']['source']!=selection['origin_source'] or
            reg['frozen']['source']!={'status':'clean','revision':ORIGIN_REVISION,'reason':None} or
            reg['frozen']['environment']['sha256']!=selection['environment_sha256'] or
            canonical_hash(reg['frozen']['inputs'])!=selection['inputs_sha256']):
            raise ValueError('Ineligible selected native case')
        if trial['team']=='models':
            if (report['completion_status']!='complete' or not report['cohort_eligible'] or
                any(p!=luna_profile_spec('qualification')['roster'][0] for p in trial['players'].values())):
                raise ValueError('Models require a complete all-Luna origin')
        if frozen is not None:
            if (not _same(reg['frozen']['environment'],frozen['environment']) or
                not _same(reg['frozen']['inputs'],frozen['inputs']) or
                not _same(reg['frozen']['catalog'],frozen['catalog']) or
                trial['team']=='models' and not _same(reg['frozen']['provider_contracts'].get('openai'),
                                                       frozen['provider_contracts'].get('openai'))):
                raise ValueError('Changed execution inputs or model API contract')
        campaign=_contained(evidence_root,origin['campaign'])
        data,issues=_artifacts(campaign,trial,reg)
        if issues:raise ValueError('Native artifact validation failed')
        _phase_integrity(data,trial)
        inventory=native_inventory(campaign/'trials'/trial['trial_id'],data['result']['turns'])
        if not _same(inventory,item['artifacts']):raise ValueError('Native artifact digest mismatch')
        selected.append(row)
    # Preserve the full historical cost, including unselected mixed-model failures.
    from .money import amount, total
    paid=sum(r['calls_started'] or 0 for _,rep in origins.values() for r in rep['trials']
             if r['team']=='models' and r['launched'])
    costs={key:total(amount(r,key) for _,rep in origins.values() for r in rep['trials']
                    if r['team']=='models' and r['launched'])
           for key in ('estimated_cost_usd','known_usage_estimated_usd','retained_estimate_usd')}
    prior=selection['prior_accounting']
    if (type(prior['paid_attempts']) is not int or paid!=prior['paid_attempts'] or
        costs['estimated_cost_usd']!=Decimal(prior['estimated_usd_decimal']) or
        costs['known_usage_estimated_usd']!=Decimal(prior['known_usage_estimated_usd_decimal']) or
        costs['retained_estimate_usd']!=Decimal(prior['retained_estimate_usd_decimal']) or
        prior['original_failed_trial_retained'] is not True):raise ValueError('Historical accounting changed')
    return {'selected_cases':len(selected),'models':10,'controls':45,'selection_sha256':canonical_hash(selection),
            'prior_accounting':prior,'trials':selected}


def _git(*args: str) -> bytes:
    env={name:os.environ[name] for name in GIT_PROCESS_ENV_KEYS if name in os.environ}
    env['GIT_OPTIONAL_LOCKS']='0'
    result=subprocess.run(['git','-c','core.fsmonitor=','-C',str(ROOT),*args],env=env,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=15)
    if result.returncode:raise ValueError('Source bridge Git identity unavailable')
    return result.stdout


def _tree(revision: str) -> dict:
    values={}
    for row in _git('ls-tree','-rz','--full-tree',revision).split(b'\0'):
        if not row:continue
        metadata,path=row.split(b'\t',1);mode,kind,oid=metadata.decode().split()
        if mode not in ('100644','100755') or kind!='blob':raise ValueError('Unsupported source tree entry')
        values[path.decode('utf-8')]={'mode':mode,'oid':oid}
    return values


def validate_bridge_changes(changes: dict) -> None:
    """Default-deny the entire Git tree, not just selected function bodies."""
    for name in changes:
        if not (name in BRIDGE_MODULES or name.startswith('tests/test_luna') or
                name=='tests/test_qualification.py' or name.startswith('docs/') or
                name=='configs/luna_qualification_selection_v1.json' or name in
                ('README.md','CHANGELOG.md')):
            raise ValueError('Unreviewable execution/dependency/source bridge drift')


def _binding_nodes(raw: bytes) -> dict:
    nodes={}
    for item in ast.parse(raw).body:
        # Inspect module-level bindings as well as function/class bodies.
        if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            key=item.name
        else:key=ast.dump(item,include_attributes=False)
        if key in nodes:raise ValueError('Ambiguous source binding')
        nodes[key]=ast.dump(item,include_attributes=False)
    return nodes


def build_bridge() -> dict:
    """Freeze a specific clean full-tree bridge; reviewers inspect its full diff."""
    source=collect_source(ROOT)
    if source['status']!='clean':raise ValueError('Source bridge requires clean committed source')
    # Python/package files outside the checked tree cannot be attested by Git.
    # Reject observed import overrides; the documented locked-host trust remains.
    if any(os.environ.get(k) for k in ('PYTHONPATH','PYTHONHOME')):
        raise ValueError('Import overrides prevent a locked source bridge')
    before=_tree(ORIGIN_REVISION);after=_tree(source['revision'])
    changes={key:(before.get(key),after.get(key)) for key in before.keys()|after.keys()
             if before.get(key)!=after.get(key)}
    validate_bridge_changes(changes)
    # Immutable providers, engine, prompts, settings, recorder, provenance and
    # their transitive imports are protected by the full-tree comparison above.
    # Also protect existing match execution and its mutable module bindings.
    protected={
        'parallax_relay/campaign.py':('execute_trial','atomic_json','now','Ledger'),
        'parallax_relay/campaign_models.py':('trial_settings','trial_exposure','assignments','_same_profile_types'),
    }
    for module,names in protected.items():
        old=_binding_nodes(_git('show',ORIGIN_REVISION+':'+module))
        new=_binding_nodes(_git('show',source['revision']+':'+module))
        if any(old.get(name)!=new.get(name) for name in names):
            raise ValueError('Source bridge changed a protected match execution binding')
        # Existing top-level constants/import bindings must survive unchanged;
        # new imports may only select the gate/profile functions reviewed here.
        old_imports={key:value for key,value in old.items() if key.startswith(('Import(','ImportFrom('))}
        new_imports={key:value for key,value in new.items() if key.startswith(('Import(','ImportFrom('))}
        for key in old_imports:
            if key not in new_imports:
                # Extending the existing exploratory import is the sole allowed
                # import replacement; check every pre-existing alias explicitly.
                if "module='exploratory'" not in key:raise ValueError('Changed execution import binding')
                old_node=next(n for n in ast.parse(_git('show',ORIGIN_REVISION+':'+module)).body
                              if isinstance(n,ast.ImportFrom) and n.module=='exploratory')
                new_node=next(n for n in ast.parse(_git('show',source['revision']+':'+module)).body
                              if isinstance(n,ast.ImportFrom) and n.module=='exploratory')
                if not {(n.name,n.asname) for n in old_node.names}<={(n.name,n.asname) for n in new_node.names}:
                    raise ValueError('Changed execution import alias')
        # No changed or added assignment can shadow the protected bindings or
        # imported engine/provider/settings helpers.
        new_ast=ast.parse(_git('show',source['revision']+':'+module))
        permitted_changes=({'read_json','frozen_inputs','register','validate_registration',
                            '_execution_preflight','run_campaign','main'} if module.endswith('/campaign.py')
                           else {'CampaignSpec'})
        for key in old.keys()|new.keys():
            if old.get(key)==new.get(key) or key in permitted_changes or key.startswith(('Import(','ImportFrom(')):
                continue
            raise ValueError('Unreviewed module-level execution binding')
        permitted_imports={'exploratory':{'GEMINI_ROLE_BY_ROOM','is_exploratory','profile_spec',
            'profile_analysis','is_luna','is_descriptive','luna_profile_spec','luna_profile_analysis'},
            'collections.abc':{'Mapping'}}
        for node in new_ast.body:
            if isinstance(node,(ast.Import,ast.ImportFrom)) and ast.dump(node,include_attributes=False) not in old:
                if (not isinstance(node,ast.ImportFrom) or node.module not in permitted_imports or
                    any(n.name not in permitted_imports[node.module] or n.asname is not None for n in node.names)):
                    raise ValueError('Unreviewed execution import')
            elif isinstance(node,(ast.Assign,ast.AnnAssign,ast.AugAssign)) and ast.dump(node,include_attributes=False) not in old:
                raise ValueError('Changed execution global binding')
    bridge={'schema_version':1,'profile_id':PROFILE_ID,'origin_revision':ORIGIN_REVISION,
            'target_source':source,'origin_tree':before,'target_tree':after,
            'changed_paths':sorted(changes),'tree_transition_sha256':canonical_hash(changes),
            'environment':collect_environment(),'trust':'Reviewed exact full-tree bridge on a trusted locked host; no binary/backend attestation.'}
    bridge['sha256']=canonical_hash(bridge)
    return bridge


def check_bridge(path: Path, frozen: dict) -> dict:
    bridge=load(path)
    if not _same(bridge,build_bridge()) or not _same(bridge['target_source'],frozen['source']) or not _same(
            bridge['environment'],frozen['environment']):raise ValueError('Source bridge no longer matches')
    return bridge


def selection_binding(selection_path: Path, evidence_root: Path, bridge_path: Path, frozen: dict) -> dict:
    audit=audit_selection(selection_path,evidence_root,frozen=frozen)
    bridge=check_bridge(bridge_path,frozen)
    # Selection must be committed before the five new outcomes can be observed.
    committed=_git('show',frozen['source']['revision']+':configs/luna_qualification_selection_v1.json')
    if not _same(strict_loads(committed.decode()),load(selection_path)):
        raise ValueError('Qualification selection is not committed in the frozen source')
    return {'kind':'selection','selection_path':str(selection_path.resolve()),
            'evidence_root':str(evidence_root.resolve()),'source_bridge_path':str(bridge_path.resolve()),
            'selection_sha256':audit['selection_sha256'],'source_bridge_sha256':bridge['sha256']}


def check_binding(binding: dict, frozen: dict, *, kind: str) -> dict:
    if type(binding) is not dict or binding.get('kind')!=kind:raise ValueError('Missing qualification binding')
    if kind=='selection':
        expected=selection_binding(Path(binding['selection_path']),Path(binding['evidence_root']),
                                   Path(binding['source_bridge_path']),frozen)
    elif kind=='qualified':
        receipt=check_receipt(Path(binding['receipt_path']),frozen=frozen)
        expected={'kind':'qualified','receipt_path':str(Path(binding['receipt_path']).resolve()),
                  'receipt_sha256':receipt['sha256'],'selection_sha256':receipt['selection_sha256'],
                  'source_bridge_sha256':receipt['source_bridge_sha256']}
    else:raise ValueError('Unknown qualification binding kind')
    if not _same(binding,expected):raise ValueError('Qualification binding changed')
    return expected


def build_receipt(supplement: Path) -> dict:
    from .campaign import read_registration
    from .campaign_analysis import analyze, _artifacts
    from .exploratory import is_luna
    reg=read_registration(supplement)
    if not is_luna(reg['spec']) or reg['spec']['stage']!='qualification':
        raise ValueError('Expected all-Luna qualification supplement')
    binding=check_binding(reg['qualification'],reg['frozen'],kind='selection')
    report=analyze(supplement)
    if (report['completion_status']!='complete' or not report['cohort_eligible'] or report['anomalies'] or
        report['campaign_accounting']['reservation_balance_calls']!=0 or
        Decimal(report['campaign_accounting']['reservation_balance_estimated_usd_decimal'])!=0 or
        any(not eligible_row(row) for row in report['trials'])):
        raise ValueError('Supplement is incomplete, binding, or invalid')
    inventory=[]
    for trial in reg['schedule']:
        data,issues=_artifacts(supplement,trial,reg)
        if issues:raise ValueError('Supplement native artifact validation failed')
        _phase_integrity(data,trial)
        inventory.append({'trial_id':trial['trial_id'],'cell':{k:trial[k] for k in ('room','team','condition','repetition')},
                          'artifacts':native_inventory(supplement/'trials'/trial['trial_id'],data['result']['turns'])})
    from .money import amount,total
    value={'schema_version':1,'profile_id':PROFILE_ID,'qualified':True,'evidence_class':'retrospective_exploratory',
           'confirmatory_eligible':False,'selection_sha256':binding['selection_sha256'],
           'source_bridge_sha256':binding['source_bridge_sha256'],'selection_binding':binding,
           'supplement_root':str(supplement.resolve()),'supplement_registration_sha256':reg['sha256'],
           'supplement_ledger_sha256':file_hash(supplement/'ledger.jsonl'),
           'frozen':reg['frozen'],'counts':{'models':15,'controls':45,'total':60},'new_cases':inventory,
           'prior_accounting':load(Path(binding['selection_path']))['prior_accounting'],
           'new_accounting':{'paid_attempts':sum(r['calls_started'] for r in report['trials']),
               **{key+'_decimal':str(total(amount(r,key) for r in report['trials'])) for key in
                  ('estimated_cost_usd','known_usage_estimated_usd','retained_estimate_usd')}},
           'interpretation':'Composite qualification only. Original mixed pilot stays incomplete; all historical costs and failures retained.'}
    value['sha256']=canonical_hash(value)
    return value


def check_receipt(path: Path, *, frozen: dict|None=None) -> dict:
    value=load(path)
    expected=build_receipt(Path(value['supplement_root']))
    if not _same(value,expected) or frozen is not None and not _same(value['frozen'],frozen):
        raise ValueError('Stale, forged, or incompatible qualification receipt')
    return value


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    audit=commands.add_parser('audit');audit.add_argument('--selection',type=Path,default=SELECTION_PATH)
    audit.add_argument('--evidence-root',type=Path,required=True)
    bridge=commands.add_parser('bridge');bridge.add_argument('--out',type=Path,required=True)
    build=commands.add_parser('build');build.add_argument('--supplement',type=Path,required=True)
    build.add_argument('--out',type=Path,required=True)
    check=commands.add_parser('check');check.add_argument('--receipt',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='audit':
            value=audit_selection(args.selection,args.evidence_root)
            print(json.dumps({k:v for k,v in value.items() if k!='trials'}));return 0
        if args.command=='check':value=check_receipt(args.receipt)
        else:
            value=build_bridge() if args.command=='bridge' else build_receipt(args.supplement)
            from .campaign import atomic_json
            if args.out.exists() or args.out.is_symlink():raise ValueError('Qualification output already exists')
            args.out.parent.mkdir(parents=True,exist_ok=True)
            atomic_json(args.out,value)
            if not _same(load(args.out),value):raise ValueError('Qualification readback failed')
        print(json.dumps({'sha256':value['sha256'],'qualified':value.get('qualified',False)}));return 0
    except (ValueError,OSError,KeyError,TypeError,RecursionError,StopIteration,subprocess.SubprocessError):
        print('Qualification check failed; preserve evidence and inspect sanitized diagnostics.');return 2


if __name__=='__main__':raise SystemExit(main())
