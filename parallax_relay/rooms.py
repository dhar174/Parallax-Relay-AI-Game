"""Finite, immutable room definitions. Full definitions are spectator-only."""
from typing import Literal
import hashlib
import json
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator


class BridgeDefinition(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,strict=True)
    gap: tuple[int,...]
    motor: int=Field(ge=0)
    heat: int=Field(ge=0,le=12)

    @model_validator(mode='after')
    def valid_gap(self):
        if not self.gap or tuple(range(min(self.gap),max(self.gap)+1))!=self.gap:
            raise ValueError('Bridge gap must be contiguous and unique')
        return self


class RoomDefinition(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True,strict=True)
    id: str=Field(pattern=r'^[a-z][a-z0-9_]{0,63}$')
    version: Literal[1]=1
    family: Literal['crossing','retrieval_return','two_bridge_relay']
    split: Literal['development','held_out']
    width: int=Field(ge=3,le=13)
    deadline: Literal[12]=12
    bridges: tuple[BridgeDefinition,...]
    exit: int
    shard: int
    cells: tuple[int,...]
    starts: tuple[int,int,int]
    energy: Literal[6]=6
    coolant: int=Field(ge=0,le=12)
    cell_value: Literal[2]=2
    requires_shard: bool=False
    scoring_version: Literal[1]=1
    generation: Literal['curated']='curated'
    generation_seed: None=None

    @field_validator('version','scoring_version','deadline','energy','cell_value',mode='before')
    @classmethod
    def integer_literals(cls,value):
        if type(value) is not int:raise ValueError('Integer metadata requires an integer')
        return value

    @model_validator(mode='after')
    def valid_room(self):
        if not 1<=len(self.bridges)<=2 or not self.cells or len(set(self.cells))!=len(self.cells):
            raise ValueError('Invalid bridges or cells')
        gaps=[x for bridge in self.bridges for x in bridge.gap]
        coords=[*gaps,self.exit,self.shard,*self.cells,*self.starts,*(b.motor for b in self.bridges)]
        if any(type(x) is not int or not 0<=x<self.width for x in coords) or len(set(gaps))!=len(gaps):
            raise ValueError('Invalid room coordinates')
        if set(gaps)&{self.exit,self.shard,*self.cells,*self.starts,*(b.motor for b in self.bridges)}:
            raise ValueError('Objects and starts require floor')
        if any(abs(a.motor-b.motor)<=2 for i,a in enumerate(self.bridges) for b in self.bridges[i+1:]):
            raise ValueError('Ambiguous controller interaction ranges')
        if any(b.motor>=min(b.gap) for b in self.bridges):
            raise ValueError('Controllers precede their bridges')
        if tuple(min(b.gap) for b in self.bridges)!=tuple(sorted(min(b.gap) for b in self.bridges)):
            raise ValueError('Bridges require canonical order')
        if self.family=='crossing':
            valid=self.split=='development' and len(self.bridges)==1 and self.exit>max(gaps) and self.shard>max(gaps) and not self.requires_shard
        elif self.family=='retrieval_return':
            valid=self.split=='held_out' and len(self.bridges)==1 and self.exit<min(gaps) and self.shard>max(gaps) and self.requires_shard
        else:
            valid=self.split=='held_out' and len(self.bridges)==2 and self.exit>max(gaps) and self.shard>max(gaps) and not self.requires_shard
        if not valid or any(x>=min(gaps) for x in self.starts):
            raise ValueError('Room does not match its structural family')
        return self


def _room(id,width,gaps,motors,exit,shard,cells,starts,heats,coolant):
    family='crossing' if id in ('split_span','dev_01','dev_02') else 'retrieval_return' if id.startswith('ret_') else 'two_bridge_relay'
    return RoomDefinition(id=id,width=width,family=family,split='development' if family=='crossing' else 'held_out',
        bridges=tuple(BridgeDefinition(gap=g,motor=m,heat=h) for g,m,h in zip(gaps,motors,heats)),
        exit=exit,shard=shard,cells=cells,starts=starts,coolant=coolant,requires_shard=family=='retrieval_return')


