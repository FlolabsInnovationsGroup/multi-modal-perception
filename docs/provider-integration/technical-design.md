# Provider Integration Architecture and Technical Design

Revision 2.1, 2026-09-19. Status: implementation specification proposed for T1 review. Local decisions L1-L8 below are concrete review candidates, not approved code changes. Live mechanisms B1-B7 remain unresolved. This is a local module design, not a second deployment or a public API specification.

Read the [requirements](requirements.md) first. Sections below combine the former module contract, data flow, and backend contract so there is one technical reference. Use synthetic fakes for local work; do not invent a live service contract.

## Local module contract

Status: **Proposed; review in T1 before implementation**. Updated 2026-09-18.
This is implementation guidance outside the PRD, not a requirement to deploy a second service.

### Small module boundary

Use the existing FastAPI/Pydantic/Python conventions. Keep orchestration independent of provider SDK specifics. Begin with one real adapter under mocked transport and one fake; do not build a plugin marketplace, dynamic provider loader, or database catalog.

Proposed responsibilities:

| Component | Responsibility |
| --- | --- |
| Trusted-context boundary | Verify service caller/context through the agreed backend mechanism; fail closed when unavailable |
| CredentialReader | Resolve only the scoped, current permitted version; fake locally until B1-B4 are agreed |
| ProviderAdapter | Validate access, generate text, transcribe audio where supported, map errors, extract usage |
| Orchestrator | Enforce configuration, use one request-scoped secret/client, combine text/audio, close resources, return safe results |
| Route mapping | Preserve approved transport and existing fields; contains no key lookup policy or provider SDK logic |

Operation responsibilities (exact internal signatures are specified in L2 below):

- `validate_access(context, credential, model, operation) -> ValidationResult`
- `generate_text(context, credential, model, text) -> GenerationResult`
- `transcribe_audio(context, credential, model, audio) -> TranscriptionResult`
- `supported_operations() -> declared capabilities`

Do not pass credentials between network services through this abstraction by assumption. It describes internal request-local calls. Live credential access uses the separate backend contract.

### Data and errors

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

### Validation design

Validate access only when the backend requests it; not a billable synthetic probe before every inference. Keep definitive rejection separate from an inconclusive check. An operation check establishes only the checked capability/model at that moment, not eternal key validity or all-model access.

L6 specifies the proposed OpenAI checks for T1 acceptance; T3 verifies the installed SDK and implements them with mocked transport. Later providers need their own reviewed checks. Each validation targets one capability, not both automatically. Backend/UI owners handle cost disclosure. No scheduler, persistence, activation, or hidden retries are added here.

### Execution safeguards

- Configuration restricts models/operations/destinations; the backend's authorized choice must match it.
- Reuse connections only if isolation is proven; never reuse a client retaining another request's key.
- No cross-request response cache, shared global key in the new path, or echo-on-error.
- If the first step of an audio+text pipeline fails, fail the operation; do not quietly return partial success.
- Capture usage per actual provider operation when available. Do not fabricate audio token counts or double-count generation.
- Close resources on success, failure, timeout, and cancellation. Do not claim cancellation undoes an upstream charge.
- Start with no automatic application-level retries. Review/disable SDK default retries where necessary. Any later retry policy requires an explicit bounded, duplicate-cost-aware decision.
- Enforce limits before unbounded reads/provider calls; test framework temporary-file behavior as well as application memory.
- Fake credentials/transports are injected only by tests/local approved harnesses, never selected by untrusted request fields.

### Implementation map

The L1 file map below is the proposed implementation layout. Keep new internal types separate from the existing public `schemas.py`. No dependency installation or public route change is authorized by this document.

## M1 implementation specification — review L1-L8 together

These decisions fill the multimodal-owned design. T1 records accept/amend/reject for each L ID in the review record. After acceptance, implement them in T2-T4; do not reopen settled choices without evidence of a conflict. They do not select a real backend schema or authenticate a real caller.

### L1 — Architecture and file ownership

