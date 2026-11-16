"""Antigravity Sonnet review reproductions; offline native paths only."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay import campaign
from parallax_relay.campaign_models import CampaignSpec

CLEAN={'status':'clean','revision':'a'*40,'reason':None}


def confirmation(root):
    value={'schema_version':2,'protocol_version':2,'stage':'pilot','mode':'offline',
           'match':{'max_turns':1,'max_attempts':1},'campaign_max_calls':36}
    campaign.register(value,root/'pilot')
    value['stage']='confirmatory'
    with patch('parallax_relay.campaign_analysis.analyze',return_value={'cohort_eligible':True}):
        return campaign.register(value,root/'confirmation',pilot=root/'pilot')


class SonnetCampaignTests(unittest.IsolatedAsyncioTestCase):
    async def test_permit_setup_failure_closes_ledger_and_releases_entire_block(self):
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN):
            root=Path(temp);confirmation(root);out=root/'confirmation'
            with patch('parallax_relay.room_execution.RoomExecutionPermit.from_registration',side_effect=ValueError('SECRET_SENTINEL')),patch('parallax_relay.campaign.Recorder') as recorder,patch('parallax_relay.campaign.make_policy') as policy,patch('parallax_relay.campaign.HTTPAgent') as http:
                await campaign.run_campaign(out,offline=True)
            recorder.assert_not_called();policy.assert_not_called();http.assert_not_called()
            events=[json.loads(line) for line in (out/'ledger.jsonl').read_text().splitlines()]
            receipt=next(row for row in events if row['event']=='trial_finished')
            self.assertEqual(receipt['stop_reason'],'setup_failure');self.assertEqual(receipt['stage'],'setup')
            self.assertEqual(receipt['accounted_calls'],0);self.assertIsNone(receipt['result'])
            self.assertEqual(events[-2]['event'],'block_released');self.assertEqual(events[-1]['reason'],'setup_failure')
            self.assertEqual(events[-1]['accounted_calls'],0)
            reserved=sum(row['reserved_calls'] for row in events if row['event']=='block_reserved')
            released=sum(row['released_calls'] for row in events if row['event'] in ('trial_finished','block_released'))
            self.assertEqual(reserved,released)
            self.assertFalse((out/'.runner.lock').exists());self.assertFalse((out/'trials').exists())
            self.assertNotIn('SECRET_SENTINEL',(out/'ledger.jsonl').read_text())

    async def test_one_frozen_scan_per_heldout_launch_with_entry_gate_preserved(self):
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN),patch('parallax_relay.provenance.collect_source',return_value=CLEAN):
            root=Path(temp);registration=confirmation(root);out=root/'confirmation'
            with patch('parallax_relay.campaign.frozen_inputs',return_value=registration['frozen']) as scan:
                await campaign.run_campaign(out,offline=True)
            events=[json.loads(line) for line in (out/'ledger.jsonl').read_text().splitlines()]
            launched=[row for row in events if row['event']=='trial_launched']
            self.assertEqual(len(launched),5)  # One fully admitted native five-arm block.
            self.assertEqual(scan.call_count,1+len(launched))  # Preflight plus one fresh scan per launch.
            self.assertTrue(all(row['stop_reason']=='turn_limit' for row in events if row['event']=='trial_finished'))

    async def test_direct_trial_scans_once_and_rejects_drift_before_output(self):
        with tempfile.TemporaryDirectory() as temp,patch('parallax_relay.campaign.collect_source',return_value=CLEAN):
            root=Path(temp);registration=confirmation(root);spec=CampaignSpec.model_validate(registration['spec'])
            trial=next(t for t in registration['schedule'] if t['team']=='wait' and t['condition']=='disabled')
            with patch('parallax_relay.campaign.frozen_inputs',return_value=registration['frozen']) as scan:
                receipt=await campaign.execute_trial(root/'native',registration,spec,trial,{})
            self.assertEqual(receipt['stop_reason'],'turn_limit');self.assertEqual(scan.call_count,1)
            changed=copy.deepcopy(registration['frozen']);changed['source']['status']='unavailable'
            with patch('parallax_relay.campaign.frozen_inputs',return_value=changed),patch('parallax_relay.campaign.Recorder') as recorder:
                failed=await campaign.execute_trial(root/'rejected',registration,spec,trial,{})
            self.assertEqual(failed['stop_reason'],'setup_failure');recorder.assert_not_called()
            self.assertFalse((root/'rejected').exists())


class SonnetCLITests(unittest.TestCase):
    def test_initial_manifest_uses_selected_room_when_setup_fails(self):
        from parallax_relay.play import main
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'run'
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()),patch('parallax_relay.play.ScriptedAgent',side_effect=OSError('setup failure')):
                self.assertEqual(main(['--mock','--quiet','--room','dev_02','--out',str(out)]),2)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['room'],'dev_02')
