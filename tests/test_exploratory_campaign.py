"""Offline protocol-3 gates; dummy identities never establish model evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from parallax_relay.campaign import (CampaignError, frozen_inputs, register,
    read_registration, validate_registration, validate_pilot_transition)
from parallax_relay.campaign_models import CampaignSpec
from parallax_relay.campaign_validation import validate_frozen
from parallax_relay.exploratory import profile_spec
from parallax_relay.provenance import canonical_hash

CLEAN = {'status': 'clean', 'revision': 'a'*40, 'reason': None}
ALL_ROOMS = {'split_span','dev_01','dev_02','ret_01','ret_02','ret_03',
             'relay_01','relay_02','relay_03'}


def eligible_pilot_report():
    # Gate-focused analyzer fixture; separate real-driver tests cover artifacts.
    return {'cohort_eligible': True, 'completion_status': 'complete',
            'analysis_source': CLEAN, 'anomalies': [],
            'trials': [{'stop_reason': 'turn_limit', 'cleanup_status': 'ok'} for _ in range(60)]}


class ExploratoryCampaignTests(unittest.TestCase):
    def setUp(self):
        for target in ('parallax_relay.campaign.collect_source',
                       'parallax_relay.campaign_analysis.collect_source',
                       'parallax_relay.provenance.collect_source'):
            mocked=patch(target, return_value=CLEAN)
            mocked.start();self.addCleanup(mocked.stop)

    def test_frozen_identity_covers_all_nine_rooms_with_no_inferential_contract(self):
        spec=CampaignSpec.model_validate(profile_spec('pilot'))
        value=frozen_inputs(spec)
        self.assertEqual(set(value['inputs']),ALL_ROOMS)
        self.assertEqual(value['analysis'],{
            'version':3,'profile_id':'exploratory-under20-v1',
            'evidence_class':'exploratory','method':'descriptive_per_room',
            'bootstrap_resamples':0,'seed':0,'percentile':None,'prng':None,
            'concurrency':1,'primary_contrast':['full','disabled']})
        validate_frozen(value,spec,version=2)
        for key,bad in [('bootstrap_resamples',True),('seed',False),('version',3.0)]:
            broken=copy.deepcopy(value);broken['analysis'][key]=bad
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_frozen(broken,spec,version=2)

    def test_pilot_registration_roundtrips_and_strictly_rejects_rehashed_numeric_schedule_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'pilot';registration=register(profile_spec('pilot'),root)
            self.assertEqual(read_registration(root),registration)
            self.assertEqual(len(registration['schedule']),60)
            for key,bad in [('repetition',False),('room_version',True)]:
                changed=copy.deepcopy(registration);changed['schedule'][0][key]=bad
                changed['sha256']=canonical_hash({k:v for k,v in changed.items() if k!='sha256'})
                with self.subTest(key=key),self.assertRaises(CampaignError):
                    validate_registration(changed)

    def test_validation_requires_eligible_nonbinding_same_profile_pilot_and_freezes_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);pilot=base/'pilot';registration=register(profile_spec('pilot'),pilot)
            with self.assertRaises(CampaignError):register(profile_spec('validation'),base/'missing')
            with self.assertRaises(CampaignError):register(profile_spec('validation'),base/'unrun',pilot=pilot)
            for key,bad in [('stop_reason','spend_budget'),('stop_reason','call_budget'),('cleanup_status','failed')]:
                report=eligible_pilot_report();report['trials'][0][key]=bad
                with patch('parallax_relay.campaign_analysis.analyze',return_value=report):
                    with self.subTest(key=key,value=bad),self.assertRaises(CampaignError):
                        register(profile_spec('validation'),base/('rejected-'+bad),pilot=pilot)
            with patch('parallax_relay.campaign_analysis.analyze',return_value=eligible_pilot_report()):
                value=register(profile_spec('validation'),base/'validation',pilot=pilot)
            self.assertEqual(value['pilot']['registration_sha256'],registration['sha256'])
            self.assertEqual(value['pilot']['changed_frozen_sections'],[])
            self.assertFalse(value['pilot']['match_settings_changed'])
            self.assertEqual(read_registration(base/'validation'),value)
            self.assertEqual(len(value['schedule']),120)
            a=CampaignSpec.model_validate(registration['spec']);b=CampaignSpec.model_validate(value['spec'])
            validate_pilot_transition(a,b,registration['frozen'],value['frozen'])
            for section in ('source','environment','inputs','catalog','analysis'):
                changed=copy.deepcopy(value['frozen']);changed[section]={}
                with self.subTest(section=section),self.assertRaises(CampaignError):
                    validate_pilot_transition(a,b,registration['frozen'],changed)


if __name__=='__main__':unittest.main()
