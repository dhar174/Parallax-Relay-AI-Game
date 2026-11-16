# PR #40 Antigravity follow-up

The review of `58be0fd`/`c809ed8` was investigated against reproductions. PR #40
retains its `main` base and includes the PR #39 corrections from `76fb564` through
merge `ffbee0b`. Neither PR is merged. Historical diagnostic and hosted receipts
remain evidence for their original revisions.

| Review items | Resolution and regression evidence |
|---|---|
| Major 1 | Strict summary/count/energy validation and explicit budget projection prevent outcome/assignment overwrite; adversarial extra keys and bad counters are tested. |
| Major 2; minor 15 | Validate ledger UUIDs and stop enums; neutralize CSV formula prefixes; write CSVs through fsynced temporary files/replace, retaining empty headers. Injected strings, interrupted writes and JSON readback are tested. |
| Major 3; minor 12 | Cross-check ended lifecycle, scheduled mode/policy, run IDs, stops, turns/energy, phases/replay sequence and usage/cost conservation. Contradictory or missing evidence cannot qualify for inference. Mutation tests assert specific issue codes. |
| Major 4; minor 7 | Acquire the lock before rechecking markers (including broken symlinks); immediately protect owned-lock write/close with finally. Race, contention and write-failure tests exercise ownership. |
| Minor 5, 8 | Release all phase tickets even for tasks cancelled before entry; preserve cancellation when cleanup fails. Both cancellation windows are tested. |
| Minor 6, 14 | Persist additive exact Decimal strings beside numeric estimates, use Decimal totals, disclose legacy float uncertainty and explicit partial-pricing coverage. A sub-ULP cost survives runner/analysis with zero reservation balance. All-unpriced report totals stay null. |
| Minor 9–10 | Check/trim selected credentials before markers; return actionable sanitized configuration errors, including the python -m entry point. Tests use explicit fake keys and cover exits 0/2/4/130. |
| Minor 11 | Reject nonfinite/deep ledgers, duplicate start/stop events, mismatched block IDs, unmatched receipts and reservation imbalance before complete-cohort inference. |
| Minor 13 | Compare model rosters canonically; validate experiment UUID, frozen identities, pilot record and planned exposure. Tests cover reordered rosters, changed model rejection, malformed pilot/frozen data and rerun linkage. |
| Minor 15, inherited controls | PR #39 checks standalone prompt notice suffixes as well as structured notices/version; HTTP tests cover retries, exhausted withheld fallback, positive message delivery and exact image reservation differences. |
| Nits and coverage | Reject boolean caps/intervals and ignored round settings; reject repeated deterministic-only diagnostics; validate statistical bounds and add equal-weight launched bounds; clear stale diagnostics and remove duplicate state assignment. Test all 11 codes and caller non-mutation, nondegenerate bootstrap, Node nonfinite splits and zero/unavailable rendering. Repair README/status/verification prose. |

Terminal engine outcomes and execution status remain separate: engine victory
followed by local/internal failure or cancellation is valid evidence, while a
victory stop without an engine win and win/turn-limit contradictions are rejected.
Partial per-role prices remain useful call evidence; an unknown overall total is
not converted into a complete priced total.

Local Python 3.12.14 verification passed **325 tests in 52.296 seconds**. Node 24
passed **57 tests**, zero failures/skips. Dependency consistency, compilation,
normal/fast mock victories (7 turns, 63/42 calls, 5 energy, scores 100), workbench
build/syntax and whitespace checks passed. Chromium 156 exercised selectors,
round-edit/smoke recovery and keyboard focus, a native no-images companion run,
three spectator PNGs, unscored turn-limit outcome and desktop/mobile overflow with
no runtime exceptions. The 15 current documentation files had 134 valid local
links/anchors before this evidence file was added.

A fresh `register` → `run --offline` → `analyze` CLI roundtrip exited 0 for all
three commands: 15/15 artifact-complete trials, 216 calls, zero call/dollar
reservation balances and null unpriced total; JSON and all three CSV row-count
readbacks matched. It is a dirty-source diagnostic with intentional turn limits.

The submitted revision's hosted matrix is reported with its actual receipts in
the PR response. All verification is offline or uses
intercepted HTTP/fake agents; no real provider request, paid run or deployment was
performed. This does not close held-out room, general browser or security work.

## Re-review follow-up

The re-review of `2f81aeb` found a CSV readback failure on CPython 3.11.2 that
newer CI patch releases did not reproduce. An isolated interpreter was built from
the official 3.11.2 source with locked dependencies. Executing the old revision's
write_report reproduced `Report readback failed`; the same input passed with
always-quoted CSV fields. No global Python installation was changed.

Additional corrections reject mixed cost availability and unpriced model trials,
require priced quotes, flag null-result/native-result disagreements without
erasing known failures, validate block reservation/release IDs and ordering, and
continue checking later calls after malformed usage. Legacy stop uncertainty
includes the final receipt's ULP. Negative monetary zero normalizes to zero;
formula detection covers Unicode whitespace; count summaries reject booleans;
JSON temporary files are cleaned on failure and a missing owned lock does not
mask another error. The controls re-review fixes are integrated from `972dc8c`.

Regression mutations cover the remaining artifact/receipt/accounting issue codes,
broken lock symlinks, invalid-key CLI preflight, cancellation inside client close,
pilot validation branches, priced zero versus null totals, nested JSON CSV cells,
atomic JSON failure and final-receipt rounding. Final full-suite and hosted
receipts are recorded in the PR response for the submitted revision.

Local final verification passed **337 tests on CPython 3.11.2** (58.387 seconds)
and **337 tests on CPython 3.12.14** (54.474 seconds). Node 24 passed **58 tests**
with zero failures/skips. Both environments passed dependency consistency; Python
compilation, workbench build/syntax, expected normal/fast mocks and whitespace
checks passed. The old CSV implementation and fixed implementation were exercised
on the same 3.11.2 interpreter/input, independently of the newer hosted matrix.