```text
Existing public routes (unchanged/unconnected during M1)

Test harness / future approved backend bridge
    -> handler -> ContextVerifier -> VerifiedContext
               -> input/config checks and capacity gate
               -> CredentialReader.admit (exact scope/version/state)
               -> request-local ProviderSession
                    -> transcription when audio exists
                    -> generation
               -> safe result + operation usage -> caller

Separate validation handler
    -> same guard/admission (pending allowed only here)
    -> one synthetic capability probe -> version-bound validation result

Fakes live only in tests; the unconfigured runtime denies access.
```

| Proposed path | Responsibility / primary task |
| --- | --- |
| `services/provider_integration/__init__.py` | Public internal entry points; no I/O at import; T2 |
| `services/provider_integration/types.py` | Internal immutable request/result types, secret holder, enums; T2 |
| `services/provider_integration/ports.py` | ContextVerifier, CredentialReader, ProviderAdapter and ProviderSession protocols; T2 |
| `services/provider_integration/errors.py` | Safe failure codes/messages; T2 |
| `services/provider_integration/config.py` | Explicit immutable model/destination/limit configuration; T2 |
| `services/provider_integration/orchestrator.py` | Admission, ordering, deadlines, cleanup and safe result composition; T2 |
| `services/provider_integration/adapters/openai.py` | Only OpenAI SDK-dependent behavior; T3 |
| `services/provider_integration/handler.py` | Internal input normalization and legacy-success projection; T4 |
| `services/provider_integration/wiring.py` | Explicit dependency injection; deny-all unconfigured verifier/reader; T4 |
| `tests/provider_integration/fakes.py` | Synthetic verifier, atomic in-memory reader, scripted provider and clock; T2 |
| `tests/provider_integration/test_*.py` | Dedicated offline tests listed in acceptance plan; T2-T4 |

Only the adapter imports OpenAI. No import reads `OPENAI_API_KEY`, creates a client, loads dotenv, performs network I/O, or registers routes. Provider registry is a small explicit mapping injected at composition, not a discovery framework. Shared configuration and capacity counters contain no keys/content. Do not alter MiniCPM or build provider stubs for future brands.

### L2 — Exact internal contract

Use Python 3.11/3.12 standard-library dataclasses/enums/protocols and existing Pydantic conventions for safe boundaries. Reject unknown fields where parsing is used. These are in-process types, NOT a new public JSON API. No client can construct a trusted context merely by supplying these fields.

| Type | Fields and rules |
| --- | --- |
| `Binding` | `scope_id`, `credential_ref`, `credential_version`, `credential_source` (`customer` or `platform`), `provider`; exact equality, never case-fold opaque IDs |
| `VerifiedContext` | Binding plus `request_id`, `kind` (`invoke` or `validate`), `allowed_targets` (immutable pairs of operation/model), `expires_at` (UTC); only returned by the injected verifier after verification |
| `Target` | `operation` (`generate_text` or `transcribe_audio`), `model`; must exactly match both context and configured capabilities |
| `InvocationInput` | `text` string (empty allowed only with nonempty audio), `audio` optional in-memory bytes, `audio_format` required when audio exists (`wav`, `mp3`, `m4a`, `webm`, `mp4`, `mpeg`, `mpga`); caller filename discarded |
| `InvocationRequest` | Input plus generation Target and optional transcription Target; text-only forbids an unused transcription target; nonempty audio requires both targets |
| `ValidationRequest` | Exactly one Target, no customer text/audio; context kind must be validate |
| `CredentialLease` | Binding, `state`, request-local secret holder, permitted targets, opaque admission ID; async context-managed and never serializable |
| `UsageEntry` | `operation`, `model`, nullable nonnegative `input_tokens`, `output_tokens`, `total_tokens`, `audio_seconds`; optional sanitized `provider_request_id`; copy only provider-reported values, never calculate an invoice or sum unlike units |
| `InvocationResult` | `request_id`, `provider`, generation `model`, `file_type` (`text` or `audio`), `outcome` (`success` or `error`), nullable `result`, nullable `error_code`, `usage` tuple |
| `ValidationResult` | `request_id`, Binding (internal only), Target, UTC `checked_at`, `status` (`valid`, `rejected`, `indeterminate`), nullable `reason_code`, usage tuple; no provider response text |
| `BoundaryFailure` | Locally generated `request_id`, `outcome=error`, `result=null`, allowlisted `error_code`, empty usage; no reflection of unverified scope/provider/model values |

