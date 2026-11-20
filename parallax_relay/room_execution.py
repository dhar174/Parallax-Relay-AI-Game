"""Trusted-host permits for the registered runner, not a Python security sandbox."""
from dataclasses import dataclass
import json

from .rooms import get_room,catalog_identity
from .provenance import canonical_hash


@dataclass(frozen=True)
class RoomExecutionPermit:
    registration_json: str
    trial_json: str
    checked_inputs_json: str

    @classmethod
    def from_registration(cls,registration: dict,trial: dict,*,_checked_inputs: dict|None=None):
        """Bind this launch's fresh host check; direct callers collect it here."""
        from .campaign import validate_registration,frozen_inputs
        from .campaign_models import CampaignSpec
        validate_registration(registration)
        checked=(_checked_inputs if _checked_inputs is not None else
                 frozen_inputs(CampaignSpec.model_validate(registration['spec'])))
        permit=cls(json.dumps(registration,sort_keys=True),json.dumps(trial,sort_keys=True),json.dumps(checked,sort_keys=True))
        permit.validate(trial['room'])
        return permit

    def validate(self,room_id: str) -> None:
        from .campaign_models import CampaignSpec
        registration=json.loads(self.registration_json);trial=json.loads(self.trial_json)
        # Recheck immutable registration/trial/catalog bindings at run_match's
        # entry without repeating the launch's Git/package/input scan.
        checked=json.loads(self.checked_inputs_json)
        spec=CampaignSpec.model_validate(registration['spec'])
        if spec.protocol_version==4:
            from .campaign import validate_registration
            from .qualification import check_binding, strict_loads
            # Direct construction must not bypass the file reader's ambiguity
            # checks. Reparse all three serialized authority inputs strictly.
            registration=strict_loads(self.registration_json)
            trial=strict_loads(self.trial_json)
            checked=strict_loads(self.checked_inputs_json)
            validate_registration(registration)
            check_binding(registration['qualification'],checked,kind='qualified')
        if (registration.get('schema_version')!=2 or
            (spec.protocol_version,spec.stage) not in ((2,'confirmatory'),(3,'validation'),(4,'validation')) or
            spec.protocol_version!=4 and (not isinstance(registration.get('pilot'),dict) or not registration['pilot'].get('registration_sha256')) or
            registration.get('sha256')!=canonical_hash({k:v for k,v in registration.items() if k!='sha256'}) or
            trial not in registration['schedule'] or trial['room']!=room_id or
            get_room(room_id).split!='held_out' or trial.get('split')!='held_out' or
            trial.get('catalog_sha256')!=catalog_identity()['sha256'] or
            registration['frozen'].get('catalog')!=catalog_identity() or
            registration['frozen']['source']['status']!='clean' or
            registration['frozen']['environment']['value']['status']!='complete' or
            registration['frozen']!=checked):
            raise ValueError('A held-out room requires a matching registered confirmatory or validation campaign')
