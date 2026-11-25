# FLUX Circuit Relief approval and verification

The owner selected Circuit Relief from the Round 1 directions for
[#60](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/60). Round 2 faded
ordinary scenery and raised the contrast of the directional power trace. The
owner then asked for clearer robot contact signatures and approved the four
reference scenes below on November 25, 2026.

| Raised Span fixture | SPECTRA, PYRA, FLUX columns | Circuit | Energy cell |
| --- | --- | --- | --- |
| [Idle approach](idle.png) | 1, 2, 3 | Idle | Present |
| [Powered crossing](powered-crossing.png) | 5, 7, 8 | Powered | Present |
| [Far bank](cell-collected.png) | 8, 9, 10 | Powered | Collected |
| [Cluster at the relay](cluster-at-relay.png) | 4, 4, 4 | Powered | Present |

The offline renderer matched all four approved 850 × 295 reference scenes
pixel for pixel outside the three letters. Pillow's bundled font replaces the
approval mockup's desktop font. The power trace, arrows, cell, scenery, and
badge outlines match exactly. A layout sweep covered 105,456 combinations of
columns, sampled heights, and circuit states. Every combination retained all
three contact marks.

The spectator renders the illustration from snapped robot columns, FLUX's own
height, bridge power, and energy cell status at each decision window. Teammate
positions use the original FLUX PNG's column resolution and their drawn heights
follow the terrain. The original FLUX PNGs matched the pre-integration files
byte for byte in the three Round 1 fixtures. The offline regression varies
PYRA's thermal reading, SPECTRA's shard state, and teammate kinematics while
checking that the FLUX illustration stays identical.

The offline browser check opens both FLUX views for the same sample, decodes
the illustration, and checks its layout at a 390-pixel viewport. Circuit Relief
uses static chevrons. Model attention and gameplay effects require a separate
evaluation. No provider calls were made.

## PR #64 review follow-up

The review revision adds a lamp for the sampled public exit state. Across the
four reference scenes, the lamp is the only pixel change from the original
implementation. The illustrated view also reports FLUX's sampled height and
robot columns in text, and **Enlarge image** lets viewers read the artwork at
its original size on narrow screens.