IDs/model names must be nonempty ASCII `[A-Za-z0-9._:-]`, at most 128 characters; generated local request IDs are UUIDs. This is a proposed internal representation, not a requirement that a backend change its identifiers: B2's bridge must use a reviewed opaque mapping if its format differs. Check context expiry before admission; the real authority, clock tolerance and replay mechanism are B3. Exact request targets must be included in the context; never trust an input field named `authorized`.

Success has a nonempty result and no error code; failure has null result and one allowlisted code. An empty/whitespace provider generation, refusal without usable content, or malformed response is `PROVIDER_RESPONSE_INVALID`, never a successful echo. A timeout of the overall operation is `OPERATION_TIMEOUT`; local saturation is `CAPACITY_EXCEEDED`. These three codes extend the earlier error table. No HTTP status is implied. Safe user messages come from a fixed code-to-message map; don't interpolate IDs, filenames, exception text or model output into errors.

Parsing or verifier failure returns BoundaryFailure (INVALID_INPUT or ACCESS_DENIED), without reflecting untrusted metadata. Once context and request are verified, invocation failures use InvocationResult; validation failures before a definitive provider access decision are indeterminate, including unavailable reader/state, capacity and local timeout. A reader outage is CREDENTIAL_UNAVAILABLE; a returned binding mismatch is ACCESS_DENIED. Only L6's definitive provider rejections produce validation status rejected. No-call results have empty usage; each attempted provider operation has an entry with null unreported quantities, retaining earlier completed-step usage. Malformed usage quantities become null rather than failing an otherwise valid content response; negative numbers are not accepted.

Internal signatures: verify, invoke, validate, process and session operations are async. `admit` and `open_session` are factories returning async context managers, used with `async with` (not awaited separately). Capability lookup, configuration validation and legacy_success are synchronous.

```text
ContextVerifier.verify(call_evidence, requested_binding, kind, targets) -> VerifiedContext
CredentialReader.admit(context, targets) -> async context manager yielding CredentialLease
ProviderAdapter.supported_operations() -> immutable configured operation/model pairs
ProviderAdapter.open_session(lease, config) -> async context manager yielding ProviderSession
ProviderSession.generate_text(target, text, remaining_seconds) -> text + UsageEntry
ProviderSession.transcribe_audio(target, audio, format, remaining_seconds) -> transcript + UsageEntry
ProviderSession.validate_access(target, remaining_seconds) -> ValidationResult data
Orchestrator.invoke(verified_context, request) -> InvocationResult
Orchestrator.validate(verified_context, request) -> ValidationResult
Handler.process(call_evidence, requested_binding, request) -> InvocationResult or BoundaryFailure
Handler.validate(call_evidence, requested_binding, request) -> ValidationResult or BoundaryFailure
legacy_success(result) -> PerceptionOutput (success only; errors cannot be projected)
```

Verifier/reader/session infrastructure failures become safe errors; cancellation is propagated after cleanup, not swallowed as a normal result. Sessions never activate/update/delete a credential. The secret holder has constant redacted repr/str, identity-based equality, and denies serialization/copy/pickle. Plaintext extraction is private to the adapter session. Avoid retaining raw SDK exceptions as causes or result fields; capture only allowlisted classifications then discard them. Drop a returned provider request ID if it fails the ID rule or contains the exact in-flight key. Reject any outgoing result containing the exact key as `INTERNAL_ERROR`; this is defense in depth, not a guarantee against every encoded disclosure.

### L3 — Admission, lifecycle and isolated test implementation

Invocation accepts only `active`. Validation accepts `active` or `pending`. `disabled`, `deleted`, `expired`, unknown state, absent record or mismatched binding always deny. A replacement is a separate version; the module never searches for another version.

