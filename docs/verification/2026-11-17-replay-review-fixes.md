# Replay review corrections — November 17, 2026

Independent review of PR #43 reproduced two display defects despite the earlier
passing suites. Orphan phase evidence was labeled definitely unfinished when a
nested post-resolution snapshot contradicted its replay row, or later phase/call
evidence contradicted the final checkpoint. The workbench also claimed completed
commitments after communication-only stops.

Both viewers now leave orphan resolution unknown when nested turn/terminal
evidence or later valid call/phase turns contradict the checkpoint. The workbench
asserts completed commitments only when a COMMIT phase contains sealed actions.
Native records and exports remain unchanged; historical readers are preserved.

Two new Node behavior tests failed before correction and pass afterward. Their
counterexamples cover nested turn disagreement, terminal disagreement, later phase
evidence, and a communication-only stop. The full Node application suite passed
76 tests with no skips/failures. Full Python verification passed 364 tests using
the existing locked Python 3.12 environment with Pillow 13. These are offline
checks, not qualification or source-security scan evidence. Browser regressions
and final assembled-source checks are recorded separately in the browser and
integration receipts.
