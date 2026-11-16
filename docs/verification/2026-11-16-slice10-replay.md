# Replay inspection verification — 2026-11-16

Scope: offline work on base `4e0851b`, using synthetic/scripted recordings. No
provider requests, deployment, or historical fixture changes were made.

The recorder recovery test first failed because the HTML payload lacked completed
phases and the final snapshot. Focused browser-module tests also reproduced the
missing final/unfinished navigation, unsafe image reference, and missing-field
failures. These tests passed after the changes. A further focused test failed on
unlabelled stop reasons and blank missing-field panels, then passed after each fix.

- Full Python suite: 364 tests passed (69.656 s), before the final UI-only copy
  and layout adjustments; a repeat against the final tree was started separately.
- Built the workbench and ran the Node suite against the final UI: 66 tests passed.
- `compileall`, JavaScript syntax checks, both scripted mock checks, and the nine
  room certificates passed. Normal/fast mock runs produced 63/42 calls, seven
  turns, five energy and scores of 100.
- Existing finalization recovery tests exercised independent artifact failures;
  the historical schema-2 fixture and native schema-3 import/export paths remain
  covered by the offline suites. Browser layout and accessibility need the separate
  browser harness; Node's DOM substitutes do not establish those properties.

This is local functional evidence, not a claim of model ability or live provider
compatibility. Full spectator artifacts and raw test logs are not included here.