The fake reader stores synthetic records indexed by scope/ref/version. Under one async lock it checks full binding, context expiry, targets, state and the active-version pointer, then records an admission and returns that exact snapshot. A test-only rotate/disable operation uses the same lock. A request admitted before a change may finish its entire audio+text pipeline; a later admission using an old version fails, rather than silently upgrading. Validation results retain the checked version even if replacement/deletion happens meanwhile. The simulated backend fixture discards stale results; multimodal does not implement backend persistence or activation.

The fake verifier uses explicit test registrations for evidence handles and returns prepared contexts; unknown or expired handles fail. This is a test double, not authentication. Fake keys use only `test-provider-key-...` values; fake transports capture call arguments in test memory, never dump them on assertion failure. Orchestrator checks lease binding/state/targets again to catch a broken reader. Test B4 timing with barriers/events, not sleep-based race guesses. One admission covers one invocation/validation; release on all exits.

### L4 — Text/audio compatibility and content handling

Normalize submitted text with `.strip()`. Empty audio bytes count as no audio. Reject missing content before reader access. With audio and no text, use the existing instruction `reply to the audio`. Transcribe before generating; assemble `instruction + "\n\nAudio transcript:\n" + transcript` when both are nonempty. Preserve existing empty-transcript behavior: use the instruction alone (successful transcription with no speech is not an exception). Do not generate when transcription fails. Generation output is stripped; an empty output fails as specified in L2.

Successful legacy projection includes only `result`, generation `model`, and `file_type` (`audio` whenever nonempty audio was supplied). Provider/usage/correlation fields remain in the internal result for the later backend bridge; don't silently extend the existing public schema. Record per-step usage; if generation fails after successful transcription, return an error with the known transcription usage, not partial successful content. Transcript is never a separate response field.

M1 accepts bytes already supplied by a trusted local test harness, with no files persisted. Generate a safe upload filename such as `input.wav` from the validated format. Extension/MIME is not proof that audio is decodable; provider rejection becomes safe `INVALID_INPUT`. Do not add a media decoder dependency. Input size is checked before copying into streams. A live HTTP bridge must enforce size before multipart parsing/spooling and have memory-only bounded handling; closing/deleting a spool after use does not meet non-persistence. Existing FastAPI upload routes are NOT evidence this is solved. T4 documents this constraint without connecting the new module to those routes.

### L5 — Reviewable local operating profile

These are proposed conservative engineering limits for M1, not provider limits, service SLOs or approved production quotas. T1 accepts/amends them together; B5/B7 reconcile live budgets before T5/T6. Use immutable injected configuration, not user overrides. Reject missing/invalid configuration instead of inventing defaults in a request.

| Setting | Proposed value / action |
| --- | --- |
| Raw text input | 65,536 UTF-8 bytes maximum, checked before stripping; over limit -> INVALID_INPUT |
| Combined generated prompt / transcript | 131,072 UTF-8 bytes each maximum; over limit -> INVALID_INPUT; never truncate silently |
| Audio | 10,485,760 bytes maximum; formats L2; over limit -> INVALID_INPUT |
| Returned generation | 65,536 UTF-8 bytes maximum; larger -> PROVIDER_RESPONSE_INVALID |
| Total provider response body | 1,048,576 bytes per operation, counted while receiving before SDK deserialization; excess aborts safely |
| Overall invocation | 90 seconds from handler entry including verification/admission; OPERATION_TIMEOUT on expiry |
| Overall validation | 20 seconds including verification/admission; indeterminate with OPERATION_TIMEOUT on expiry |
| Verify and admit | Each at most 5 seconds, also bounded by remaining overall deadline; denial/unavailability on failure |
| Provider calls | Generation at most 30 seconds, transcription at most 60, validation at most 15; always min with remaining overall deadline |
| Connections / cleanup | Connect at most 5 seconds; bounded cleanup at most 2 seconds, release capacity even on cleanup failure |
| Concurrency | Shared per-process gate of 8 invocations/validations total; no waiting queue; ninth -> CAPACITY_EXCEEDED before credential access |
| Retries / redirects | Zero application retries; SDK max_retries=0; redirects disabled; never retry an entire combined pipeline |
| Text generation settings | Existing first-slice defaults: max_tokens=256, temperature=0.4; existing fixed system prompt passed explicitly in configuration |

