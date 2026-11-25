"""Shared geometry and sprite masks for the illustrated spectator feeds."""

from functools import lru_cache
from itertools import product
from pathlib import Path

from PIL import Image

from ..protocol import ROLES
from ..render import H, W


_SHEETS = Path(__file__).resolve().parents[2] / 'tools/realtime_spectator/art/animations/sheets'
_TAG_SHIFTS = tuple(product((0, -22, 22), (0, -28, 28, -56, 56, -84, 84, -112, 112)))


@lru_cache(maxsize=2 * len(ROLES))
def robot_mask(role: str, size: tuple[int, int]) -> Image.Image:
    with Image.open(_SHEETS / f'{role.lower()}-idle.png') as sheet:
        mask = sheet.crop((0, 0, 256, 256)).convert('RGBA').getchannel('A')
    mask = mask.crop(mask.getbbox())
    mask.thumbnail(size, Image.Resampling.LANCZOS)
    return mask


def place_tags(preferred, blocked, half_size):
    """Keep badges within the image and clear of earlier badges and equipment."""
    occupied = list(blocked)
    half_width, half_height = half_size
    for role, anchor, (x, y) in preferred:
        y = min(H - half_height - 2, max(half_height + 1, y))
        for dy, dx in _TAG_SHIFTS:
            mark_x, mark_y = x + dx, y + dy
            left, right = mark_x - half_width, mark_x + half_width
            top, bottom = mark_y - half_height, mark_y + half_height
            if left < 1 or right >= W - 1 or top < 1 or bottom >= H - 1:
                continue
            if any(left <= r + 2 and right >= l - 2 and top <= b and bottom >= t
                   for l, t, r, b in occupied):
                continue
            occupied.append((left, top, right, bottom))
            yield role, anchor, (mark_x, mark_y)
            break
