"""Contracts for the art consumed by the real-time spectator."""

import hashlib
import json
import unittest
from pathlib import Path

from PIL import Image, ImageOps


ART = Path(__file__).resolve().parents[1] / "tools" / "realtime_spectator" / "art"
ANIMATIONS = ART / "animations"
JUMP_POSES = ["takeoff", "ascent", "descent", "landing"]


class RealtimeArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ANIMATIONS / "manifest.json").read_text(encoding="utf-8"))
        cls.clips = {(clip["role"], clip["action"]): clip for clip in cls.manifest["animations"]}

    def test_role_frames_pack_exactly_and_flip_around_the_foot_pivot(self):
        expected = {(role, action) for role in ("SPECTRA", "PYRA", "FLUX")
                    for action in ("idle", "walk", "jump")}
        self.assertEqual(set(self.clips), expected)
        self.assertEqual(len(self.manifest["animations"]), len(expected))
        for (_, action), clip in self.clips.items():
            with self.subTest(sheet=clip["sheet"]), Image.open(ANIMATIONS / clip["sheet"]) as sheet:
                count = {"idle": 4, "walk": 6, "jump": 4}[action]
                self.assertEqual((sheet.format, sheet.mode, sheet.size), ("PNG", "RGBA", (256 * count, 256)))
                self.assertEqual((clip["frame_count"], len(clip["frames"])), (count, count))
                self.assertEqual((clip["facing"], clip["nominal_anchor"], clip["frame_size"]),
                                 ("right", [128, 239], [256, 256]))
                for index, path in enumerate(clip["frames"]):
                    with Image.open(ANIMATIONS / path) as frame:
                        self.assertEqual(frame.mode, "RGBA")
                        self.assertEqual(frame.size, (256, 256))
                        self.assertEqual(frame.tobytes(), sheet.crop((256 * index, 0, 256 * (index + 1), 256)).tobytes())
                        alpha = frame.getchannel("A")
                        self.assertEqual(alpha.getextrema(), (0, 255))
                        left, top, right, bottom = alpha.getbbox()
                        self.assertEqual(clip["alpha_bounds_xyxy_exclusive"][index], [left, top, right, bottom])
                        self.assertEqual(ImageOps.mirror(alpha).getbbox(), (256 - right, top, 256 - left, bottom))
                        for ground_x in (72, 120):
                            # Same registration on opposing ledge edges at 64 CSS px.
                            origin = ground_x - clip["nominal_anchor"][0] / 4
                            self.assertEqual(origin + (256 - clip["nominal_anchor"][0]) / 4, ground_x)

    def test_physics_poses_and_measured_soles_at_game_scale(self):
        for (_, action), clip in self.clips.items():
            with self.subTest(sheet=clip["sheet"]):
                measured = []
                for path in clip["frames"]:
                    with Image.open(ANIMATIONS / path) as frame:
                        boots = frame.getchannel("A").crop((0, 175, 256, 256))
                        lower = boots.point(lambda a: 255 if a >= 128 else 0).getbbox()[3] + 175
                        measured.append(lower - 239)
                self.assertEqual(clip["lowest_boot_offsets_px"], measured)
                if action == "jump":
                    self.assertEqual(clip["poses"], JUMP_POSES)
                    self.assertEqual(clip["selection"], "physics")
                    self.assertNotIn("fps", clip)
                    self.assertEqual(clip["contact_offsets_px"], [measured[0], None, None, measured[3]])
                    self.assertLess(measured[1], measured[2])
                    self.assertLess(measured[2], -2)
                else:
                    self.assertEqual(clip["contact_offsets_px"], measured)
                    self.assertEqual(clip["fps"], 2 if action == "idle" else 8)
                for value in clip["contact_offsets_px"]:
                    if value is not None:
                        # One CSS pixel of radial antialiasing/sole detail at the 64px review scale.
                        self.assertLessEqual(abs(value), 4)

    def test_edit_sources_previews_and_original_asset_identity(self):
        imports = json.loads((ART / "imports.json").read_text(encoding="utf-8"))
        for item in imports["imports"]:
            with self.subTest(source=item["local"]):
                payload = (ART / item["local"]).read_bytes()
                git_header = f"blob {len(payload)}\0".encode()
                self.assertEqual(hashlib.sha1(git_header + payload, usedforsecurity=False).hexdigest(), item["git_blob"])
        for (role, action), clip in self.clips.items():
            with self.subTest(role=role, action=action):
                raw = (ANIMATIONS / clip["source"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), clip["source_sha256"])
                for reference in clip["references"]:
                    self.assertTrue((ANIMATIONS / reference).is_file(), reference)
                with Image.open(ANIMATIONS / clip["preview"]) as preview:
                    self.assertEqual((preview.format, preview.n_frames, preview.size),
                                     ("GIF", clip["frame_count"], (256, 256)))
                    for index in range(preview.n_frames):
                        preview.seek(index)
                        self.assertGreater(preview.info["duration"], 0)
            for size in ("native", "gameplay"):
                with Image.open(ANIMATIONS / "previews" / f"{role.lower()}-{size}.png") as contact:
                    self.assertEqual(contact.format, "PNG")
                    self.assertGreater(contact.width, 6 * (60 if size == "gameplay" else 250))

    def test_walk_rig_has_alternating_support_and_real_master_hand_masks(self):
        clip = self.clips["SPECTRA", "walk"]
        rig = json.loads((ANIMATIONS / clip["rig"]).read_text(encoding="utf-8"))
        self.assertEqual([frame["support"] for frame in rig["frames"]], ["near"] * 3 + ["far"] * 3)
        self.assertGreater(rig["frames"][0]["near_boot"][0], rig["frames"][0]["far_boot"][0])
        self.assertLess(rig["frames"][3]["near_boot"][0], rig["frames"][3]["far_boot"][0])
        self.assertIn("near_arm", rig["polygons"])
        self.assertIn("far_arm", rig["polygons"])


if __name__ == "__main__":
    unittest.main()
