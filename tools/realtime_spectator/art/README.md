# Real-time spectator art

The spectator uses the three robots from the approved light direction board. Each robot has an idle, a walk and four physics-selected jump poses. Runtime images are local PNGs. The development room's transport serves its scenery and atlas files. [Direction board](animations/references/light-direction.png) · [Runtime manifest](animations/manifest.json)

## Registration and playback

All 42 frames are transparent 256 × 256 pixel cells. The right-facing three-quarter art has a common foot pivot at pixel edge `(128, 239)`, measured from the top left. At 64 CSS pixels the pivot is `(32, 59.75)`. Align it to the simulation foot point and flip the artwork around that point for leftward travel. The large neutral master files at the root have their own source-image padding.

| Clip | Atlas | Selection |
| --- | --- | --- |
| Idle | 1024 × 256, four frames | 2 fps loop |
| Walk | 1536 × 256, six frames | 8 fps loop from grounded travel |
| Jump | 1024 × 256, four frames | Accepted takeoff impulse, positive vertical velocity, apex or descent, then new support contact |

The recorded world supplies height, motion and support. The painted toe meets the pivot in all three takeoff and landing frames. A ledger of per-frame boot measurements lives in the manifest. It uses the lower exclusive edge of pixels with alpha at least 128 in the boot band. SPECTRA's walk soles align exactly. PYRA's range is −1 to +1 native pixel. FLUX's walking soles align exactly and its unmodified idle sits 3 native pixels above the pivot, or 0.75 pixel in a 64-pixel cell. The airborne boot tips clear the pivot by 23–24 pixels during ascent and 7–8 pixels during descent.

## Editing a pose

The registration table records raw image windows, source pivots, uniform scales and any waist-to-boot adjustments used to match body proportions across source sheets. The source file can change between poses within the same clip. Nearby soft alpha preserves the antenna light. A source-specific threshold removes faint gray background noise in SPECTRA's upright study. [Registration](animations/registration.json) · [Raw edit prompts and outputs](animations/generation-prompts.md)

SPECTRA's two generated walk studies repeated much of the same leg motion. Its six delivered poses articulate the original neutral robot with separate upper arms, segmented pincers, leg linkages and boots. The near boot bears weight through frames 1–3 and the far boot through frames 4–6. The JSON polygons select the original pixels and the hinge coordinates control each limb. PYRA and FLUX use edits of their six-pose walks, preserving the alternating lifted boots. FLUX's descent and landing use graphite pincers and cream forearms cut from its neutral frame. Their editable polygons and joint placements are available alongside the rig. [Walk masks and hinges](animations/spectra-walk-rig.json) · [Hand and forearm masks](animations/hand-corrections.json)

Run these commands at the repository root with its Python environment active.

```console
python tools/realtime_spectator/pack_art.py
python tools/realtime_spectator/pack_art.py --check
python -m unittest discover -s tests -p test_realtime_art.py -v
```

The packer rebuilds the registered frames, horizontal sheets, per-clip GIFs, native contact sheets, 64-pixel light/dark contact sheets and manifest. The individual imported idle PNGs are editable canonical frames. Shape, registration and source checks run offline.

## Visual review

The native sheets expose hand seams and foot contacts. The 64-pixel sheets place the same frames over light and dark colors with a line at the foot pivot. PYRA's painted fins and broad boots and FLUX's luminous orbit stay visible during flight. Some finer pincer segments merge at small display sizes, especially when FLUX swings a hand in front of its torso. The jump GIFs use illustrative preview timings. The running game selects the jump pose from simulation events.

| Robot | Native and gameplay sheets | Animated jump |
| --- | --- | --- |
| SPECTRA | [Native](animations/previews/spectra-native.png) · [64 px](animations/previews/spectra-gameplay.png) | [Preview](animations/previews/spectra-jump.gif) |
| PYRA | [Native](animations/previews/pyra-native.png) · [64 px](animations/previews/pyra-gameplay.png) | [Preview](animations/previews/pyra-jump.gif) |
| FLUX | [Native](animations/previews/flux-native.png) · [64 px](animations/previews/flux-gameplay.png) | [Preview](animations/previews/flux-jump.gif) |

## Source and rights information

The direction board, scenery and three neutral character masters come from this project's spectator PR #51 at `b2d4f250ff150f23a39ada1a780effd1b644b69a`. The idle frames and walk references come from PR #52 at `017870ff1dc942473a23d14106160bbc16d11cc1`. The import ledger records a repository path, commit, Git blob and verified local copy for each imported file. Newly drawn pose studies use the built-in ImageGen tool with those project references. The repository includes the MIT license and its copyright notice. [Original asset identities](imports.json) · [Repository license](../../../LICENSE)