_ROOMS=(
    _room('split_span',13,((5,6,7),),(4,),12,9,(10,),(2,3,4),(4,),2),
    _room('dev_01',13,((5,6,7),),(4,),12,8,(9,),(2,3,4),(2,),2),
    _room('dev_02',13,((5,6,7),),(4,),12,10,(9,),(1,3,4),(5,),1),
    _room('ret_01',9,((3,4),),(2,),0,8,(1,),(2,1,2),(4,),1),
    _room('ret_02',9,((4,5),),(3,),0,8,(2,),(1,2,3),(2,),1),
    _room('ret_03',11,((5,6),),(4,),1,10,(3,),(3,3,4),(5,),1),
    _room('relay_01',9,((3,),(6,)),(2,5),8,7,(2,5),(1,1,2),(4,4),2),
    _room('relay_02',10,((3,),(7,)),(2,6),9,8,(2,6),(0,1,2),(2,5),2),
    _room('relay_03',11,((4,),(8,)),(3,7),10,9,(3,7),(1,2,3),(5,4),2),
)


def rooms(*,split: str|None=None) -> tuple[RoomDefinition,...]:
    if split not in (None,'development','held_out'):raise ValueError('Unknown room split')
    return tuple(room for room in _ROOMS if split is None or room.split==split)


def get_room(room_id: str='split_span') -> RoomDefinition:
    for room in _ROOMS:
        if type(room_id) is str and room.id==room_id:return room
    raise ValueError('Unknown room selection')


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def room_hash(room: RoomDefinition) -> str:
    return digest(room.model_dump(mode='json'))


def catalog_identity() -> dict:
    from .room_certificates import certificate_hash
    value={'id':'catalog_v1','version':1,'rooms':[r.model_dump(mode='json') for r in rooms()],
           'certificates':{r.id:certificate_hash(r.id) for r in rooms()}}
    return {'value':value,'sha256':digest(value)}


def validate_snapshot(value: dict,room: RoomDefinition) -> None:
    """Validate recorded geometry/state without constructing a live engine world."""
    if not isinstance(value,dict):raise ValueError('Invalid room snapshot')
    if value.get('room_id')!=room.id or type(value.get('room_version')) is not int or value['room_version']!=room.version:
        raise ValueError('Snapshot room identity mismatch')
    for key in ('turn','energy','coolant'):
        if type(value.get(key)) is not int or value[key]<0:raise ValueError('Invalid room counter')
    if value['turn']>room.deadline:raise ValueError('Room deadline exceeded')
    robots=value.get('robots')
    if not isinstance(robots,dict) or set(robots)!={'SPECTRA','PYRA','FLUX'}:raise ValueError('Invalid room roster')
    for role,robot in robots.items():
        if (not isinstance(robot,dict) or robot.get('role')!=role or type(robot.get('x')) is not int or
            not 0<=robot['x']<room.width or type(robot.get('damage')) is not int or robot['damage']<0):
            raise ValueError('Invalid recorded robot')
    keys={f'bridge_{i}' for i in range(len(room.bridges))};heats=value.get('motor_heats')
    if not isinstance(heats,dict) or set(heats)!=keys or any(type(v) is not int or v<0 for v in heats.values()):
        raise ValueError('Invalid motor state')
    for key,allowed in (('powered_bridges',keys),('collected_cells',set(room.cells))):
        values=value.get(key)
        if not isinstance(values,list) or any(type(v) is not (str if key=='powered_bridges' else int) for v in values):raise ValueError('Invalid room set')
        if len(set(values))!=len(values) or not set(values)<=allowed:raise ValueError('Unknown room state reference')
    for key in ('exit_unlocked','shard_collected','win','loss'):
        if type(value.get(key)) is not bool:raise ValueError('Invalid room flag')
    if value['win'] and (value['loss'] or not value['exit_unlocked'] or any(r['x']!=room.exit for r in robots.values()) or room.requires_shard and not value['shard_collected']):
        raise ValueError('Contradictory room victory')
    if value['loss'] and (value['win'] or value['turn']!=room.deadline):raise ValueError('Contradictory room defeat')
    if not isinstance(value.get('events'),list) or any(not isinstance(e,str) for e in value['events']):raise ValueError('Invalid public events')
    if len(room.bridges)==1:
        aliases={'motor_heat':heats['bridge_0'],'bridge_extended':'bridge_0' in value['powered_bridges'],
                 'cell_collected':set(room.cells)<=set(value['collected_cells'])}
        for key,expected in aliases.items():
            if key in value and (type(value[key]) is not type(expected) or value[key]!=expected):raise ValueError('Contradictory legacy alias')
