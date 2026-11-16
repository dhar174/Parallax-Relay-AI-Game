"""Trusted-host permits for the registered runner, not a Python security sandbox."""
from dataclasses import dataclass
import json

from .rooms import get_room,catalog_identity
from .provenance import canonical_hash


@dataclass(frozen=True)
class RoomExecutionPermit:
    registration_json: str
    trial_json: str

    @classmethod
    def from_registration(cls,registration: dict,trial: dict):
        from .campaign import validate_registration
        validate_registration(registration)
        permit=cls(json.dumps(registration,sort_keys=True),json.dumps(trial,sort_keys=True))
        permit.validate(trial['room'])
        return permit

    def validate(self,room_id: str) -> None:
        from .campaign_models import CampaignSpec
        from .campaign import frozen_inputs
        registration=json.loads(self.registration_json);trial=json.loads(self.trial_json)
        spec=CampaignSpec.model_validate(registration['spec'])
        if (registration.get('schema_version')!=2 or spec.protocol_version!=2 or spec.stage!='confirmatory' or
            not isinstance(registration.get('pilot'),dict) or not registration['pilot'].get('registration_sha256') or
            registration.get('sha256')!=canonical_hash({k:v for k,v in registration.items() if k!='sha256'}) or
            trial not in registration['schedule'] or trial['room']!=room_id or
            get_room(room_id).split!='held_out' or trial.get('split')!='held_out' or
            trial.get('catalog_sha256')!=catalog_identity()['sha256'] or
            registration['frozen'].get('catalog')!=catalog_identity() or
            registration['frozen']['source']['status']!='clean' or
            registration['frozen']['environment']['value']['status']!='complete' or
            registration['frozen']!=frozen_inputs(spec)):
            raise ValueError('A held-out room requires a matching registered confirmatory campaign')
