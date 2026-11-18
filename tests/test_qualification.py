"""Qualification integrity tests are offline; fixture outcomes imply no model ability."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from parallax_relay.provenance import canonical_hash


class QualificationIntegrityTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_discriminators_nonfinite_and_jsonl_arrays(self):
        from parallax_relay.qualification import strict_loads, strict_jsonl
        for raw in ('{"x":1,"x":2}', '{"protocol_version":4,"protocol_version":2}', '{"x":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):strict_loads(raw)
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'calls.jsonl';p.write_text('{}\n[]\n')
            with self.assertRaises(ValueError):strict_jsonl(p)

    def test_selection_requires_exact_cells_and_strict_repetitions_including_defeats(self):
        from parallax_relay.qualification import validate_selection_shape
        selection=json.loads(Path('configs/luna_qualification_selection_v1.json').read_text())
        validate_selection_shape(selection)
        for mutate in (lambda s:s['selected'].pop(),
                       lambda s:s['selected'].append(copy.deepcopy(s['selected'][0])),
                       lambda s:s['selected'][0]['cell'].update(repetition=False),
                       lambda s:s['missing'][0].update(condition='reduced')):
            broken=copy.deepcopy(selection);mutate(broken)
            with self.assertRaises(ValueError):validate_selection_shape(broken)
        self.assertEqual(sum(t['cell']['team']=='models' for t in selection['selected']),10)
        self.assertEqual(sum(t['cell']['team']!='models' for t in selection['selected']),45)

    def test_native_inventory_rejects_extra_missing_and_corrupt_pngs(self):
        from parallax_relay.qualification import native_inventory
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)
            for name in ('manifest.json','result.json','final_state.json'):p.joinpath(name).write_text('{}')
            for name in ('calls.jsonl','phases.jsonl','replay.jsonl'):p.joinpath(name).write_text('')
            p.joinpath('index.html').write_text('<!doctype html>')
            for name in ('spectra','pyra','flux','spectator'):
                Image.new('RGB',(2,2)).save(p/f'turn_00_{name}.png')
            Image.new('RGB',(2,2)).save(p/'final_spectator.png')
            inventory=native_inventory(p,1)
            self.assertEqual(len(inventory),12)
            (p/'turn_00_flux.png').write_bytes(b'not png')
            with self.assertRaises(ValueError):native_inventory(p,1)
            Image.new('RGB',(2,2)).save(p/'turn_00_flux.png')
            (p/'extra.png').write_bytes(b'not png')
            with self.assertRaises(ValueError):native_inventory(p,1)
            (p/'extra.png').unlink();(p/'turn_00_flux.png').unlink()
            with self.assertRaises(ValueError):native_inventory(p,1)

    def test_gate_accepts_legitimate_defeat_and_blocks_budget_or_inconsistent_stops(self):
        from parallax_relay.qualification import eligible_row
        row={'launched':True,'artifact_available':True,'artifact_issues':[],
             'cleanup_status':'ok','stop_reason':'defeat','execution_stop_reason':'defeat',
             'recording_stop_reason':'defeat','operational_success':False,
             'reserved_calls':0,'calls_reserved_total':6,'calls_started':3,'calls_released':3,
             'fallbacks':0}
        self.assertTrue(eligible_row(row))
        for key,value in [('stop_reason','spend_budget'),('recording_stop_reason','victory'),
                          ('execution_stop_reason',None),('cleanup_status','failed'),
                          ('reserved_calls',1),('calls_started',True),('fallbacks',1)]:
            broken={**row,key:value}
            with self.subTest(key=key):self.assertFalse(eligible_row(broken))

    def test_source_bridge_rejects_unchanged_function_with_transitive_provider_drift(self):
        from parallax_relay.qualification import validate_bridge_changes
        with self.assertRaises(ValueError):
            validate_bridge_changes({'parallax_relay/providers.py':('old','new')})
        with self.assertRaises(ValueError):
            validate_bridge_changes({'parallax_relay/config.py':('old','new')})
        with self.assertRaises(ValueError):
            validate_bridge_changes({'sitecustomize.py':(None,'new')})
        validate_bridge_changes({'docs/LUNA_QUALIFICATION.md':(None,'new')})

    def test_old_protocol_cannot_consume_qualification_authorization(self):
        from parallax_relay.campaign import register, CampaignError
        from parallax_relay.exploratory import profile_spec
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'denied'
            with self.assertRaises(CampaignError):
                register(profile_spec('pilot'),out,qualification=Path(temp)/'forged')
            self.assertFalse(out.exists())

    def test_full_tree_bridge_pins_exact_target_and_rejects_globals_and_import_shadowing(self):
        from unittest.mock import patch
        from parallax_relay import qualification as q
        # Use the real origin sources and candidate execution module texts.
        git=q._git
        origin=q.ORIGIN_REVISION
        target='b'*40
        modules=('parallax_relay/campaign.py','parallax_relay/campaign_models.py')
        before={m:git('show',origin+':'+m) for m in modules}
        after={m:Path(m).read_bytes() for m in modules}
        trees={origin:{m:{'mode':'100644','oid':'a'*40} for m in modules},
               target:{m:{'mode':'100644','oid':'b'*40} for m in modules}}
        def source(*args):
            self.assertEqual(args[0],'show')
            rev,module=args[1].split(':',1)
            return (before if rev==origin else after)[module]
        with patch.object(q,'collect_source',return_value={'status':'clean','revision':target,'reason':None}),patch.object(
                q,'_tree',side_effect=lambda revision:trees[revision]),patch.object(q,'_git',side_effect=source),patch.dict(
                'os.environ',{'PYTHONPATH':'','PYTHONHOME':''}):
            bridge=q.build_bridge()
            self.assertEqual(bridge['target_tree'],trees[target])
            self.assertEqual(bridge['changed_paths'],sorted(modules))
            self.assertEqual(bridge['sha256'],canonical_hash({k:v for k,v in bridge.items() if k!='sha256'}))
            saved=after[modules[0]]
            for mutation in (b'\nHTTPAgent = object\n',b'\nfrom .qualification import build_bridge as HTTPAgent\n',
                             b'\nrun_match.__defaults__ = ()\n',b'\ndef HTTPAgent(*args): return None\n'):
                after[modules[0]]=saved+mutation
                with self.subTest(mutation=mutation),self.assertRaises(ValueError):q.build_bridge()
            after[modules[0]]=saved
            trees[target]['parallax_relay/providers.py']={'mode':'100644','oid':'c'*40}
            with self.assertRaises(ValueError):q.build_bridge()


if __name__=='__main__':unittest.main()
