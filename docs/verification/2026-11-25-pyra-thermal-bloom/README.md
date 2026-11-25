# PYRA Thermal Bloom approval and verification

The owner selected Thermal Bloom (direction A) for
[#61](https://github.com/dhar174/Parallax-Relay-AI-Game/issues/61) and approved
the refined design on November 25, 2026. Round 2 softened the scenery and
enlarged the motor's halo and meter at high heat.

| Approved Raised Span frame | Heat | SPECTRA, PYRA, FLUX columns |
| --- | --- | --- |
| [Before venting](threshold.png) | 4 | 2, 4, 4 |
| [After one vent](cooled.png) | 1 | 2, 4, 4 |
| [After rerouting](rising.png) | 3 | 2, 4, 4 |
| [Team crossing](crossing.png) | 3 | 6, 7, 9 |

The renderer matched all four approved 850 × 295 PNGs pixel for pixel. The
before and after frames use the same positions and scenery. In a fixed crop
around the motor, 1,871 pixels exceed grayscale intensity 145 at heat 4,
compared with 187 at heat 1. The meter also drops from four filled segments to
one. A layout sweep retained all three contact marks across 26,364
combinations of columns and sampled PYRA heights.

The spectator renders the illustration from the sampled motor heat, public
bridge state, PYRA's height, and the snapped columns from the original
schematic. Teammate heights follow the terrain. The regression verifies that
PYRA's view is identical when the other roles' private item states and finer
positions change. **PYRA · Original thermal feed** opens the exact PNG used by
the player.

The browser test switches between the original and illustrated feeds for the
same window at a 390-pixel viewport. The session test executes a legal vent
and checks that both sampled windows retain their respective heat readings.
These checks used offline development-room fixtures.

## PR #64 review follow-up

The review revision adds a lamp for the sampled public exit state. Across the
four approved scenes, the lamp is the only pixel change. The illustrated view
also reports the sampled heat, PYRA's height and the robot columns in text.
**Enlarge image** lets viewers inspect the heat meter and badges at the
original image size on narrow screens.
