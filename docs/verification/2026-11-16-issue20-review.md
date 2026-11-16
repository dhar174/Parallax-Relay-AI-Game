# Issue #20 independent review and disposition

A fresh `gpt-6-astra` reviewer inspected `9ba0306..c315812`, the approved plan,
ledger and actual offline artifacts. It found no critical issue or supported-path
held-out bypass. The author graded all three findings Important for the fix pass:

| Finding | User effect | Correction and regression |
|---|---|---|
| R1: pooled Wilson intervals | Cross-room data appeared inferential despite descriptive labels | Family/split and multi-room overall summaries omit `wilson_95`; per-room cells retain it. Python regression failed before correction. |
| R2: stale fixed-room outcome copy | A different selected room appeared guaranteed to win | Offline copy identifies the original Split Span fixture and states that the unchanged script may fail in selected development rooms. UI regression failed before correction. |
| R3: incomplete browser archive validation | Malformed imports could replace the selected run | Recorded geometry, terminal loss and optional legacy aliases are checked; rejected-import regressions preserve the prior run. All nine actual Recorder definitions are covered. |

R2/R3 were initially labeled Minor by the reviewer; the author upgraded them based
on their concrete user impact. No minor findings are deferred. An additional R3
compatibility regression caught external-result v3 recordings without embedded
room identity. They now declare the supplied world's room definition without
inventing execution input identity or times. That regression also failed first.
The author verified the fixes with tests; a second review was not commissioned.

## Rulings made

- Reuse an existing locked environment in an isolated sibling worktree. This
  preserves main; the only tradeoff is local path differences, covered by checks.
- Graphical layout/accessibility/console verification remains unavailable because
  CUA failed to initialize. Native/automated integration is evidence; visual defects
  remain possible and are not claimed to be tested.
- Hosted CI was unavailable at review time. Inspect final-head six-job results
  before claiming hosted verification; platform regressions may remain until then.
- Paid-provider behavior and model-performance/generalization testing remain
  outside the authorized offline plan. There is no new empirical model-ability
  evidence, and no such claim is made.
