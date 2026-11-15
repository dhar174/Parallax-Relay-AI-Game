# Provider contract references

The adapters in `parallax_relay/providers.py` use direct REST calls. This document
separates implementation choices, source checks, and live evidence. No credentialed
provider match has been verified for this repository.

## Independent contract audit — November 14, 2026

Issue #13 checks the existing non-streaming direct-HTTP paths. Official REST guides
and official SDK source were read independently of the serializers and synthetic
envelopes. The SDK revisions below were retrieved successfully, pinned by commit,
and inspected as source; none was installed or executed. Documentation retrieval
used official sites and raw official GitHub files, not credentialed inference.

### Sources and immutable corroboration

| Provider | Official REST/guides | Pinned SDK evidence |
|---|---|---|
| OpenAI | [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create.md), [structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs.md), [vision](https://developers.openai.com/api/docs/guides/images-vision) | `openai-python` at `3dae6090cc31cc64a437fe0bcee740b6d81ed2cc`: [response/error states](https://github.com/openai/openai-python/blob/3dae6090cc31cc64a437fe0bcee740b6d81ed2cc/src/openai/types/responses/response_error.py), [message status/phase](https://github.com/openai/openai-python/blob/3dae6090cc31cc64a437fe0bcee740b6d81ed2cc/src/openai/types/responses/response_output_message.py), [usage](https://github.com/openai/openai-python/blob/3dae6090cc31cc64a437fe0bcee740b6d81ed2cc/src/openai/types/responses/response_usage.py), [HTTP retry classification](https://github.com/openai/openai-python/blob/3dae6090cc31cc64a437fe0bcee740b6d81ed2cc/src/openai/_base_client.py) |
| Anthropic | [Messages](https://platform.claude.com/docs/en/api/messages), [vision](https://platform.claude.com/docs/en/build-with-claude/vision), [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [cache accounting](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [errors](https://platform.claude.com/docs/en/api/errors) | `anthropic-sdk-python` at `5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9`: [version constant](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/_constants.py), [JSON output format](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/types/json_output_format_param.py), [usage](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/types/usage.py), [thinking breakdown](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/types/output_tokens_details.py), [retry classification](https://github.com/anthropics/anthropic-sdk-python/blob/5139cf2e7d07aa618a6c30b7e0c712f10ccb5ad9/src/anthropic/_base_client.py) |
| Gemini | [generateContent REST reference](https://ai.google.dev/api/generate-content), [image inputs](https://aistudio.google.com/docs/image-understanding), [structured-output guidance](https://aistudio.google.com/docs/structured-output), [Interactions migration](https://aistudio.google.com/docs/migrate-to-interactions) | `python-genai` at `a3d04bd5edc0e131267425506b025576de2d0242`: [request converters](https://github.com/googleapis/python-genai/blob/a3d04bd5edc0e131267425506b025576de2d0242/google/genai/models.py), [schema/config and usage definitions](https://github.com/googleapis/python-genai/blob/a3d04bd5edc0e131267425506b025576de2d0242/google/genai/types.py) |

### Request contracts retained

| Provider | Endpoint/authentication and image | Structured format and output bound |
|---|---|---|
| OpenAI | `POST https://api.openai.com/v1/responses`; bearer authorization; `input_image` with PNG data URI and `detail=high`, alongside `input_text` | `text.format={type:json_schema,name,schema,strict:true}`, `max_output_tokens`, `store=false`; fresh input/instructions, no server conversation |
| Anthropic | `POST https://api.anthropic.com/v1/messages`; `x-api-key`, `anthropic-version: 2026-10-21`; image `source={type:base64,media_type:image/png,data}` alongside text | `output_config.format={type:json_schema,schema}`, `max_tokens`; no beta header or sampling controls added |
| Gemini Developer API | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`; `x-goog-api-key`; `inlineData={mimeType:image/png,data}` alongside text | `generationConfig` with `responseMimeType=application/json`, `responseJsonSchema`, `maxOutputTokens`, `candidateCount=1`; `systemInstruction` remains separate |

All phases use a small schema: object/properties/required/additionalProperties,
integer and string types, descriptions, and a string enum. Every object forbids
extra keys and requires all its properties. The commitment adds one nested action
object. OpenAI's documented strict subset requires these object constraints;
Anthropic documents JSON Schema limitations; Google's pinned `GenerateContentConfig`
explicitly lists these structural keywords for `response_json_schema`. Local
Pydantic parsing still enforces turn/type/length bounds, and the engine enforces
game legality. No unsupported rich schema features or case-insensitive action
coercion were added.

**Gemini format decision:** the REST reference lists newer `responseFormat` fields,
but its rendered `responseJsonSchema` description is circular. The independently
checked `_GenerateContentConfig_to_mldev` converter emits `responseJsonSchema`, and
its config type describes the JSON Schema subset. The newer structured-output guide
demonstrates `client.interactions.create` and `response_format`, a distinct API.
Retain this supported generateContent shape; do not mechanically replace it with
Interactions or Vertex fields. No fallback to another API/model is attempted.

### Response normalization and local policy

| Provider | Usable output | Refusal/filtering | Other stopping paths |
|---|---|---|---|
| OpenAI | Completed top-level response and completed final/legacy unlabelled message output; commentary and reasoning are excluded | Refusal content or `incomplete_details.reason=content_filter` becomes `refusal`, preserving available usage | Explicitly incomplete/in-progress message output stays `incomplete`; failed/non-null-error envelopes raise sanitized `response_failed` |
| Anthropic | Text blocks with `stop_reason=end_turn`; thinking blocks excluded | `stop_reason=refusal` | `max_tokens`, `tool_use`, `pause_turn`, and other stops are `incomplete`; no tool/continuation loop is implemented |
| Gemini | Non-thought text parts from the single requested candidate with `finishReason=STOP` | Prompt `blockReason`, or candidate SAFETY/RECITATION/BLOCKLIST/PROHIBITED_CONTENT/SPII/IMAGE_SAFETY | `MAX_TOKENS`, missing candidate without blocking, and other finishes are `incomplete`; no automatic continuation |

The OpenAI SDK explicitly distinguishes message status and commentary/final-answer
phase. Older envelopes lacking these optional-to-this-adapter labels remain
readable. Failed response error codes `server_error` and `rate_limit_exceeded` are
retryable locally; other/unknown codes are fatal. Raw error codes/messages are not
copied into public errors or artifacts. A failed envelope raised as `ProviderError`
does not carry usage through `ModelReply`; its attempt therefore keeps the estimate
and records unknown usage, rather than claiming an exact charge.

Explicit OpenAI failure/error signals are classified before usage extraction.
Malformed error objects or non-string codes remain fatal `response_failed` with
unknown cause, rather than becoming retryable shape errors. Optional response
objects/collections may be missing or null; wrong-type values (including falsy
strings, booleans, numbers, lists in object fields and objects in list fields)
raise sanitized `invalid_provider_response`. Content-filter and prompt-block
signals take precedence over absent output; Gemini prompt blocking also overrides
a contradictory successful candidate. All providers return empty public text on
refusal while retaining available usage, including for direct `HTTPAgent` callers.

The adapter's HTTP policy retries 408/409/429 and 5xx; request/authentication errors
and redirects are fatal, with known OpenAI `insufficient_quota` and
`billing_hard_limit_reached` overriding 429 retries. OpenAI/Anthropic SDK retry
classifications corroborate these status classes. Applying them to Gemini is a
bounded local policy, not a promise that every RESOURCE_EXHAUSTED error is transient.
Timeout/transport and malformed successful envelopes are retryable. Corrupt
compressed successful responses become retryable `invalid_provider_response`;
deeply nested JSON cannot escape as an internal driver error. Oversized successful
responses are fatal. Error-body reads stop at the same limit and retain the known
HTTP status policy even for oversized proxy pages or corrupt compression; such a
body supplies no reliable quota detail. Only complete parsed errors establish the
quota override. Finite numeric `Retry-After` is clamped to 0–30 seconds; unsupported
values (including HTTP dates, NaN and infinities) use the existing backoff, not an
unbounded wait. The same finite check applies to programmatic `ProviderError`.
There are no HTTP-layer
automatic retries; the driver owns the attempt cap and whole-phase reservations.
Redirects never resend credentials. The response-body ceiling remains 262,144 bytes.

### Usage and unknowns

| Provider | Normalized totals | Breakdown metadata |
|---|---|---|
| OpenAI | Use reported `input_tokens` and `output_tokens` directly | Cache reads and reasoning tokens are subsets; do not add them again |
| Anthropic | Input = uncached `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`; output = reported inclusive `output_tokens` | Retain cache reads and `output_tokens_details.thinking_tokens`; thinking is not added to output again |
| Gemini | Input = `promptTokenCount` (already includes cached content); output = `candidatesTokenCount` + `thoughtsTokenCount` | Retain cached-content and thought counts; do not reconstruct missing counts from `totalTokenCount` |

Only nonnegative integer counters count as reported tokens; booleans, strings,
negative values and fractional numbers do not. Missing/null/invalid core totals
stay null. Omitted optional additive cache/thought counters retain the adapter's
legacy zero-contribution policy; this is a local normalization convention, not a
universal billing guarantee. Explicit null or malformed additive counters now make
the affected aggregate null. Valid independent totals remain available. Integer
breakdown metadata retains its existing zero fallback when not usable; that zero
alone does not establish complete usage. `unknown_usage_calls` and null aggregates
identify incomplete accounting, and the budget retains the reserved estimate.
The estimate does not implement cache tiers, hidden service charges or invoices.

Anthropic's pinned `Usage` type permits explicit null cache-read/cache-creation
counts. Null does not prove zero caching; the conservative unknown-aggregate policy
is intentional. Under #15, separately authorized live smoke evidence must record
whether inactive caching yields omitted, zero or null fields, the resulting
`unknown_usage_calls`, and retained estimated cost. Repeated nulls can retain the
quote on every call; do not relabel those estimates as known billed cost or change
null to zero merely to make the guard more permissive. This review made no paid run.

### Independent offline coverage

[Contract tests](../tests/test_provider_contracts.py) use hand-specified envelopes
and request expectations derived from the references above. Tests do not download
sources, import SDKs, resolve credentials or send provider traffic.

| Test group | Contract evidence exercised |
|---|---|
| `test_all_phases_use_the_documented_request_contract` | Nine provider/phase combinations: endpoint/auth, real role PNG, format/schema subset, token bounds, no tools/history/alternate fields |
| `test_documented_stops_and_legacy_openai_messages` plus OpenAI response-state tests | Completion/refusal/truncation, explicit unfinished messages, commentary/reasoning exclusion, legacy labels, failed response classification |
| Usage-total/invalid-counter/missing-core tests | Source-backed cache/reasoning arithmetic, known/partial/invalid values, no double-counting |
| `test_unknown_aggregates_retain_real_budget_reservations` | Real Budget settlement retains estimates, counts attempts/unknowns, and releases reservations |
| HTTP/transport, malformed-envelope, and stream tests | Safe bounded status policy, timeouts/network failures, redirects, invalid JSON, size ceiling, response cleanup |
| [Review regressions](../tests/test_provider_review.py) | Malformed failure/telemetry precedence, null versus wrong-type containers, prompt blocking, finite delays, corrupt compression/deep JSON, bounded HTTP error bodies and client ownership |
| `test_failed_responses_have_bounded_driver_retries_and_safe_artifacts` | Real driver/Recorder: transient retries stay bounded; fatal failure stops before resolution; sentinel text absent from JSON/JSONL/HTML |

Existing provider, protocol, budget, cancellation, cleanup, recovery and intercepted
three-provider integration tests remain required. Synthetic success establishes
local contract handling, not remote model acceptance.

### Selecting a compatible model

No model shortlist or default ID is supplied. Before a separately authorized smoke
test, consult the exact model's official documentation and confirm:

1. The account can access that bare ID on this exact endpoint/API version; it accepts
   PNG input and the selected structured-output/schema mode together.
2. Image size/resolution, context window and output-token bounds accommodate the
   role PNG, rules, bounded history, schema and complete reply. Check reasoning and
   default thinking behavior; visible JSON may be truncated despite short answers.
3. The configured output limit is valid for that model. OpenAI `max_output_tokens`
   includes reasoning; Anthropic `max_tokens` bounds generated output; Gemini's
   documented candidate bound/default varies by model. Do not assume the repository
   default of 2,048 or its accepted range of 256–16,384 guarantees completion.
4. Omitted sampling controls are acceptable for that model; no temperature/seed or
   deterministic remote behavior is implied. Record any alias/revision limitation.
5. Prices and per-run/campaign controls are chosen deliberately. Local `--check`
   validates configuration/credential presence only, not capability or account access.

Image/schema combinations, model-specific minima/maxima, backend revisions, access,
retention and billing remain unverified until checked for the selected model and
account. Never raise limits, select a replacement model, or switch APIs automatically
to make a failed smoke run pass. #14–#16 own bounded live evidence; parent #8 stays
open. This audit neither uses credentials nor authorizes spend.

## Historical reference check: November 13, 2026

The following source check is preserved as historical evidence. Official-documentation
and official-SDK excerpts were retrieved through Context7. The November 14 audit
above adds immutable references, response/usage corrections, and independent tests.
Neither check establishes account/model acceptance or billing accuracy. Links can
change; recheck them before modifying an adapter or choosing models.

| Provider | Implemented contract | Evidence and remaining limit |
|---|---|---|
| OpenAI | Responses, PNG data URI, `text.format` JSON Schema with `strict=true`, `store=false` | Official Responses migration guide supports `text.format`; image references support data URIs. No credentialed request executed. |
| Anthropic | Messages, base64 PNG, `output_config.format`, version `2026-10-21` | Official Python SDK constant and typed output format support the header and schema shape. No credentialed request executed. |
| Gemini | v1beta generateContent, inline PNG, `generationConfig.responseJsonSchema`, JSON MIME type | Official GenerationConfig reference lists the schema/MIME fields and candidate/token limits. Newer format guidance exists; model compatibility is unverified. |

## OpenAI

- [Responses create](https://developers.openai.com/api/reference/resources/responses/methods/create)
- [Responses migration and structured-output example](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Image inputs](https://developers.openai.com/api/docs/guides/images-vision)

The adapter sends a fresh request to `https://api.openai.com/v1/responses` with
instructions, input text and PNG, `max_output_tokens`, `store=false`, and strict
schema format. It extracts message output text and handles refusal/incomplete status
separately. It does not reuse conversation state or previous response IDs.

`store=false` is a request setting, not a blanket statement about every provider
retention policy. Output token accounting uses reported output tokens, which already
include reasoning tokens; cached/reasoning counts are retained as metadata.

## Anthropic Claude

The three `blob/main` SDK links below preserve the original November 13 reference
list. They are mutable historical pointers, not immutable evidence for the current
audit; use the pinned SDK evidence table above for the dated contract conclusions.

- [Messages](https://platform.claude.com/docs/en/api/messages)
- [Vision](https://platform.claude.com/docs/en/build-with-claude/vision)
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [API versioning](https://platform.claude.com/docs/en/api/versioning)
- [Official SDK version constant](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/_constants.py)
- [Official SDK structured-output type](https://github.com/anthropics/anthropic-sdk-python/blob/main/src/anthropic/types/json_output_format_param.py)
- [Official SDK migration notes](https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md)

The adapter calls `https://api.anthropic.com/v1/messages`, supplies system rules,
base64 image and text, `max_tokens`, and `output_config.format`. It sends
`anthropic-version: 2026-10-21`; the checked SDK source defines that same default
constant. This header was not found to be an error.

The adapter omits temperature, top_p, and top_k. Current SDK migration notes remove
those parameters from method signatures but describe passing them for older models
through `extra_body`; do not generalize this into a claim that every API/model
rejects them. Refusal and non-end_turn termination are handled separately. Input
usage includes reported cache reads and cache creation, but the local cost estimate
does not apply separate cache pricing tiers.

## Google Gemini

- [generateContent and GenerationConfig](https://ai.google.dev/api/generate-content)
- [Structured output](https://ai.google.dev/gemini-api/docs/generate-content/structured-output)
- [Token accounting](https://ai.google.dev/gemini-api/docs/generate-content/tokens)
- [Interactions migration](https://aistudio.google.com/docs/migrate-to-interactions)

The adapter calls
`https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`.
It sends system instructions, inline PNG and text, `maxOutputTokens`,
`responseMimeType=application/json`, `responseJsonSchema`, and `candidateCount=1`.
The key travels in `x-goog-api-key`, not the URL. Thought parts are excluded from
public text; reported thought-token count is added to candidate-output usage.

The checked GenerationConfig reference lists `responseJsonSchema` and also newer
`responseFormat` fields. Some migration documentation describes the distinct
Interactions API. Do not assume an Interactions wire shape applies to generateContent,
or that listing a field proves support for every model. This is the Gemini Developer
API adapter, not a Vertex AI or Interactions adapter.

## Maintenance and evidence requirements

Run provenance records the adapters' fixed endpoint/API namespace and the actual
Anthropic version-header constant alongside requested model IDs. It does not pin
remote model revisions or make provider-default sampling deterministic. See
[Run provenance](PROVENANCE.md). These declarations add identity evidence without
establishing remote access, model capability, or credentialed compatibility.

Keep direct httpx serialization tests, but verify their expectations against dated
external sources rather than deriving both code and fixture from the same guess.
Check schema subsets, required headers, image handling, refusal/truncation states,
retryable errors, usage fields, and model-specific output-token requirements.

All providers receive a common minimal schema, then local Pydantic validation.
Remote structured-output enforcement never replaces local validation or engine
legality. Attempts, timeouts, and output sizes remain bounded.

Live compatibility requires separately authorized smoke tests with selected models
and sanitized evidence. Record provider, model, date, result, usage, and limitations;
never record keys or raw provider errors. [R06](REVIEW.md#r06-live-provider-compatibility-is-unverified)
tracks this open validation gate.
