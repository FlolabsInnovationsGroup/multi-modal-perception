# Provider Module: Local Implementation Contract

Status: **Proposed; review in T1 before implementation**. Updated 2026-09-18.
This is implementation guidance outside the PRD, not a requirement to deploy a second service.

## Small module boundary

Use the existing FastAPI/Pydantic/Python conventions. Keep orchestration independent of provider SDK specifics. Begin with one real adapter under mocked transport and one fake; do not build a plugin marketplace, dynamic provider loader, or database catalog.

Proposed responsibilities:

| Component | Responsibility |
| --- | --- |
| Trusted-context boundary | Verify service caller/context through the agreed backend mechanism; fail closed when unavailable |
| CredentialReader | Resolve only the scoped, current permitted version; fake locally until B1-B4 are agreed |
| ProviderAdapter | Validate access, generate text, transcribe audio where supported, map errors, extract usage |
| Orchestrator | Enforce configuration, use one request-scoped secret/client, combine text/audio, close resources, return safe results |
| Route mapping | Preserve approved transport and existing fields; contains no key lookup policy or provider SDK logic |

Illustrative operations, subject to T1 naming review:

- `validate_access(context, credential, model, operation) -> ValidationResult`
- `generate_text(context, credential, model, text) -> GenerationResult`
- `transcribe_audio(context, credential, model, audio) -> TranscriptionResult`
- `supported_operations() -> declared capabilities`

Do not pass credentials between network services through this abstraction by assumption. It describes internal request-local calls. Live credential access uses the separate backend contract.

## Data and errors

Secret-bearing types must exclude the key from serialization, repr, equality diagnostics, exceptions, and test reports. Safe result types contain actual result, request ID, provider/model, nullable usage, optional sanitized provider request ID, and outcome.

Proposed internal error categories:

| Code | Meaning | Handling |
| --- | --- | --- |
| INVALID_INPUT | Missing, malformed, oversized, or unsupported input | Reject before provider execution |
| ACCESS_DENIED | Untrusted caller or scope/provider/version mismatch | Fail before secret/provider access where possible |
| NOT_CONFIGURED | Missing provider configuration or credential | No fallback |
| CREDENTIAL_UNAVAILABLE | Disabled, deleted, pending-for-invocation, or unresolvable state | No fallback; do not disclose record existence to an untrusted caller |
| CREDENTIAL_REJECTED | Provider definitively rejects authentication | Do not retry as transient |
| CAPABILITY_DENIED | Model/operation not allowed for this credential | Distinguish from malformed key |
| UNSUPPORTED_OPERATION | Adapter does not implement provider/model/operation | No provider substitution |
| RATE_LIMITED / QUOTA_EXCEEDED | Provider usage restriction | Preserve distinction; no automatic source change |
| PROVIDER_TIMEOUT / PROVIDER_UNAVAILABLE | Upstream problem or inconclusive validation | Indeterminate validation, not "invalid key" |
| INTERNAL_ERROR | Unexpected local failure | Generic response, sanitized metadata only |

B6 approves HTTP statuses and exact wire shape; do not invent a public API from these internal codes.

## Validation design

Validate access only when the backend requests it; not a billable synthetic probe before every inference. Keep definitive rejection separate from an inconclusive check. An operation check establishes only the checked capability/model at that moment, not eternal key validity or all-model access.

T3 proposes the smallest suitable provider-specific check and its limits from current official documentation. A check might use a tiny fixed text prompt or short non-sensitive audio fixture if needed to prove that operation. These are examples to review, not a requirement that every provider run both. Backend/UI owners handle any cost disclosure. No scheduler, persistence, activation, or hidden retries are added here.

## Execution safeguards

- Configuration restricts models/operations/destinations; the backend's authorized choice must match it.
- Reuse connections only if isolation is proven; never reuse a client retaining another request's key.
- No cross-request response cache, shared global key in the new path, or echo-on-error.
- If the first step of an audio+text pipeline fails, fail the operation; do not quietly return partial success.
- Capture usage per actual provider operation when available. Do not fabricate audio token counts or double-count generation.
- Close resources on success, failure, timeout, and cancellation. Do not claim cancellation undoes an upstream charge.
- Start with no automatic application-level retries. Review/disable SDK default retries where necessary. Any later retry policy requires an explicit bounded, duplicate-cost-aware decision.
- Enforce limits before unbounded reads/provider calls; test framework temporary-file behavior as well as application memory.
- Fake credentials/transports are injected only by tests/local approved harnesses, never selected by untrusted request fields.

## First code proposal

Likely locations: new provider modules under `services/`, safe types near `schemas.py`, a dedicated synthetic test directory, and later the existing route/service files. Exact filenames are chosen in T2's small plan. No dependency installation or public route change is authorized by this document.
