# PR #39 Antigravity follow-up

The review of `f9d035e` is checked against reproductions, not passing historical
tests or GitHub outdated markers. No provider request or deployment is required.

| Review items | Resolution and regression evidence |
|---|---|
| Major 1–2; minor 10 | Round edits clear conflicting named treatments; smoke re-derives named rounds after an empty field. Updating the existing controls preserves selector focus. Node production-handler tests cover both paths. |
| Major 3–4 | Running settings/flags and evaluation implementation status match the delivered controls; campaign work remains separate in this PR. |
| Minor 5, 11 | Reject boolean rounds before normalization; revalidate copied settings at driver/provenance boundaries before binding. Rehashed boolean and unvalidated-copy probes are rejected. |
| Minor 6; seed nit | Accept bounded prerelease/vendor Python version labels; require actual integer commitment seeds. Round-trip and rehashed boolean-seed tests cover the cases. |
| Minor 7; standalone notice check | Validate request version, structured notice and prompt notice suffix against effective conditions. Recomputed hashes do not excuse contradictory metadata. |
| Minor 8–9 | Replay policy labels distinguish WAIT/uniform/scripted; viewer/workbench recover v1 communication labels; the quiet checker recognizes the current mock banner. |
| Remaining nits | Skip image encoding when omitted, canonicalize a direct no-image request notice, reject fast/disabled conflicts, and keep changes under Unreleased. |
| Coverage gaps | Actual intercepted HTTP across every provider/arm, retries and exhausted withheld fallback; positive message/history delivery; exact image quotes; persisted role PNGs; communication-independent uniform draws; Node round/smoke cases. |

Focused probes first reproduced boolean-round acceptance, rejected Python suffixes,
notice/version contradictions, direct image-notice mismatch and copied-settings
binding. They pass after correction. The full offline suite, Node checks, actual
Chromium interaction, dependency/build/mock checks and hosted matrix are verified
for the submitted revision; exact counts/links are recorded in the PR response.
Historical fixture files are preserved. Broader browser/security/room work remains
separately tracked.
