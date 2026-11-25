"""Circuit Relief, the spectator illustration of a sampled FLUX observation."""
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from itertools import product
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from ..protocol import ROLES
from ..render import DX, H, W, px
from . import physics


_SHEETS = Path(__file__).resolve().parents[2] / 'tools/realtime_spectator/art/animations/sheets'
_LEFT = 207
_FAR = _LEFT - physics.BANK_HEIGHT * DX // physics.TILE
_START, _END = (round(px(x / physics.TILE)) for x in (physics.GAP_LEFT, physics.GAP_RIGHT))
_ROOT = px(physics.MOTOR_X // physics.TILE)
_EXIT = px(physics.EXIT_X // physics.TILE)
_CELL = px(physics.CELL_X // physics.TILE)
_SOURCE_Y, _PATH_Y, _CELL_Y = _LEFT - 17, _LEFT + 12, _FAR - 35
_MINT, _CORE = '#8dffe0', '#f0fff8'
_RIM, _INK = '#8eaabf', '#d3e1eb'
_TAG_SIZE = (12, 9)
_TAG_SHIFTS = tuple(product((0, -22, 22), (0, -28, 28, -56, 56, -84, 84, -112, 112)))
_GROUP_OFFSETS = {1: (0,), 2: (-14, 14), 3: (-28, 0, 28)}
_RELAY_OFFSETS = {1: (30,), 2: (-30, 30), 3: (-59, -31, 31)}


@dataclass(frozen=True)
class CircuitSample:
    columns: tuple[int, ...]  # The same role order and snapped columns as the original PNG.
    flux_height: int
    powered: bool
    cell_recovered: bool


@lru_cache(maxsize=2)
def _scenery(powered: bool) -> Image.Image:
    rng = random.Random(602)
    field = Image.frombytes('L', (18, 8), bytes(rng.randrange(255) for _ in range(144)))
    field = field.resize((W, H), Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(17))
    world = ImageOps.colorize(field, '#0c1623', '#25384a')
    relief = Image.new('RGBA', world.size)
    draw = ImageDraw.Draw(relief)
    banks = [(px(-.5), _START, _LEFT), (_END, px(12.5), _FAR)]
    if powered:
        banks.append((_START, _END, _LEFT))
    for left, right, y in banks:
        draw.polygon([(left, y), (right, y), (right - 4, y + 40), (right - 10, H),
                      (left + 8, H)], fill='#152332')
        draw.polygon([(left, y), (right, y), (right - 5, y + 14), (left + 6, y + 14)],
                     fill='#314657')
        for depth in (y + 28, y + 48):
            draw.polygon([(left + 6, depth), (right - 7, depth + 4),
                          (right - 13, depth + 10), (left + 9, depth + 8)], fill='#2b3c4a')
    draw.rounded_rectangle((_EXIT - 14, _FAR - 58, _EXIT + 14, _FAR + 5), radius=7, fill='#344653')
    draw.rounded_rectangle((_EXIT - 9, _FAR - 50, _EXIT + 8, _FAR), radius=4, fill='#1b2936')
    draw.rounded_rectangle((_ROOT - 10, _LEFT - 24, _ROOT + 11, _LEFT + 2), radius=5, fill='#3b4a58')
    blurred = relief.filter(ImageFilter.GaussianBlur(6))
    world.paste(blurred, (0, 0), blurred)
    draw = ImageDraw.Draw(world)
    for left, right, y in banks:
        draw.line((left, y, right, y), fill='#526575', width=2)
    draw.line((_END, _FAR, _END, _LEFT if powered else _FAR + 19), fill='#4b6070')
    if not powered:
        draw.line((_START, _LEFT, _START, _LEFT + 17), fill='#4b6070')
    return world


@lru_cache(maxsize=len(ROLES))
def _robot_mask(role: str) -> Image.Image:
    with Image.open(_SHEETS / f'{role.lower()}-idle.png') as sheet:
        mask = sheet.crop((0, 0, 256, 256)).convert('RGBA').getchannel('A')
    mask = mask.crop(mask.getbbox())
    mask.thumbnail((33, 37), Image.Resampling.LANCZOS)
    return mask


def _robot_feet(sample: CircuitSample):
    for role, column in zip(ROLES, sample.columns):
        x = px(column)
        if role == 'FLUX':
            y = _LEFT - sample.flux_height * DX / physics.TILE
        else:
            y = _LEFT if x < _END else _FAR
        yield role, x, y


def _draw_bodies(image: Image.Image, feet):
    for role, x, y in feet:
        mask = _robot_mask(role)
        silhouette = Image.new('L', (W, H))
        silhouette.paste(mask, (round(x - mask.width / 2), round(y - mask.height)))
        blurred = silhouette.filter(ImageFilter.GaussianBlur(2.5))
        image.paste('#5a7082' if role == 'FLUX' else '#4b5d6d', (0, 0, W, H), blurred)
        if role == 'FLUX':
            ImageDraw.Draw(image).line((x - 8, y + 4, x + 8, y + 4), '#668092', 2)


def _signature_positions(feet, sample: CircuitSample):
    groups = defaultdict(list)
    for role, x, y in feet:
        groups[x, round(y)].append(role)
    # Protect the bright equipment cues and leave a gap between badge contours.
    occupied = [(_ROOT - 10, _SOURCE_Y - 10, _ROOT + 10, _SOURCE_Y + 10)]
    if sample.powered:
        occupied.extend([
            (_ROOT - 7, _PATH_Y - 7, _END + 7, _PATH_Y + 7),
            (_END - 7, _FAR - 1, _END + 7, _PATH_Y),
        ])
    if not sample.cell_recovered:
        occupied.append((_CELL - 8, _CELL_Y - 16, _CELL + 8, _CELL_Y + 13))

    half_width, half_height = _TAG_SIZE
    for (x, y), roles in groups.items():
        offsets = _RELAY_OFFSETS if (x, y) == (_ROOT, _LEFT) else _GROUP_OFFSETS
        for role, offset in zip(roles, offsets[len(roles)]):
            preferred_y = min(H - half_height - 2, max(half_height + 1, y - 12))
            # If the circuit blocks its entire row, try a neighboring row.
            for dy, dx in _TAG_SHIFTS:
                mark_x, mark_y = x + offset + dx, preferred_y + dy
                left, right = mark_x - half_width, mark_x + half_width
                top, bottom = mark_y - half_height, mark_y + half_height
                if left < 1 or right >= W - 1 or top < 1 or bottom >= H - 1:
                    continue
                if any(left <= r + 2 and right >= l - 2 and top <= b and bottom >= t
                       for l, t, r, b in occupied):
                    continue
                occupied.append((left, top, right, bottom))
                yield role, (x, y), (mark_x, mark_y)
                break


def _draw_signatures(image: Image.Image, positions):
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=15)
    half_width, half_height = _TAG_SIZE
    for _, (ax, ay), (x, y) in positions:
        draw.line([(ax, ay - 1), (x, ay - 1), (x, y + half_height)], fill='#6f879a')
    for role, _, (x, y) in positions:
        left, top, right, bottom = x - half_width, y - half_height, x + half_width, y + half_height
        box = (left, top, right, bottom)
        if role == 'SPECTRA':
            draw.rectangle(box, fill='#192935', outline=_RIM)
        elif role == 'PYRA':
            draw.rounded_rectangle(box, radius=7, fill='#192935', outline=_RIM)
        else:
            draw.polygon([(left + 5, top), (right - 5, top), (right, top + 5), (right, bottom - 5),
                          (right - 5, bottom), (left + 5, bottom), (left, bottom - 5), (left, top + 5)],
                         fill='#223745', outline=_INK)
        draw.text((x, y + 1), role[0], font=font, fill=_INK, anchor='mm')


def _draw_power(image: Image.Image, sample: CircuitSample):
    root, cy = _ROOT, _SOURCE_Y
    cell_x, cell_y = _CELL, _CELL_Y
    path = [(root, cy), (root, _PATH_Y), (_END, _PATH_Y), (_END, _FAR + 1)]
    glow = Image.new('RGBA', image.size)
    draw = ImageDraw.Draw(glow)
    if sample.powered:
        draw.line(path, fill='#48ffe0', width=15, joint='curve')
        draw.ellipse((root - 12, cy - 12, root + 12, cy + 12), fill='#48ffe0')
    if not sample.cell_recovered:
        draw.rounded_rectangle((cell_x - 11, cell_y - 15, cell_x + 11, cell_y + 15),
                               radius=4, fill='#48ffe0')
    glow = glow.filter(ImageFilter.GaussianBlur(10))
    image.paste(glow, (0, 0), glow)
    draw = ImageDraw.Draw(image)
    if sample.powered:
        for color, width in (('#133f41', 15), ('#24ae96', 10), (_MINT, 7), (_CORE, 2)):
            draw.line(path, fill=color, width=width, joint='curve')
        draw.ellipse((root - 10, cy - 10, root + 10, cy + 10), fill='#152932', outline=_MINT, width=2)
        draw.polygon([(root + 1, cy - 7), (root - 5, cy + 1), (root - 1, cy + 1), (root - 2, cy + 7),
                      (root + 5, cy - 2), (root + 1, cy - 2)], fill=_CORE)
        for x in range(_START + 30, _END - 14, 36):
            draw.line([(x - 6, _PATH_Y - 5), (x + 1, _PATH_Y), (x - 6, _PATH_Y + 5)],
                      fill='#13383c', width=5)
            draw.line([(x - 4, _PATH_Y - 5), (x + 3, _PATH_Y), (x - 4, _PATH_Y + 5)],
                      fill=_CORE, width=2)
        draw.rectangle((_END - 3, _FAR - 1, _END + 4, _FAR + 4), fill=_CORE)
    else:
        draw.ellipse((root - 7, cy - 7, root + 7, cy + 7), outline='#758b9a')
        draw.line((root - 3, cy + 3, root + 3, cy + 3), fill='#677e8e')
    if not sample.cell_recovered:
        draw.rounded_rectangle((cell_x - 8, cell_y - 13, cell_x + 8, cell_y + 13),
                               radius=4, fill='#1c433f', outline=_CORE, width=2)
        draw.rectangle((cell_x - 3, cell_y - 16, cell_x + 3, cell_y - 13), fill=_CORE)
        for y in (cell_y - 6, cell_y, cell_y + 6):
            draw.line((cell_x - 4, y, cell_x + 4, y), fill=_MINT, width=2)


@lru_cache(maxsize=32)
def render_circuit_relief(sample: CircuitSample) -> bytes:
    image = _scenery(sample.powered).copy()
    feet = tuple(_robot_feet(sample))
    _draw_bodies(image, feet)
    _draw_signatures(image, tuple(_signature_positions(feet, sample)))
    _draw_power(image, sample)
    buffer = BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
