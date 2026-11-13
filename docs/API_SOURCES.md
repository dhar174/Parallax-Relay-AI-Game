# Provider contract references

The adapters in `parallax_relay/providers.py` use direct REST calls. This document
separates implementation choices, source checks, and live evidence. No credentialed
provider match has been verified for this repository.

## Reference check: November 13, 2026

Official-documentation and official-SDK excerpts were retrieved through Context7.
These sources support the selected request fields below; they do not establish
account access, every model's schema/vision capabilities, billing accuracy, or
acceptance of every response envelope. Links can change; recheck them when modifying
an adapter or choosing models.

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
