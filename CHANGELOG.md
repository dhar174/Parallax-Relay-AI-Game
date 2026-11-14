# Changelog

## Unreleased

- Check committed CI diffs, isolate caches/cancellation, and hash-check pip bootstrap
  wheels in runner temporary environments without persisting checkout credentials.
- Harden mock-checker encoding, environment isolation, strict result/artifact checks,
  cleanup diagnostics, and real subprocess coverage.
- Fix launcher parent-file diagnostics and consistent LF JSONL appends; extend
  symlink/portability regressions and reconcile current documentation status.
- Add a complete hashed development dependency lock, retaining compatibility
  ranges and historical pins, with a documented refresh procedure.
- Add a six-job offline CI matrix and a reusable normal/fast mock outcome checker,
  with focused failure tests and explicit Python/platform support policy.
- Correct the legacy demo's Windows parent-file error classification; read UTF-8
  recording artifacts explicitly in cross-platform tests without relaxing checks.
- Preserve the last resolved checkpoint on recording/callback failure; recover
  independent atomic artifacts before raising a sanitized partial-result exception.
- Bound finalization to two passes and CLI client shutdown to a five-second
  cooperative timeout; preserve primary failures and cancellation.
- Disable only the CLI scripted mock's effective dollar cap, preserving call/turn
  limits and live/programmatic guards; record requested versus effective settings.
- Handle invalid UTF-8 TOML as a safe configuration error with CLI exit 2.
- Enforce canonical non-MOVE parameters in the engine without model retries.
- Reject existing legacy-demo destinations, sanitize local CLI I/O errors, and
  create a unique ignored run directory when --out is omitted.
- Rework onboarding and add running, architecture, contributor, and coding-agent guides.
- Add a research-oriented roadmap and an evidence-backed repository review.
- Clarify provider verification limits, non-MOVE parameters, and legacy output behavior.
- Preserve historical milestone evidence alongside dated implementation checks.

## Milestone 2

- Added concurrent public broadcasts, optional negotiation and sealed commitments.
- Added OpenAI Responses, Claude Messages and Gemini generateContent REST adapters.
- Added model/env configuration, strict response contracts and bounded private memory.
- Added retries, timeout handling, safe fallbacks, hard request limits and optional
  estimated-cost reservations with unknown-usage accounting.
- Closed exact-heat leakage through public text and removed static item-coordinate hints.
- Added incremental match/call logs and a text-safe offline spectator replay.
- Added explicit mock/live/check launcher modes and a local environment template.
- Preserved the starter's deterministic three-role engine and known seven-turn solution.
- Added tests for privacy, concurrency, wire formats, failure recovery and CLI behavior.

Not added: full platformer physics, 2/4-player support, playable ECHO, additional
providers, stronger competing-goal level design, a live web UI or measured LLM results.
