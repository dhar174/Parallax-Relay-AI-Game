# Provider contract references

Official documentation inspected November 12, 2026. These links describe API formats,
not a guarantee that every model supports the required features. No model names or
pricing are hardcoded in the launcher. Live account and capability checks remain pending.

## OpenAI

- Responses API: https://developers.openai.com/api/reference/resources/responses/methods/create
- Structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Image inputs: https://developers.openai.com/api/docs/guides/images-vision

Adapter sends one request with instructions, input text plus PNG data URI, `store=false`,
`max_output_tokens`, and `text.format` JSON Schema with strict mode. It extracts message
output text, checks completion/refusal status, and records reported usage. No server-side
conversation or previous response ID is reused.

## Anthropic Claude

- Messages: https://platform.claude.com/docs/en/api/messages
- Vision: https://platform.claude.com/docs/en/build-with-claude/vision
- Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- API versioning: https://platform.claude.com/docs/en/api/versioning

Adapter uses `/v1/messages`, a system instruction, a base64 PNG image block and text,
`max_tokens`, and `output_config.format`. It pins the documented `anthropic-version`
header to `2026-10-21`. It does not send temperature, top_p or top_k, which this version
removed. Refusal and non-end_turn termination are handled separately from normal output.

## Google Gemini

- generateContent request: https://aistudio.google.com/api-reference/generate-content/generate-content
- Response and usage: https://aistudio.google.com/api-reference/generate-content

Adapter uses the documented `v1beta/models/{model}:generateContent` endpoint with
`systemInstruction`, `contents` text plus `inlineData` PNG, and `generationConfig`
with `responseMimeType=application/json`, `responseJsonSchema`, `maxOutputTokens`
and one candidate. The API key is in `x-goog-api-key`, not a URL. Thought blocks are
excluded from text extraction; reported thought-token usage contributes to output
accounting. This is the Gemini Developer API path, not a Vertex AI adapter.

## Maintenance and limitations

Direct `httpx` adapters were chosen to keep the dependency set small and permit exact
wire-level offline tests. Provider payload parsing is maintained locally rather than
outsourced to three SDKs. Check these documents when changing versions/models.

All adapters use the same minimal schema, then validate locally with Pydantic.
Provider-side schema enforcement does not replace local validation, timeout handling,
refusal handling, truncation detection, or authoritative game-rule enforcement.
