# FloBrain Backend -> Multimodal Integration Contract

Status: **Proposed contract; live integration blocked**. Updated 2026-09-18.
Basis: PRD PI-02, PI-03, PI-05, PI-07, PI-08, PI-12.

Indra's review says multimodal reads and validates API keys from storage populated by FloBrain and uses them for provider calls. The storage schema, retrieval protocol, and service identity mechanism have not been supplied. This document specifies the information and guarantees needed; it does not assert an existing endpoint, table, cloud service, or plaintext database design.

## Ownership

FloBrain authenticates users, authorizes their requested operation, selects the permitted credential/source, stores protected keys, manages lifecycle state, and persists accepted validation results. Multimodal authenticates the calling service, validates request/context binding, reads only the permitted key version, checks provider access when asked, invokes the model, and returns safe results.

Multimodal must not expose key-management or key-readback APIs to end users. It must not implement user-role logic independently of FloBrain. A private network or a field saying "authorized" is not service authentication.

## Required logical inputs

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

## Credential reader boundary

For approved local work, define a replaceable `CredentialReader` interface with a synthetic fake. It accepts verified operation context and a credential reference; it returns the exact scoped version/state/provider and a secret-bearing request-local value or a safe error. Secret-bearing objects must not serialize or appear in repr/logging.

The live reader may require database access or a backend-mediated interface; B1 decides this from the actual FloBrain implementation. Do not invent SQL, connection strings, URLs, or decryption keys. Direct database access, if selected, must use least-privilege scoped reads and the backend-approved decryption mechanism. Never treat encrypted database contents as permission to decrypt any tenant's record.

The service verifies returned scope/provider/version/state against trusted context. The reader must not enumerate credentials or automatically select a previous or platform key. A failure returns a safe failure, not an empty value that triggers environment-key fallback.

## Validation and lifecycle coordination

1. Backend registers a candidate and requests validation of that exact version.
2. Multimodal performs the approved provider-specific access check, with no customer content.
3. It returns version-bound `valid`, `rejected`, or `indeterminate`, plus a safe reason, check time, operation/model, and provider request ID if safely available.
4. Backend persists the result and alone decides atomic activation. It must reject stale results for a changed/deleted candidate.
5. Failed candidate validation leaves active selection unchanged. Multimodal never performs activation, deletion, recovery, or provider-account revocation.
6. Runtime retrieves/rechecks current permitted state for each operation; no cross-request secret cache.

No automatic validation scheduler or queue is in this scope. The initial proposal is explicit backend-requested validation. Transient failure returns indeterminate; the backend can request another attempt under its rate/cost policy. A future scheduler needs its own requirements.

Disablement/rotation races require B4's agreed ordering point. Target behavior: operations admitted after disablement cannot acquire/use that credential, and operations admitted after replacement use the new active version. Already-admitted calls may finish. A naive "read status then use later" check cannot by itself guarantee this under races. Agree atomic admission/version checking or another tested coordination mechanism before live use.

## Outputs to FloBrain

Return a model result for invocation, or validation result for a validation operation, together with bounded request ID, provider/model, operation, safe outcome, and available usage. Provider usage is not the invoice. Missing usage is null/unavailable, not zero. Provider request IDs are optional, size-limited, and permitted only after adapter sanitization.

No secret, secret fragment, raw provider body on error, SDK object, authorization header, internal storage path, or decryption details may be returned. Success content is delivered to the caller transiently, not stored in this service.

## Decision register: backend owner and lead must complete

| ID | Question / required artifact | Blocking point | Status |
| --- | --- | --- | --- |
| B1 | Actual protected storage schema/interface; direct scoped DB read or backend-mediated retrieval; encryption/decryption and least-privilege access owner | Real credential-reader implementation | Unresolved |
| B2 | Source and schema of trusted scope/credential/provider binding; support for customer/platform sources; authorization policy ownership | Live request contract | Unresolved |
| B3 | Service authentication, request integrity, expiry/replay handling, network exposure, secret-free failure responses | Any externally reachable BYOK path | Unresolved |
| B4 | Lifecycle states, version identifiers, activation ownership, atomic admission/disable/rotation ordering, stale validation result handling | Live lifecycle correctness | Unresolved |
| B5 | When validation is requested; approved check per operation, rate/cost limits, timeout/retry budget, and result persistence | Live validation | Unresolved |
| B6 | Existing consumers; exact route/transport and error status mapping; response compatibility, usage fields, migration and rollback | Exposed API changes / T4 contract approval | Unresolved |
| B7 | Input/upload/concurrency limits; content-spooling and telemetry controls; approved metadata retention and support owner | Integration/release safety | Unresolved |

For each decision record: owner, dated answer, reviewed specification link, approving people, and acceptance tests. No values, secrets, private dumps, or real customer payloads belong here.

## Handoff checklist

- [ ] Lead and backend owner agree B1-B7 and exact schemas/transport.
- [ ] Required permissions are scoped, reviewed, and separately approved before access.
- [ ] Denied/untrusted calls cannot reach the reader or provider.
- [ ] Cross-scope identifiers, stale authorization, and inactive versions are rejected.
- [ ] Pending validation cannot become normal invocation.
- [ ] Activation/disablement race tests cover the agreed consistency boundary.
- [ ] Logging, upload spooling, SDK failures, and backend outages do not expose secrets/content.
- [ ] Staging environment and any real-key use receive explicit approval.
