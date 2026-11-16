"""Privileged offline proofs, never imported by participant policy construction."""
from dataclasses import asdict
from types import MappingProxyType
from .state import Action, initial_world
from .engine import resolve_turn
from .rooms import rooms, get_room, room_hash, digest
from .scripted import PLAN

ROLES=('SPECTRA','PYRA','FLUX')
_A=MappingProxyType({'W':Action('WAIT'),'V':Action('VENT'),'R':Action('REROUTE'),
    'C':Action('COLLECT'),'U':Action('UNLOCK'),'>1':Action('MOVE',1,1),'>2':Action('MOVE',1,2),
    '<1':Action('MOVE',-1,1),'<2':Action('MOVE',-1,2)})
_STEPS=MappingProxyType({
 'dev_01':(('>2','>2','R'),('>2','>2','>2'),('>2','>2','>2'),('C','>2','>1'),('>2','>1','C'),('>2','W','>2'),('W','W','>1'),('W','W','U')),
 'dev_02':(('>2','V','R'),('>2','>2','>2'),('>2','>2','>2'),('>2','>2','>1'),('>1','>2','C'),('C','>1','>2'),('>2','W','>1'),('W','W','U')),
 'ret_01':(('>2','V','R'),('>2','<1','<1'),('>2','W','C'),('C','W','<1'),('<2','W','U'),('<2','W','W'),('<2','W','W'),('<2','W','W')),
 'ret_02':(('>2','<2','R'),('>2','W','<1'),('>2','W','C'),('>1','W','<2'),('C','W','U'),('<2','W','W'),('<2','W','W'),('<2','W','W'),('<2','W','W')),
 'ret_03':(('>2','V','R'),('>2','<2','<1'),('>2','W','C'),('>1','W','<2'),('C','W','U'),('<2','W','W'),('<2','W','W'),('<2','W','W'),('<2','W','W'),('<1','W','W')),
 'relay_01':(('>2','V','R'),('>2','>2','C'),('W','>1','>2'),('>2','V','R'),('C','>2','>1'),('>1','>2','C'),('W','W','>2'),('W','W','>1'),('W','W','U')),
 'relay_02':(('>2','>2','R'),('>2','>2','C'),('>2','W','>2'),('W','V','>1'),('>2','>2','R'),('C','>2','>1'),('>1','W','C'),('W','W','>2'),('W','W','>1'),('W','W','U')),
 'relay_03':(('>2','V','R'),('>2','>2','C'),('>2','>2','>2'),('W','V','>1'),('>2','>2','R'),('C','>2','>1'),('>1','W','C'),('W','W','>2'),('W','W','>1'),('W','W','U')),
})


def certificate(room_id: str) -> tuple[dict[str,Action],...]:
    get_room(room_id)
    if room_id=='split_span':return tuple(dict(row) for row in PLAN)
    return tuple(dict(zip(ROLES,(_A[token] for token in row))) for row in _STEPS[room_id])


def certificate_hash(room_id: str) -> str:
    return digest({'room_sha256':room_hash(get_room(room_id)),
        'steps':[{role:asdict(action) for role,action in row.items()} for row in certificate(room_id)]})


def verify_catalog() -> list[dict]:
    result=[]
    for room in rooms():
        world=initial_world(room.id)
        for row in certificate(room.id):
            if world.win or world.loss:raise ValueError('Certificate contains actions after termination')
            outcomes={};world=resolve_turn(world,row,diagnostics=outcomes)
            if any(value not in ('applied','wait') for value in outcomes.values()):
                raise ValueError('Certificate contains illegal or redundant actions')
        goals=world.shard_collected and world.energy>=4 and all(r.damage==0 for r in world.robots.values())
        if not world.win or not goals or world.turn>room.deadline or min(world.energy,world.coolant)<0:
            raise ValueError('Room certificate did not prove the full mission')
        fixed=initial_world(room.id)
        for turn in range(room.deadline):
            fixed=resolve_turn(fixed,PLAN[turn] if turn<len(PLAN) else {r:Action('WAIT') for r in ROLES})
            if fixed.win or fixed.loss:break
        if room.split=='held_out' and fixed.win:raise ValueError('Held-out room accepts the memorized script')
        result.append({'room_id':room.id,'family':room.family,'split':room.split,'room_sha256':room_hash(room),
                       'certificate_sha256':certificate_hash(room.id),'win':world.win,'private_goals_met':bool(goals),
                       'turns':world.turn,'energy':world.energy,'fixed_script_win':fixed.win})
    return result