Apply total deadline using a monotonic clock after initial context-expiry verification. No sleep-based tests of the full 90 seconds: inject clock/barriers and use small test-only deadlines. Eight is a local resource guard, not tenant fairness or a fleet-wide quota. Those remain B7. Byte limits do not prove model context-window compatibility; provider token-limit errors are safely mapped, with no truncation or model switch.

### L6 — First OpenAI adapter specification

Proposed first slice retains existing API families and model names: generation `gpt-4o-mini` through Chat Completions, transcription `gpt-4o-mini-transcribe` through audio transcriptions. These are explicit deployment configuration entries, not fallback values and not a guarantee every account has access. Support exactly these two targets initially; new models/providers require reviewed capability entries and tests.

Create one AsyncOpenAI session per lease, with the explicit key, fixed `https://api.openai.com/v1/` destination, no environment-key fallback, max_retries=0, explicit operation timeout and owned transport. Do not inherit arbitrary base URL, proxy, organization/project headers, custom auth headers or verbose SDK logging from the caller/environment. Use TLS verification and no redirects. B1/B3/B7 must review any real environment routing needs; fail configuration rather than override silently. The transport must enforce L5's response byte cap before buffering; use the already-installed HTTP transport's streaming boundary, with fake transport tests. If the installed SDK cannot satisfy this without a dependency change, stop for the specific change approval.

Generation sends the existing system prompt and composed user prompt, non-streaming, max_tokens=256, temperature=0.4 and store=false. Transcription sends the bounded memory stream with generated filename, selected model and response_format=json, non-streaming. No remote file upload API, background jobs, tools or conversation persistence are added. `store=false` is not a provider zero-retention promise. Current reference marks max_tokens deprecated; this slice retains the repository's parameter for compatibility with its existing model/API family. If the installed SDK/model cannot support the reviewed request, seek a compatibility decision rather than silently migrating it.

Validation uses exactly one selected capability, never both implicitly. Text probe: fixed `Reply with OK.`, max_tokens=8, temperature=0, store=false; a structurally valid nonempty text response proves access, not exact wording. Audio probe: one-second mono 16-kHz, 16-bit PCM silent WAV generated in memory with standard-library wave/io; a successful transcription object with a text string (including empty string) proves endpoint access. No customer media, prerecorded voice, downloaded fixture or local audio file. Validation sends only this fixture to the selected model; no list-models call is accepted as proof of operation access. Each validation can consume quota. Live approval and backend disclosure/rate controls remain B5.

| Provider/transport evidence | Invocation code | Validation outcome |
| --- | --- | --- |
| 401 with allowlisted invalid_api_key code | CREDENTIAL_REJECTED | rejected |
| Other 401 (may include account/IP restrictions) | ACCESS_DENIED | indeterminate; do not call key invalid from status alone |
| 403 access denied | CAPABILITY_DENIED | rejected for target, not proof key invalid |
| 404 model_not_found for configured target | CAPABILITY_DENIED | rejected for target; existence and permission are not distinguished |
| 429 with quota/billing code listed below | QUOTA_EXCEEDED | indeterminate |
| Other 429 | RATE_LIMITED | indeterminate |
| Timeout | PROVIDER_TIMEOUT | indeterminate |
| Connection failure / 408 / 5xx | PROVIDER_UNAVAILABLE | indeterminate |
| 400/413/422 input failure | INVALID_INPUT | indeterminate (fixture/config problem, not invalid key) |
| Other status, redirect, malformed success | PROVIDER_RESPONSE_INVALID | indeterminate |

Unknown local exceptions are INTERNAL_ERROR. Never classify by searching raw exception messages. Read only status and bounded allowlisted provider code/type; never retain raw body. Quota/billing code allowlist: insufficient_quota, credit_balance_exhausted, organization_spend_limit_exceeded, project_spend_limit_exceeded, organization_usage_limit_exceeded; legacy type insufficient_quota also maps to QUOTA_EXCEEDED. Unknown 429 remains RATE_LIMITED without claiming a billing diagnosis. Null/missing usage is null, not zero; map Chat prompt/completion tokens to input/output and transcription's reported token/duration fields when present. Preserve each operation/model separately; no derived total across calls. Captured upstream request IDs must pass L2 filtering.

