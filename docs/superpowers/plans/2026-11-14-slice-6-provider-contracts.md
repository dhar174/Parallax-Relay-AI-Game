# Slice 6 provider-contract implementation plan

Approved November 14, 2026. Source: issue #13 and the approved conversation plan.
Use native implementation with TDD and one fresh whole-branch review.

**Goal:** independently verify the current OpenAI Responses, Anthropic Messages
and Gemini Developer API generateContent paths, correct evidenced mismatches, and
document requirements for compatible model selection. Defer the named shortlist.

## Constraints and interfaces

- Branch from updated main; slice 5/PR #31 is not a prerequisite or merge request.
- Preserve existing HTTPAgent/ModelReply/Usage/ProviderError interfaces, config,
  schemas, game rules, phase/call limits, cancellation and owned-client cleanup.
- Keep Anthropic 2026-10-21 and Gemini responseMimeType/responseJsonSchema when
  official evidence corroborates them. No SDK dependencies or alternate APIs.
- Use official documentation plus immutable SDK source, not self-derived mocks.
- No credentials, paid requests, named defaults/shortlist, or live-support claims.
- Preserve historical fixtures/dependencies/evidence; leave parent #8 and #14–#16 open.

## Tasks

Historical pre-execution snapshot: the unchecked boxes below preserve the original
planning state, rather than current unfinished work. The dated slice-6 entries in
[Verification](../../VERIFICATION.md) and the delivery PR record implementation,
review and hosted-CI results. Later explicit merge authorization supersedes the
original instruction to leave merging for a subsequent request.

- [ ] Pin/retrieve source evidence; record dated endpoint/auth/image/schema/limits,
  completion/refusal/truncation/usage/error references and local-policy boundaries.
- [ ] Reproduce gaps first: OpenAI failed envelopes, filtering, unfinished messages,
  commentary; malformed additive counts; inclusive Anthropic thinking telemetry.
- [ ] Implement minimal corrections; expand all-provider/all-phase intercepted
  tests independently, including known/unknown usage and real Budget/driver/Recorder.
- [ ] Update API/running/protocol/review/roadmap/changelog and dated verification;
  specify model-selection requirements without selecting model IDs.
- [ ] Run focused/full unittests, pip check, compileall, both real mock CLIs and the
  reusable checker; inspect exact changes, links, fixtures and dependencies.
- [ ] Obtain one fresh independent review; fix significant findings with regressions;
  commit/push/open one PR (Closes #13; refs #8/#2), inspect all six final-head CI jobs.
  Leave merging for explicit instruction and #13 open until merge.

## Review focus

Incomplete or failed output must not become an action; final-text extraction must
exclude intermediate/thought blocks while retaining legacy labels. Invalid token
components must not release cost estimates incorrectly. Error code/body/credential
sentinels must not reach public exceptions or artifacts. Contradictory provider
guidance must be resolved by the correct API/SDK path, with unresolved model limits
disclosed. New behavior must preserve driver cancellation, bounds and offline mocks.
