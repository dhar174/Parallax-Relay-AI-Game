# Campaign preparation review fixes — November 17, 2026

## Scope

An independent review of PR #46 (`ba62cda..cfb198e`) found that ordinary JSON
parsing silently accepted duplicate object keys before hashing preparation inputs
and artifacts. A first-wins reader could display a different limit from the
last-wins Python parser even though the candidate check succeeded. The checked
frozen Q artifacts were duplicate-free; this finding did not demonstrate a
bypass of their native execution caps. The source-record schema-version check
also accepted JSON `true` and `1.0` as `1`.

Preparation now rejects duplicate object keys at any depth when reading the source
record, smoke profile, candidate specs, receipt and written-file readback. It
requires an integer source-record schema version. Candidate documentation permits
registration offline for concrete review while retaining separate Q approval before
live execution. The native campaign registration/parser is an inherited separate
boundary and is not changed here. No roster, prices, scenario calculation, Q/P/C
limits or provider behavior changed.

## Checks

Checks ran offline from the `cfb198e` preparation branch with the repair applied,
using `/workspace/scratch/parallax-assurance-locked/bin/python` and without
changing that environment. Temporary files and compilation caches were outside the
checkout. No provider calls or live campaigns were made.

- Focused regression tests before the fix: **4 tests, 7 expected failing subcases**,
  exit 1. The failures were source, profile, spec, receipt and write-readback
  duplicate keys, plus boolean and float source schema versions; each reported
  `ValueError not raised`.
- The same focused regressions after the fix: **4 tests in 4.334s, OK**, exit 0.
- `python -m unittest discover -s tests -v`: **379 tests in 151.759s, OK**, exit 0.
- `python -m pip check`: `No broken requirements found.`, exit 0.
- `python scripts/check_mock_runs.py`: normal and fast victories after 7 turns,
  63 and 42 calls respectively, 5 energy and every score 100; exit 0.
- `compileall` for `parallax_relay`, `tests`, `scripts`, and `site` with a
  temporary bytecode cache: all four returned `True`; exit 0.

The existing preparation tests in the full suite also check the unchanged selected
local guards: Q $0.65 per match and $9.75 across 15 matches with at most 432
provider attempts; P $9.85/$2,216.25 and C $9.85/$26,595.00. These are local
estimates, not provider invoice ceilings. P and C remain separately gated and no
spending authorization follows from generating or registering candidates.

The tracked fix changes source identity. Rebuild and check the candidate receipt
and create a fresh Q registration at the final clean integrated revision before
any authorized Q execution. Preserve the prior registration and do not erase any
one-shot markers. Actual model/arm compatibility, quota, usage and invoices remain
unverified until the authorized Q is executed and its evidence is reviewed. This
work is not the unavailable formal Standard source/privacy scan.
