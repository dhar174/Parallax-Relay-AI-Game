"""Protocol-v1 treatments shared by the driver, provenance and interfaces."""
from dataclasses import dataclass
from typing import Literal

ConditionName = Literal['full', 'reduced', 'disabled', 'withheld', 'no_images']
NOTICE_VERSION = 1


@dataclass(frozen=True)
class Condition:
    name: str
    phases: tuple[str, ...]
    deliver_messages: bool = True
    include_image: bool = True

    @property
    def communication_rounds(self) -> int:
        return len(self.phases) - 1

    def notice(self) -> dict:
        # The same factual template in every arm; no replacement deliberation.
        return {'version': NOTICE_VERSION, 'phases': list(self.phases),
                'public_messages_available': self.deliver_messages,
                'role_image_available': self.include_image}


CONDITIONS = {
    'full': Condition('full', ('broadcast', 'negotiate', 'commit')),
    'reduced': Condition('reduced', ('broadcast', 'commit')),
    'disabled': Condition('disabled', ('commit',), False),
    'withheld': Condition('withheld', ('broadcast', 'negotiate', 'commit'), False),
    'no_images': Condition('no_images', ('broadcast', 'negotiate', 'commit'), True, False),
}


def resolve_condition(settings) -> Condition:
    return CONDITIONS[settings.condition or {0: 'disabled', 1: 'reduced', 2: 'full'}[settings.communication_rounds]]
