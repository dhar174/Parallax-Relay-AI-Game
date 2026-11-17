# Completion integration verification — November 16, 2026

The reviewable execution stack is frozen at
`9b3b6b570c9cff4ed66f2e1fe4b36e0c7ba830f8`, with a clean worktree and the
hashed Python environment (CPython 3.12.14, Pillow 13.0.0). This document is written
in the separate documentation worktree so that recording evidence does not change
the registered execution identity. No PR has been merged by this work.

## Review units

| PR | Deliverable | Base |
|---|---|---|
| [#43](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/43) | Final/partial replay inspection and workbench parity | main |
| [#44](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/44) | Real-browser harness, native fixtures, CI and evidence | #43 |
| [#45](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/45) | Pillow 13.x minimum and hash-lock remediation | #44 |
| [#46](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/46) | Campaign preparation, type-faithful receipts, safe Git environment and pricing scenarios | #45 |
| [#47](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/47) | Dependency/license evidence and confined, portable collector | #46 |
| [#42](https://github.com/dhar174/Parallax-Relay-AI-Game/pull/42) | Approved plan, current-status reconciliation, assurance blockers and this handoff | main, independent |

All remain reviewable deliverables; issue closure requires accepted merges and the
individual evidence gates. Main's historical fixtures and requirements-tested.txt
are unchanged. No game provider requests, paid campaign, deployment or issue closure
occurred during this implementation.

## Actual verification

- Final combined local Python suite: **382 tests passed**, 120.741 seconds.
- Application Node suite: **74 passed**; real Chromium harness: **22 passed**.
  Those local checks exercised the identical game/workbench/browser runtime before
  the final inventory-only portability correction. The final hosted run below
  independently exercises the complete final revision.
- Dependency consistency, compilation, JS syntax/build and whitespace passed.
  Normal/fast mocks won in seven turns, with 63/42 calls, five energy and every
  score 100. All nine room certificates passed.
- [Final hosted workflow 43963180959](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/43963180959)
  passed **all seven jobs** on head `9b3b6b5`. Actual logs were inspected: each of
  the six Python jobs passed 382 tests; locked Linux/Python 3.12 passed 74 Node
  tests; the separate Chromium job passed 22 tests, with zero browser skips/failures.
  Python coverage includes Linux 3.11–3.13, Windows/macOS 3.12, and independent
  compatibility-range resolution. The mock assertions passed in all six jobs.

Independent scoped reviews produced reproduced corrections: missing replay rows
must not imply unresolved actions; arbitrary phase metadata must remain renderable;
fallback actions retain role-specific reasons; browser assertions must bind exact
rows/images to their actual round; retries and completed-but-unresolved commits
need native fixtures; preparation must reject numeric type drift and exclude
provider values from Git probes; license collection must reject metadata escapes
and retain unavailable evidence. The final browser harness includes mutations that
demonstrate the former false passes and their rejection.

The earlier [workflow 43960834905](https://github.com/dhar174/Parallax-Relay-AI-Game/actions/runs/43960834905)
failed its Windows inventory tests at `2ac6df1` while the other six jobs passed.
The correction preserves raw notice bytes/hashes, uses portable fixtures, and
emits ASCII-safe JSON that round-trips Unicode license text. The successful final
workflow supersedes that failure; the failure is not erased.

## Fresh offline campaign evidence

At final source `9b3b6b5`, the existing protocol-2 development diagnostic was
registered, executed with `--offline`, and analyzed. All three commands exited 0.
It produced **45/45 launched and available trial artifacts, 648 attempts, zero
anomalies, and zero call/dollar reservation balances**. All 45 trials intentionally
stopped nonterminal at two turns. They are known operational nonsuccesses under
the reporting definition, not successful model matches. The diagnostic is not a
pilot, confirmation, benchmark or communication/generalization result.

Execution took 8.404 seconds locally. Its 720 native files occupied 8,773,476 bytes.
Full spectator artifacts remain private under ignored runs/. Reports retain all
denominators and unpriced monetary totals remain distinct from zero reservation
balances. A complete earlier diagnostic at `2ac6df1` is retained separately, not
pooled as an independent experiment or substituted for a failed trial.

The selected live Q registration was then created and checksummed without provider
requests. **It has not been executed or funded.** Its frozen hashes, limits,
operational planning and exact proposed command are in the
[qualification approval brief](2026-11-16-qualification-approval.md).

## Gates that remain open

Q/P/C each still require separate spending approval. #9 remains open pending
eligible live evaluation/reporting. #25/#26/#12 await accepted replay/browser
delivery. #24 remains open for unresolved bundled-tool advisory applicability;
neither npm's zero lock matches nor the Pillow fix is blanket clearance. The
[security prerequisite receipt](2026-11-16-security-preflight.md) records why the
Standard scan and additional formal static triage cannot proceed with the current
required resources. #23/#11 and tracker #2 remain open. Anthropic stays
live-unverified, with #15 not planned. Site release and model/modality expansion
remain separate.
