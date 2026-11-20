"""Pack and check the offline platformer art from editable, registered RGBA poses."""

import argparse
import hashlib
import json
import math
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ART = Path(__file__).resolve().parent / "art"
ANIMATIONS = ART / "animations"
CELL = 256
PIVOT = (128, 239)
ROLES = ("spectra", "pyra", "flux")
CLIPS = {
    "idle": ("idle_1", "idle_2", "idle_3", "idle_4"),
    "walk": ("near_contact", "near_support", "far_approach",
             "far_contact", "far_support", "near_approach"),
    "jump": ("takeoff", "ascent", "descent", "landing"),
}
FPS = {"idle": 2, "walk": 8}
PREVIEW_DELAYS = {"idle": [500] * 4, "walk": [120, 130] * 3,
                  "jump": [150, 230, 260, 200]}
LIGHT = (239, 232, 215)
DARK = (37, 48, 58)
ANGLE_NOTE = "Three-quarter right-facing. Mirror only the artwork around its nominal anchor."
PACK_NOTE = "Pixel-edge coordinates use the untrimmed frame's top-left as the origin."


def read_rgba(path):
    with Image.open(path) as image:
        if image.format != "PNG" or image.mode != "RGBA":
            raise ValueError(f"Expected RGBA PNG at {path}")
        return image.copy()


def encoded(image, file_format, **options):
    stream = BytesIO()
    image.save(stream, format=file_format, **options)
    return stream.getvalue()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files_agree(path, payload):
    if not path.is_file():
        return False
    old = path.read_bytes()
    if old == payload:
        return True
    # Preserve upstream encodings when every decoded RGBA pixel agrees.
    if path.suffix == ".png":
        with Image.open(BytesIO(payload)) as expected, Image.open(BytesIO(old)) as actual:
            return (expected.mode == actual.mode and expected.size == actual.size
                    and expected.tobytes() == actual.tobytes())
    return False


