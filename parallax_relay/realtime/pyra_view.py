"""Thermal Bloom, the spectator illustration of a sampled PYRA observation."""

from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..protocol import ROLES
from ..render import DX, H, W, px
from . import physics
from .sensor_art import draw_exit_lamp, exit_lamp_bounds, place_tags, robot_mask


_LEFT = 211
_FAR = _LEFT - physics.BANK_HEIGHT * DX // physics.TILE
_GAP_IN, _GAP_OUT = (round(px(edge / physics.TILE)) for edge in (physics.GAP_LEFT, physics.GAP_RIGHT))
_OPEN, _CLOSE = (round(px(edge / physics.TILE)) for edge in (physics.LEFT_EDGE, physics.RIGHT_EDGE))
_MOTOR, _HOT_Y = px(physics.MOTOR_X // physics.TILE), _LEFT - 20
_CORE = ('#777786', '#aa9eb6', '#d69a86', '#ffd7a9', '#fff8eb')
_RING = ('#565567', '#9688a8', '#ad746f', '#f6a079', '#ffbe83')
_TAG_SIZE = (10, 9)
_GROUP_OFFSETS = {1: (0,), 2: (-13, 13), 3: (-26, 0, 26)}
_MOTOR_OFFSETS = {1: (-45,), 2: (-47, 44), 3: (-73, -46, 44)}


@dataclass(frozen=True)
class ThermalSample:
    columns: tuple[int, ...]
    heat: int
    own_height: int
    powered: bool
    exit_unlocked: bool


@lru_cache(maxsize=2)
def _terrain(powered: bool) -> Image.Image:
    rng = random.Random(612)
    field = Image.frombytes('L', (11, 6), bytes(rng.randrange(22, 231) for _ in range(66)))
    field = field.resize((W, H), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(27))
    image = ImageOps.colorize(field, '#100d1e', '#262539')
    shadows = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(shadows)
    draw.ellipse((-124, 114, 337, 270), fill='#211d32')
    draw.ellipse((507, 99, 923, 229), fill='#292339')
    banks = [(_OPEN, _GAP_IN, _LEFT), (_GAP_OUT, _CLOSE, _FAR)]
    if powered:
        banks.append((_GAP_IN, _GAP_OUT, _LEFT))
    for start, end, y in banks:
        draw.polygon([(start, y), (end, y), (end - 7, H), (start + 8, H)], fill='#1d192e')
        draw.polygon([(start, y), (end, y), (end - 5, y + 15), (start + 4, y + 15)], fill='#302940')
    blurred = shadows.filter(ImageFilter.GaussianBlur(12))
    image.paste(blurred, (0, 0), blurred)
    draw = ImageDraw.Draw(image)
    for start, end, y in banks:
        draw.line((start, y, end, y), fill='#645a76', width=2)
    draw.line((_GAP_OUT, _FAR, _GAP_OUT, _LEFT if powered else _FAR + 18), fill='#4c445b')
    if not powered:
        draw.line((_GAP_IN, _LEFT, _GAP_IN, _LEFT + 14), fill='#4c445b')
    return image


def _robot_feet(sample: ThermalSample):
    for role, column in zip(ROLES, sample.columns):
        x = px(column)
        if role == 'PYRA':
            y = _LEFT - round(sample.own_height * DX / physics.TILE)
        else:
            y = _LEFT if x < _GAP_OUT else _FAR
        yield role, x, y


def _signature_positions(feet):
    groups = defaultdict(list)
    for role, x, y in feet:
        groups[x, y].append(role)
    preferred = []
    for (x, y), roles in groups.items():
        offsets, mark_y = (_MOTOR_OFFSETS, y + 15) if x == _MOTOR else (_GROUP_OFFSETS, y - 10)
        for role, offset in zip(roles, offsets[len(roles)]):
            preferred.append((role, (x, y), (x + offset, mark_y)))
    # Keep the same label positions as the motor warms and cools.
    blocked = [(_MOTOR - 53, _HOT_Y - 40, _MOTOR + 53, _HOT_Y + 21), (25, 19, 185, 100),
               exit_lamp_bounds(_FAR)]
    return place_tags(preferred, blocked, _TAG_SIZE)


def _draw_contacts(image: Image.Image, feet):
    for role, x, y in feet:
        mask = robot_mask(role, (30, 34))
        silhouette = Image.new('L', image.size)
        silhouette.paste(mask, (x - mask.width // 2, y - mask.height))
        image.paste('#695f83', (0, 0, W, H), silhouette.filter(ImageFilter.GaussianBlur(2.7)))
    positions = tuple(_signature_positions(feet))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=15)
    for _, (ax, ay), (x, y) in positions:
        if (ax, ay - 10) != (x, y):
            draw.line([(ax, ay), (x, y), (x, y - 2)], fill='#665d80', width=1)
    for role, _, (x, y) in positions:
        half_width, half_height = _TAG_SIZE
        box = (x - half_width, y - half_height, x + half_width, y + half_height)
        draw.rounded_rectangle(box, radius=7, fill='#0f0c21', outline='#665d80')
        draw.text((x, y), role[0], anchor='mm', font=font, fill='#c5c2dd')


def _arc_box(rx, ry):
    return _MOTOR - rx, _HOT_Y - ry, _MOTOR + rx, _HOT_Y + ry


def _draw_motor(image: Image.Image, heat: int):
    radius = (9, 13, 22, 33, 43)[heat]
    thickness = (0, 1, 2, 2, 3)[heat]
    halo = Image.new('RGBA', image.size)
    glow = ImageDraw.Draw(halo)
    if heat >= 2:
        glow.ellipse(_arc_box(radius + 12, round(radius * .75)), fill='#922c5a')
        glow.ellipse(_arc_box(radius - 5, round(radius * .50)), fill='#f65f3c')
        glow.ellipse(_arc_box(round(radius * .38), round(radius * .32)), fill=_RING[heat])
    else:
        glow.ellipse(_arc_box(radius + 1, radius - 1), fill='#534560')
    blurred = halo.filter(ImageFilter.GaussianBlur(8 if heat >= 2 else 4))
    image.paste(blurred, (0, 0), blurred)

    draw = ImageDraw.Draw(image)
    if thickness:
        draw.ellipse(_arc_box(radius, round(radius * .65)), outline=_RING[heat], width=thickness)
    if heat >= 3:
        draw.arc(_arc_box(radius + 7, round(radius * .65) + 6), 193, 347, fill='#de7384', width=2)
    if heat == physics.HEAT_LIMIT:
        draw.arc(_arc_box(radius + 13, round(radius * .65) + 11), 205, 334, fill='#995675', width=2)
    core_size = (5, 7, 8, 10, 13)[heat]
    draw.rounded_rectangle(_arc_box(core_size, core_size), radius=4, fill=_CORE[heat])
    draw.line((_MOTOR - 4, _HOT_Y + 2, _MOTOR + 4, _HOT_Y + 2),
              fill='#584363' if heat < 2 else '#b9716d', width=2)


def _draw_meter(image: Image.Image, heat: int):
    draw = ImageDraw.Draw(image)
    draw.text((29, 21), 'MOTOR HEAT', font=ImageFont.load_default(size=18), fill='#d5cde4')
    draw.text((28, 43), str(heat), font=ImageFont.load_default(size=51), fill='#faf4ff')
    for step in range(1, physics.HEAT_LIMIT + 1):
        left = 81 + (step - 1) * 25
        color = _CORE[heat] if step <= heat else '#252035'
        draw.rounded_rectangle((left, 57, left + 19, 71), radius=3, fill=color, outline='#826e8d')
    draw.line((181, 54, 181, 75), fill='#bba5c8', width=2)
    state = 'AT LIMIT' if heat == physics.HEAT_LIMIT else 'LOW HEAT' if heat <= 1 else f'LIMIT {physics.HEAT_LIMIT}'
    draw.text((81, 80), state, font=ImageFont.load_default(size=15), fill='#ded0e9')


@lru_cache(maxsize=32)
def render_thermal_bloom(sample: ThermalSample) -> bytes:
    image = _terrain(sample.powered).copy()
    _draw_contacts(image, tuple(_robot_feet(sample)))
    _draw_motor(image, sample.heat)
    _draw_meter(image, sample.heat)
    draw_exit_lamp(image, _FAR, sample.exit_unlocked)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
