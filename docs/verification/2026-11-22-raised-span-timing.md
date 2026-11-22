# Raised Span offline timing and recovery · November 22, 2026

The playtests ran on Windows from merged revision `843113b` using local
fixtures. The historical delays came from a turn-based smoke run. The tests
made zero provider calls. [Historical delay source](2026-11-15-slice7-live-retry-summary.json)

## Timing sweep

Across 36 standard matches and 12 controlled airborne probes, all 48 journals
replayed successfully across 35,058 ticks. Each of the 132 windows released all
three roles on one authoritative tick. The tick journal showed no early action
commands. All 36 standard matches finished in three windows.

With the historical trace and frozen physics, one discussion round at ten
seconds per phase cut the median match from 72.9 seconds (two rounds, twenty
seconds) to 44.4 seconds. FLUX's broadcast timed out once per window, and each
commit arrived before its cutoff. At twenty seconds with one round, all
broadcasts arrived and the median match took 63.4 seconds. At five seconds
with one round, only one robot's broadcast arrived per window. In the paired
one-round, ten-second tests, continued physics advanced a median 792 ticks
between sampling and release. The controlled probe landed during discussion
under continue. Under freeze it remained airborne until release and a second
jump was blocked.

## FLUX recovery

The fixture resubmitted the prior live run's accepted commands through central
validation to reproduce its tick-480 checkpoint. FLUX was grounded at deck
height against the raised face, and SPECTRA and PYRA were already at extraction.
The local reactive controllers chose the recovery commands from their own role
observations. The historical response delays applied only to the three recovery
windows. The table records elapsed time from the first recovery broadcast
opening to completion. [Original live-run evidence](2026-11-20-realtime-demo.md#authorized-live-model-run--november-20-2026)

| Per-phase timeout | Recovery time across two runs | FLUX broadcasts delivered per run | Commit fallbacks during recovery |
| --- | --- | --- | --- |
| 10 seconds | 43.781–43.828 s | 0 of 3 | 0 |
| 20 seconds | 62.531–62.547 s | 3 of 3 | 0 |

FLUX hit the raised face without a jump on tick 142 in the setup. It jumped
from the lip at tick 481, landed on the far bank at 511, collected the energy
cell at 610, and reached team extraction at 744 in all four matches. Release
ticks were 1, 121, 241, 361, 481, 601, and 721. All 28 releases and 2,976 ticks
verified across four replays. Chromium 159 showed the collision, landing,
extraction, and the difference in public dialogue in both configurations.
The first twenty-second capture reached the browser harness's wait limit.
The capture passed after extending that wait with the game settings unchanged.

Use the ten-second reactive default for quick offline play. Use twenty seconds
when the timing comparison needs slower public dialogue. The recovery fixture
allows up to seven windows to include the four setup windows and three recovery
windows. The live profile remains capped at four windows. Full journals,
role-private feeds, and browser captures are stored locally.