def output(path, payload, check):
    if files_agree(path, payload):
        return
    if check:
        raise ValueError(f"Missing or stale asset: {path.relative_to(ART)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    if path.read_bytes() != payload:
        raise OSError(f"Could not verify written asset: {path}")


def registered_pose(source, spec):
    """Use the digital artist's source window and pivot, preserving the stance height."""
    left, top, right, bottom = spec["bounds"]
    if not (0 <= left < right <= source.width and 0 <= top < bottom <= source.height):
        raise ValueError(f"Out-of-sheet source rectangle: {spec['bounds']}")
    crop = source.crop((left, top, right, bottom))
    alpha = crop.getchannel("A")
    # Preserve antialiasing and contiguous antenna light. Discard distant nearly
    # invisible specks in the raw generator canvas before resampling the cutout.
    threshold = spec.get("edge_threshold", 4)
    near_art = alpha.point(lambda a: 255 if a >= threshold else 0).filter(ImageFilter.MaxFilter(7))
    crop.putalpha(ImageChops.multiply(alpha, near_art))
    scale = spec["scale"]
    anchor_x, anchor_y = spec["source_anchor"]
    if "leg_registration" in spec:
        # The upright lift source has longer shins than the master. Preserve head
        # size and register the lower section to the role's original proportions.
        waist, factor = spec["leg_registration"]
        split = waist - top
        upper = crop.crop((0, 0, crop.width, split))
        lower = crop.crop((0, split, crop.width, crop.height))
        lower = lower.resize((lower.width, round(lower.height * factor)), Image.Resampling.LANCZOS)
        crop = Image.new("RGBA", (upper.width, upper.height + lower.height))
        crop.paste(upper)
        crop.paste(lower, (0, split))
        anchor_y = waist + (anchor_y - waist) * factor
    offset = (round(PIVOT[0] + (left - anchor_x) * scale),
              round(PIVOT[1] + (top - anchor_y) * scale))
    size = (round(crop.width * scale), round(crop.height * scale))
    scaled = crop.resize(size, Image.Resampling.LANCZOS)
    box = scaled.getchannel("A").point(lambda a: 255 if a >= 16 else 0).getbbox()
    if not box or min(offset[0] + box[0], offset[1] + box[1]) < 0 or (
            offset[0] + box[2] > CELL or offset[1] + box[3] > CELL):
        raise ValueError(f"Empty or clipped pose: {spec}")
    frame = Image.new("RGBA", (CELL, CELL))
    frame.alpha_composite(scaled, offset)
    return frame


def polygon_mask(size, vertices):
    mask = Image.new("L", size)
    ImageDraw.Draw(mask).polygon([tuple(point) for point in vertices], fill=255)
    return mask


def masked(image, mask):
    part = image.copy()
    part.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    return part


def joined_part(image, seed):
    """Exclude other nearby pieces caught between the polygon and a tilted cuff."""
    alpha = image.getchannel("A")
    island = alpha.point(lambda value: 255 if value >= 8 else 0)
    if not island.getpixel(seed):
        raise ValueError(f"Part hinge outside its mask: {seed}")
    ImageDraw.floodfill(island, seed, 128)
    keep = island.point(lambda value: 255 if value == 128 else 0).filter(ImageFilter.MaxFilter(3))
    return masked(image, keep)


def fit_joint(image, start, end, target_start, target_end):
    """Map one painted linkage between new joints while retaining its thickness."""
    sx, sy = end[0] - start[0], end[1] - start[1]
    tx, ty = target_end[0] - target_start[0], target_end[1] - target_start[1]
    src_length, dst_length = math.hypot(sx, sy), math.hypot(tx, ty)
    ux, uy = sx / src_length, sy / src_length
    vx, vy = tx / dst_length, ty / dst_length
    ratio = src_length / dst_length
    a, b = ux * ratio * vx + uy * vy, ux * ratio * vy - uy * vx
    d, e = uy * ratio * vx - ux * vy, uy * ratio * vy + ux * vx
    c = start[0] - a * target_start[0] - b * target_start[1]
    f = start[1] - d * target_start[0] - e * target_start[1]
    return image.transform(image.size, Image.Transform.AFFINE, (a, b, c, d, e, f),
                           resample=Image.Resampling.BICUBIC)


def rigged_walk(path):
    rig = json.loads(path.read_text(encoding="utf-8"))
    source = read_rgba(ANIMATIONS / rig["source"])
    masks = {name: polygon_mask(source.size, polygon) for name, polygon in rig["polygons"].items()}
    parts = {name: masked(source, mask) for name, mask in masks.items()}
    removed = ImageChops.lighter(masks["near_arm"], masks["far_arm"])
    torso = masked(source, ImageChops.invert(ImageChops.lighter(removed, masks["clear_legs"])))
    pivots = rig["pivots"]
    frames = []
    for pose in rig["frames"]:
        bob = pose["body_y"]
        composite = Image.new("RGBA", source.size)
        for side in ("far", "near"):
            arm_name, boot_name = side + "_arm", side + "_boot"
            arm = parts[arm_name].rotate(pose[arm_name], center=tuple(pivots[arm_name]),
                                         resample=Image.Resampling.BICUBIC)
            if side == "far":
                composite.alpha_composite(arm, (0, bob))
            knee_x, sole_y, angle = pose[boot_name]
            hinge = pivots[boot_name]
            boot = parts[boot_name].rotate(angle, center=tuple(hinge), resample=Image.Resampling.BICUBIC)
            bottom = boot.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()[3]
            dy = sole_y - bottom
            hip = pivots[side + "_hip"]
            thigh = fit_joint(parts["thigh"], pivots["thigh"], pivots["knee"],
                              (hip[0], hip[1] + bob), (knee_x, hinge[1] + dy))
            composite.alpha_composite(thigh)
            composite.alpha_composite(boot, (knee_x - hinge[0], dy))
            if side == "far":
                composite.alpha_composite(torso, (0, bob))
            else:
                composite.alpha_composite(arm, (0, bob))
        frames.append(composite)
    return frames


def patch_hands(frames, clip_name, corrections):
    """Art-directed cutouts preserve the master's segmented graphite grippers."""
    replacement = corrections["clips"].get(clip_name)
    if not replacement:
        return
    reference = corrections["hands"][clip_name.split("-")[0]]
    master = read_rgba(ANIMATIONS / reference["image"])
    for frame_number, edits in replacement.items():
        frame = frames[int(frame_number) - 1]
        for side, edit in edits.items():
            donor = reference[side]
            hand = masked(master, polygon_mask(master.size, donor["polygon"]))
            hinge = tuple(donor["hinge"])
            hand = joined_part(hand, hinge)
            hand = hand.rotate(edit["angle"], center=hinge, resample=Image.Resampling.BICUBIC)
            erase = polygon_mask(frame.size, edit["replace_polygon"])
            frame.putalpha(ImageChops.multiply(frame.getchannel("A"), ImageChops.invert(erase)))
            tx, ty = edit["wrist"]
            connector = reference["connector"]
            rod = masked(master, polygon_mask(master.size, connector["polygon"]))
            rod = fit_joint(rod, connector["start"], connector["end"],
                            edit["arm_joint"], (tx, ty))
            frame.alpha_composite(rod)
            frame.alpha_composite(hand, (tx - hinge[0], ty - hinge[1]))


def contact(role, rows, size, backgrounds):
    label_height = 25
    row_height = size + label_height
    gutter = 5
    width = 6 * (size + gutter) - gutter
    contact_image = Image.new("RGB", (width, row_height * len(rows) * len(backgrounds)), DARK)
    draw = ImageDraw.Draw(contact_image)
    font = ImageFont.load_default(size=13)
    row_index = 0
    for action, frames in rows.items():
        for background in backgrounds:
            foreground = (239, 240, 236) if background == DARK else (39, 45, 48)
            baseline = (100, 111, 117) if background == DARK else (183, 169, 149)
            top = row_index * row_height
            draw.rectangle((0, top, width, top + row_height - 1), fill=background)
            draw.text((5, top + 4), f"{role.upper()}  /  {action}  /  {size} px",
                      font=font, fill=foreground)
            y = top + label_height
            guide_y = y + round(PIVOT[1] * size / CELL)
            draw.line((0, guide_y, width - 1, guide_y), fill=baseline)
            for index, frame in enumerate(frames):
                sprite = frame if size == CELL else frame.resize((size, size), Image.Resampling.LANCZOS)
                contact_image.paste(sprite, ((size + gutter) * index, y), sprite)
            row_index += 1
    return contact_image


def gif(frames, durations):
    painted = []
    for frame in frames:
        cell = Image.new("RGB", frame.size, LIGHT)
        cell.paste(frame, (0, 0), frame)
        painted.append(cell)
    return encoded(painted[0], "GIF", append_images=painted[1:], save_all=True,
                   duration=durations, loop=0, disposal=2, optimize=False)


def pack(check=False):
    registration = json.loads((ANIMATIONS / "registration.json").read_text(encoding="utf-8"))
    corrections = json.loads((ANIMATIONS / "hand-corrections.json").read_text(encoding="utf-8"))
    records = []
    for role in ROLES:
        rows = {}
        for action, poses in CLIPS.items():
            clip_name = f"{role}-{action}"
            clip = registration["clips"][clip_name]
            paths = [f"frames/{clip_name}/{i:02}.png" for i in range(1, len(poses) + 1)]
            if "rig" in clip:
                frames = rigged_walk(ANIMATIONS / clip["rig"])
            elif "registration" in clip:
                entries = clip["registration"]
                if len(entries) != len(poses):
                    raise ValueError(f"Wrong registration count for {clip_name}")
                names = [entry.get("source", clip["raw"]) for entry in entries]
                sources = {name: read_rgba(ANIMATIONS / name) for name in set(names)}
                frames = [registered_pose(sources[name], entry)
                          for name, entry in zip(names, entries, strict=True)]
            else:
                frames = [read_rgba(ANIMATIONS / path) for path in paths]
            patch_hands(frames, clip_name, corrections)
            if "registration" in clip or "rig" in clip:
                for path, frame in zip(paths, frames, strict=True):
                    output(ANIMATIONS / path, encoded(frame, "PNG"), check)
            sheet = Image.new("RGBA", (CELL * len(poses), CELL))
            bounds = []
            sole_offsets = []
            for index, frame in enumerate(frames):
                box = frame.getchannel("A").getbbox()
                if frame.size != (CELL, CELL) or not box:
                    raise ValueError(f"Incorrect frame at {paths[index]}")
                bounds.append(box)
                # All roles' boots occupy this band. The antenna and its glow are above it.
                sole_band_top = 175
                boot = frame.getchannel("A").crop((0, sole_band_top, CELL, CELL))
                boot_box = boot.point(lambda a: 255 if a >= 128 else 0).getbbox()
                if boot_box is None:
                    raise ValueError(f"Missing boot in {paths[index]}")
                sole_offsets.append(sole_band_top + boot_box[3] - PIVOT[1])
                sheet.paste(frame, (CELL * index, 0))
            sheet_path = f"sheets/{clip_name}.png"
            output(ANIMATIONS / sheet_path, encoded(sheet, "PNG"), check)
            gif_path = f"previews/{clip_name}.gif"
            output(ANIMATIONS / gif_path, gif(frames, PREVIEW_DELAYS[action]), check)
            raw_path = ANIMATIONS / clip["raw"]
            for reference in clip["references"]:
                if not (ANIMATIONS / reference).is_file():
                    raise ValueError(f"Missing reference {reference}")
            record = {
                "role": role.upper(), "action": action, "sheet": sheet_path,
                "frames": paths, "frame_size": [CELL, CELL], "frame_count": len(poses),
                "facing": "right", "nominal_anchor": list(PIVOT), "poses": poses,
                "selection": "physics" if action == "jump" else "loop",
                "alpha_bounds_xyxy_exclusive": bounds, "lowest_boot_offsets_px": sole_offsets,
                "contact_offsets_px": [sole_offsets[0], None, None, sole_offsets[-1]]
                if action == "jump" else sole_offsets,
                "source": clip["raw"],
                "source_sha256": sha256(raw_path), "references": clip["references"],
                "provenance": clip["provenance"], "preview": gif_path,
            }
            if action in FPS:
                record["fps"] = FPS[action]
            if "rig" in clip:
                record["rig"] = clip["rig"]
            if "registration" in clip:
                record["frame_sources"] = names
                record["raw_source_sha256"] = {name: sha256(ANIMATIONS / name) for name in sorted(set(names))}
            records.append(record)
            rows[action] = frames
        for size, backgrounds, suffix in [(CELL, (LIGHT,), "native"), (64, (LIGHT, DARK), "gameplay")]:
            sheet = contact(role, rows, size, backgrounds)
            output(ANIMATIONS / f"previews/{role}-{suffix}.png", encoded(sheet, "PNG"), check)
    manifest = {"format_version": 1, "frame_coordinates": PACK_NOTE, "facing_note": ANGLE_NOTE,
                "boot_measurement": "Exclusive lower boot edge at alpha >=128 minus nominal anchor y. "
                                    "Takeoff and landing list contact alignment; flight has null contacts.",
                "jump_triggers": {"takeoff": "accepted jump impulse", "ascent": "positive up velocity",
                                  "descent": "apex or downward velocity", "landing": "new support contact"},
                "animations": records}
    payload = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    output(ANIMATIONS / "manifest.json", payload, check)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="compare without writing files")
    args = parser.parse_args()
    pack(args.check)
    print(f"{'Checked' if args.check else 'Packed'} 9 clips, 42 frames, 9 GIFs and 6 contact sheets.")


if __name__ == "__main__":
    main()