Official sources checked 2026-09-19 (documentation only; no API call): [GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini), [Chat Completions request fields](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create), [transcriptions](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create), [Python SDK](https://developers.openai.com/api/reference/python), [error codes](https://developers.openai.com/api/docs/guides/error-codes). These support API family/fields, transcription JSON, configurable retries/timeouts, and error distinctions; local limits/probes are our proposals, not provider recommendations.

Important version boundary: requirements currently permit openai>=1,<2, while current online SDK documentation can describe later releases. T3 must record the installed Python/OpenAI/transport versions and inspect their actual public signatures/source read-only before coding. Do not copy a new transport package name from current docs or upgrade silently. If unavailable, request environment approval; mocked tests alone do not prove live account/model access. Recheck official model availability/deprecations before live enablement.

### L7 — Offline execution and wiring

Use standard-library unittest/IsolatedAsyncioTestCase and unittest.mock; use installed transport mocking only if present. Tests deny real socket/network creation and instantiate only explicit synthetic dependencies. No `.env` loading, real credential lookup, GPU tests, downloads or paid calls. Verify import with OPENAI_API_KEY unset in a subprocess whose environment omits secrets; do not print environment values. M1's example is an in-process test harness, not a runnable public demo server.

Unconfigured wiring has deny-all verifier/reader and no enabled provider; attempts fail before secret/provider access. No `mode=fake` request parameter or production env flag selects fakes. Test harness imports fakes from tests only. Legacy `services/openai_service.py`, `api/process.py`, `api/openAI.py` and `main.py` remain unchanged in M1, so existing risks remain explicitly documented and no claim of production protection is made. T5/T6 separately replace/wire the real path after B1-B7 approval and test that no legacy route bypasses it. Rollback disables BYOK; it never sends a BYOK request through the old singleton.

### L8 — Review and handoff definition

M1 is complete only with an accepted L1-L8 record, all T2-T4 task evidence, the local TC cases passing, a runnable offline test command, reviewed changes, zero unresolved high/critical isolation or disclosure issues, and a backend handoff documenting B1-B7. Names of human reviewers/owners must be supplied by the team, not AI.

Handoff consists of this internal contract and version, the fake reader/verifier conformance tests, result/error examples, compatibility projection, limit profile, installed SDK versions, known legacy exposure/spooling risks, and local test evidence. B1-B7 then determine adapters at the boundary; do not redesign core behavior casually or label the live feature finished. The backend need not adopt our Python classes or identifier format on its wire API.

Synthetic example: test verifier admits scope `scope-A`, ref `credential-A`, version `v1`, source `customer`, provider `openai`, kind invoke, target generate_text/gpt-4o-mini. For text `Hello`, the scripted provider returns `Synthetic answer`; output is success with result `Synthetic answer`, model `gpt-4o-mini`, file_type text, empty/nullable usage as reported. Changing scope to `scope-B` must produce ACCESS_DENIED with null result, zero provider calls and no key in output. Validation of pending `v2` returns the same version without changing active `v1`. These examples contain no actual credentials or authorization tokens.

## Data flow and trust boundaries

Status: proposed technical flow for team review, 2026-09-18.
Replaces the earlier all-platform broker flow. No AWS topology is selected.

### Current code

Caller -> unauthenticated FastAPI route -> global OpenAI client/environment key -> provider.
Generation also uses a prompt-only response cache and echoes input on failure. Both routes return result/model/file_type. This is a baseline to change, not a safe BYOK design.

### Target logical flow

```text
User -> FloBrain backend (user authentication, authorization, credential selection)
                    |
                    | authenticated service request + bound scope/reference + content
                    v
          Multimodal request boundary
                    |
                    +-> CredentialReader -> backend-managed protected storage/interface
                    |      exact permitted version/state; request-local secret
                    v
           Selected provider adapter -> approved provider endpoint
                    |
                    v
          result + safe metadata -> FloBrain backend -> User
```

The reader protocol and service authentication are unresolved B1-B3, not implied by the arrows. An internal function boundary does not require another deployed service. Backend-managed storage may contain an encrypted credential or a secure reference; no plaintext database design is authorized.

### Invocation order

1. Verify the backend caller/context; validate input limits and selected supported provider/model/operation.
2. Resolve the exact scoped credential/version through the approved reader. Verify returned ownership/provider/state against trusted context.
3. Apply the agreed admission/state consistency rule immediately before provider use; B4 must cover races, not only sequential checks.
4. Create request-local provider execution. Transcribe audio if requested, then generate the response with that authorized configuration.
5. Return actual result plus safe metadata/usage. On failure return a normalized error, not an echo or another key/provider.
6. Close clients/streams and release secret/content references on every exit path. Never cache across requests.

### Validation path

Backend selects a candidate version -> authenticated validation request -> scoped reader permits that pending version only for validation -> adapter checks specified capability with approved synthetic data -> version-bound validation result -> backend decides whether to activate.

Validation does not save keys, grant ownership, register users, activate replacements, or start a scheduler. No separate customer write-only credential route is created in this repository.

### Boundaries to verify

| Boundary | Owner/control | Evidence |
| --- | --- | --- |
| User -> backend | Backend user auth and authorization; not implemented here | Backend contract approval |
| Backend -> multimodal | Authenticated caller, fresh bound context, no bypass through old routes | TC-02, TC-14 |
| Multimodal -> credential source | Least-privilege exact lookup, protected retrieval, state/version consistency | TC-02, TC-05, TC-06, TC-13 |
| Adapter -> provider | Approved destination/configuration, bounded execution, request-scoped secret | TC-07, TC-09, TC-12 |
| Runtime -> diagnostics | Allowlisted metadata only; no raw bodies/headers/exceptions | TC-08, TC-11 |

Multimodal stores no credential values or interaction content. FloBrain owns lifecycle metadata and its retention policy; the platform owner owns logging retention and deployment. Provider-side data handling requires separate verification.

## Backend integration boundary

Status: **Proposed contract; live integration blocked**. Updated 2026-09-18.
Basis: PRD PI-02, PI-03, PI-05, PI-07, PI-08, PI-12.

Indra's review says multimodal reads and validates API keys from storage populated by FloBrain and uses them for provider calls. The storage schema, retrieval protocol, and service identity mechanism have not been supplied. This document specifies the information and guarantees needed; it does not assert an existing endpoint, table, cloud service, or plaintext database design.

### Ownership

FloBrain authenticates users, authorizes their requested operation, selects the permitted credential/source, stores protected keys, manages lifecycle state, and persists accepted validation results. Multimodal authenticates the calling service, validates request/context binding, reads only the permitted key version, checks provider access when asked, invokes the model, and returns safe results.

Multimodal must not expose key-management or key-readback APIs to end users. It must not implement user-role logic independently of FloBrain. A private network or a field saying "authorized" is not service authentication.

### Required logical inputs

These are conceptual names for review, **not a published HTTP schema**.

| Field / information | Required guarantee |
| --- | --- |
| request_id | Bounded correlation ID generated or validated by the service; no secrets embedded |
| authorization_context | Authenticated backend authority bound to scope, credential, provider, permitted operation, and freshness |
| ownership_scope | Opaque backend-defined customer/workspace scope; exact schema remains B2 |
| credential_reference + version | Exact backend-selected record/version; an identifier is not an authorization capability by itself |
| credential_source | Explicit customer-managed or platform-managed selection if both are supported; never inferred from failure |
| provider + model + operation | Approved supported configuration, including transcription model when needed |
| input | Validated text/audio for invocation; validation uses approved synthetic input only |
| operation_kind | Invocation or validation; validation of a pending version does not authorize model use for a customer request |

Do not accept endpoint overrides, arbitrary authentication headers, role claims, or a plaintext API-key field from a public processing caller.

### Credential reader boundary

For approved local work, define a replaceable `CredentialReader` interface with a synthetic fake. It accepts verified operation context and a credential reference; it returns the exact scoped version/state/provider and a secret-bearing request-local value or a safe error. Secret-bearing objects must not serialize or appear in repr/logging.

The live reader may require database access or a backend-mediated interface; B1 decides this from the actual FloBrain implementation. Do not invent SQL, connection strings, URLs, or decryption keys. Direct database access, if selected, must use least-privilege scoped reads and the backend-approved decryption mechanism. Never treat encrypted database contents as permission to decrypt any tenant's record.

The service verifies returned scope/provider/version/state against trusted context. The reader must not enumerate credentials or automatically select a previous or platform key. A failure returns a safe failure, not an empty value that triggers environment-key fallback.

### Validation and lifecycle coordination

1. Backend registers a candidate and requests validation of that exact version.
2. Multimodal performs the approved provider-specific access check, with no customer content.
3. It returns version-bound `valid`, `rejected`, or `indeterminate`, plus a safe reason, check time, operation/model, and provider request ID if safely available.
4. Backend persists the result and alone decides atomic activation. It must reject stale results for a changed/deleted candidate.
5. Failed candidate validation leaves active selection unchanged. Multimodal never performs activation, deletion, recovery, or provider-account revocation.
6. Runtime retrieves/rechecks current permitted state for each operation; no cross-request secret cache.

No automatic validation scheduler or queue is in this scope. The initial proposal is explicit backend-requested validation. Transient failure returns indeterminate; the backend can request another attempt under its rate/cost policy. A future scheduler needs its own requirements.

Disablement/rotation races require B4's agreed ordering point. Target behavior: operations admitted after disablement cannot acquire/use that credential, and operations admitted after replacement use the new active version. Already-admitted calls may finish. A naive "read status then use later" check cannot by itself guarantee this under races. Agree atomic admission/version checking or another tested coordination mechanism before live use.

### Outputs to FloBrain

Return a model result for invocation, or validation result for a validation operation, together with bounded request ID, provider/model, operation, safe outcome, and available usage. Provider usage is not the invoice. Missing usage is null/unavailable, not zero. Provider request IDs are optional, size-limited, and permitted only after adapter sanitization.

No secret, secret fragment, raw provider body on error, SDK object, authorization header, internal storage path, or decryption details may be returned. Success content is delivered to the caller transiently, not stored in this service.

### Decision register: backend owner and lead must complete

| ID | Question / required artifact | Blocking point | Status |
| --- | --- | --- | --- |
| B1 | Actual protected storage schema/interface; direct scoped DB read or backend-mediated retrieval; encryption/decryption and least-privilege access owner | Real credential-reader implementation | Unresolved |
| B2 | Source and schema of trusted scope/credential/provider binding; support for customer/platform sources; authorization policy ownership | Live request contract | Unresolved |
| B3 | Service authentication, request integrity, expiry/replay handling, network exposure, secret-free failure responses | Any externally reachable BYOK path | Unresolved |
| B4 | Lifecycle states, version identifiers, activation ownership, atomic admission/disable/rotation ordering, stale validation result handling | Live lifecycle correctness | Unresolved |
| B5 | When validation is requested; approved check per operation, rate/cost limits, timeout/retry budget, and result persistence | Live validation | Unresolved |
| B6 | Existing consumers; exact route/transport and error status mapping; response compatibility, usage fields, migration and rollback | Exposed API changes / T5-T7; T4 uses reviewed local assumptions only | Unresolved |
| B7 | Input/upload/concurrency limits; content-spooling and telemetry controls; approved metadata retention and support owner | Integration/release safety | Unresolved |

For each decision record: owner, dated answer, reviewed specification link, approving people, and acceptance tests. No values, secrets, private dumps, or real customer payloads belong here.

### Handoff checklist

- [ ] Lead and backend owner agree B1-B7 and exact schemas/transport.
- [ ] Required permissions are scoped, reviewed, and separately approved before access.
- [ ] Denied/untrusted calls cannot reach the reader or provider.
- [ ] Cross-scope identifiers, stale authorization, and inactive versions are rejected.
- [ ] Pending validation cannot become normal invocation.
- [ ] Activation/disablement race tests cover the agreed consistency boundary.
- [ ] Logging, upload spooling, SDK failures, and backend outages do not expose secrets/content.
- [ ] Staging environment and any real-key use receive explicit approval.
