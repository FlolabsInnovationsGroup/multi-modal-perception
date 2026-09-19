# Feature Requirements: Provider Integration with Backend-Managed API Keys

Revision: 2.1 — 2026-09-19. Status: **Ready for team review; local implementation specification L1-L8 awaits acceptance**.
Prepared under the user's approved documentation-revision plan, incorporating Indra Araujo's review. This is not a claim that Indra has approved the rewritten wording or an implementation design. A separate Credential Broker deployment is not required by this specification.

## 1. Problem and purpose

The multimodal service currently calls a provider using one shared API key. It needs to use the correct backend-managed key for each authorized request, validate provider access, and return the model's result without exposing the key or mixing customers' requests.

The goal is a modular, independent provider-integration service whose common behavior does not depend on one provider. Supporting a provider means implementing and verifying its integration; it does not mean any provider or model works automatically. Provider sequence belongs in the delivery plan, not these requirements.

## 2. Team responsibilities

| Multimodal team owns | FloBrain backend / other teams own |
| --- | --- |
| Read the selected credential through an agreed secure interface to backend-managed storage | User authentication, permissions, and determining which credential a request may use |
| Validate provider access and return a clear result | Key submission, protected storage, ownership records, activation/replacement, disablement, deletion, and recovery policy |
| Call the selected provider/model with the selected key | User interface, customer notices, account/billing policy, and platform infrastructure |
| Return results, safe errors, and available usage metadata | Persisting permitted validation/usage metadata and operating backend lifecycle workflows |

There are no owner/admin/member roles to implement inside this service. It must nevertheless accept only trusted backend calls and reject credential/context mismatches. Backend responsibility does not make an unauthenticated request trustworthy.

## 3. Functional requirements

**PI-01 — Modular provider support.** Use a common integration boundary for credential validation and model execution. Each supported provider can implement its own authentication and capabilities without changing unrelated provider code. Unsupported providers or operations return an explicit error.

**PI-02 — Correct credential selection.** Read only the credential authorized by the backend for this request. Match its ownership scope, provider, version, and permitted operation to trusted request context. Missing or mismatched context must fail before credential use. Do not select an arbitrary database record from a caller-supplied identifier alone.

**PI-03 — Credential validation.** Report whether a selected key can perform the requested supported operation, whether access is definitively rejected, or whether the check could not be completed. A correctly formatted key is not proof of provider access. A timeout or unavailable provider must not be reported as an invalid key. Validation must not use customer content or automatically activate a key.

**PI-04 — Model interaction.** Invoke the provider and model explicitly selected in authorized backend configuration. Reject unsupported models, operations, and incompatible inputs before sending content. Return the actual model result and identify the provider/model used. Preserve supported text/audio behavior; additional modalities require their own tasks.

**PI-05 — Credential changes.** Respect the backend's current active version and state. New operations must not use disabled or deleted credentials. Validate a pending replacement only for a backend-authorized validation operation; normal execution uses the active version. Return validation against the exact version checked so the backend cannot accidentally activate a different version. Failed replacement validation must not cause this service to switch away from the current active key.

**PI-06 — Explicit failure, no fallback.** Missing, rejected, unavailable, disabled, expired, rate-limited, or quota-exhausted credentials produce a safe failure. Never silently switch to a platform key, a previous key, another provider, model, endpoint, deployment, or region. Never return the submitted prompt as a successful substitute response.

**PI-07 — Predictable results and errors.** Return a correlation ID, safe outcome, selected provider/model, and provider-reported usage when available. Distinguish unavailable usage from zero usage. Errors must distinguish invalid input, access denied, missing configuration, rejected credential, unavailable credential, unsupported operation, quota, rate limit, timeout, and upstream failure without leaking raw provider details.

## 4. Security and reliability requirements

**PI-08 — Secret protection.** Use keys only server-side for the current authorized operation. Do not return them to callers or put them in logs, traces, URLs, analytics, fixtures, queues, or cross-request caches. Do not persist a local copy of backend-managed keys. Storage encryption and retrieval permissions must be agreed with the backend before real integration.

**PI-09 — Request isolation and content handling.** Concurrent requests must not share credential-bearing clients or cached responses across customers. Do not persist prompts, audio, transcripts, or responses in this service. Provider-side retention is separate and must not be described as controlled by this requirement.

**PI-10 — Approved destinations.** Credentials and content go only to destinations configured for the selected supported provider. Do not accept arbitrary caller-supplied destinations or authentication headers.

**PI-11 — Bounded execution.** Validation and invocation must have agreed input, concurrency, and time limits. Any retry policy must be bounded and must not retry definitive access failures or silently duplicate potentially billable operations. Numerical limits and provider-specific checks belong in technical configuration and tests.

**PI-12 — Backend integration and compatibility.** Agree on service authentication, credential retrieval, status/version consistency, response/error format, and existing caller migration with FloBrain. Do not replace existing routes or break response fields without an approved compatibility decision. Operational metadata must exclude secrets and customer content.

## 5. Plain-language definitions

- **Credential / API key:** a secret authorizing access to a provider account.
- **Capability / operation:** what a model is asked to do, such as generating text or transcribing audio.
- **Validation:** a deliberate check of access to a selected operation; the method varies by provider and may consume quota.
- **Safe result category:** a short code such as valid, rejected, or temporarily unavailable, not the provider's raw response.
- **Request ID:** this service's correlation reference. A **provider request ID** is the provider's support reference, when supplied.
- **Customer-managed key:** belongs to the customer's provider account. **Platform-managed key:** belongs to the platform's provider account. The backend explicitly chooses the permitted source; the service never substitutes one for the other.
- **Replacement / rotation:** changing to a new key value. The backend owns saving and activating it; this service validates and uses the selected version.

## 6. Scope boundary and unresolved dependency

This feature does not build sign-in, organizations, workspace roles, credential CRUD/UI, cloud provisioning, billing, recovery scheduling, or a new audit platform. It also does not promise a particular deployment topology, retention period, availability percentage, latency target, or provider rollout sequence.

The backend schema/API and secure retrieval mechanism have not been supplied. The [backend contract](technical-design.md) records the decisions needed before live integration. The [plan](delivery-plan.md) allows separately approved mock-based work without pretending that dependency is resolved. Detailed acceptance tests are in the [test plan](acceptance-tests.md), not embedded here.

## 7. Review-to-implementation boundary

The technical design's L1-L8 decisions specify the multimodal module's interfaces, architecture, first adapter, limits, compatibility, test doubles and handoff. T1 accepts or amends that package; approved T2-T4 tasks then produce actual implementation tested without external services (M1). This is not merely a mock prototype: the provider adapter and orchestration are real code, exercised through simulated transports. Actual credential retrieval/service authentication and safe live wiring remain T5-T7 (M2).

The short PRD remains provider-independent. Numerical defaults and implementation filenames belong in the design, not duplicated here. No unknown backend endpoint, database, deployment or authorization mechanism is made up to label the documentation complete.
