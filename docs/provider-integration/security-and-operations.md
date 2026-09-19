# Provider Integration Security and Operations

Revision 2.1, 2026-09-19. Status: ready for review. This combines the threat checklist, provider enablement review, and operational handoff. It does not assign backend/platform implementation to multimodal or authorize live access.

## Local implementation profile

The [technical design](technical-design.md) L1-L8 is the single source for exact proposed internal types, admission semantics, model/destination configuration, limits, probes and cleanup. Review these decisions in T1; don't replace them with guessed AWS settings or additional platform services. The [acceptance plan](acceptance-tests.md) lists local evidence separately from live controls.

M1 must enforce fail-closed injected boundaries, request-local sessions, bounded provider response streams, zero retries/redirects, secret-safe failures and no content writes. Current public upload routes remain unchanged and disconnected from the new module until a separate live integration task. In particular, cleaning up a temporary file after use is not the same as preventing content persistence; before a live route is enabled, its owner must prove bounded memory-only input handling before multipart spooling.

Only fixed validation probes defined in L6 may be used. No probe is free or a permanent guarantee of account access. The OpenAI API/SDK facts were checked against official documentation for this revision, as linked in L6; actual account permissions, applicable terms, provider retention settings, environment access and installed SDK compatibility are not verified by that documentation check.

## Security checklist

Status: ready for scoped review, 2026-09-18. Replaces the broad platform threat model.
Assets: provider keys, trusted authorization context, scoped credential references, transient content, and safe operational metadata.

| Risk | Required scoped control | Test / owner |
| --- | --- | --- |
| Forged backend caller or caller-supplied "authorized" field | Real service authentication and fresh bound context before reader/provider use | TC-02; joint B3 |
| Cross-customer reference substitution | Bind scope/provider/version/operation to context and verify reader result; deny enumeration | TC-02/03; joint B2 |
| Key exposure through diagnostics | Secret-safe types; no raw exceptions, bodies, auth headers, repr, request dumps, or trace payloads | TC-08; multimodal |
| Backend storage compromise or excessive reader permissions | Backend-approved encryption/decryption and least privilege; no guessed plaintext store | TC-13; backend B1 |
| Reuse of disabled or replaced key | No cross-request secret cache; agreed atomic admission/version semantics | TC-05/06; joint B4 |
| Stale validation activates wrong version | Result bound to exact candidate; backend rejects stale result and owns activation | TC-05; backend + multimodal |
| Hidden cost or data routing | Never switch key/source/provider/model/destination/region, including on error | TC-07; multimodal |
| SSRF or key sent to attacker | Configured destinations only, reviewed TLS/redirect behavior, no endpoint/header override | TC-09; multimodal + platform |
| Cross-request cached content/client | Remove global response cache from new flow; request-local secret-bearing clients | TC-03/08; multimodal |
| Temporary audio/content retention | Check framework spooling, failure cleanup, diagnostics, and upload limits | TC-08/12; multimodal + platform |
| Quota exhaustion / retries / resource exhaustion | Bounded validation/invocation, concurrency/input limits, no unreviewed SDK retries | TC-04/12; joint B5/B7 |
| Unauthenticated legacy route bypass | New credential path requires verified service context on every reachable entry point | TC-14; joint B3/B6 |
| Backend outage selects legacy environment key | Fail closed, never fall back to fake/global credentials | TC-13; multimodal |
| Provider failure leaked as raw details or echo success | Safe categories and explicit failure; no raw SDK details | TC-07/08; multimodal |

### Residual risks and boundaries

- A compromised credential-reading service can expose keys in its memory. Request-local handling reduces exposure; it does not guarantee physical zeroization.
- Backend authentication/storage decisions remain unknown. Do not claim database-only compromise cannot recover keys until B1's actual design proves that.
- Already-admitted provider operations may finish and incur cost after disablement/cancellation. B4 defines and tests the admission boundary.
- Provider retention and permissions depend on the chosen offering/account; this service's non-retention promise does not control the provider.
- "Internal service" does not mean automatically trusted. Production must not expose a key-reading path without B3 enforcement.

T1 reviews the local fake/module design. T5/T6 review the actual trust boundary and unresolved risks. Do not turn this checklist into an obligation for multimodal to implement the backend's identity, recovery, database, or infrastructure platform.

## Provider enablement review

Status: checklist for the provider implementation owner and appropriate product/security reviewers, 2026-09-18.
Not a legal opinion, a provider approval, or a fresh verification of provider terms. Earlier dated provider facts must not be reused as current.

Before a live provider integration, record:

| Check | Evidence required | Owner |
| --- | --- | --- |
| Authentication and destination | Official API documentation, approved authentication method, endpoint/region/deployment configuration | Provider engineer + backend/platform |
| Operations/models | Supported text/audio operations, model permissions, configuration and incompatibilities | Provider engineer |
| Validation | What access is proven, minimal synthetic check, quota/cost implications, limitations | Provider engineer + backend/product |
| Errors/retries/usage | Safe mappings, timeout/retry semantics, SDK defaults, nullable usage/request IDs | Provider engineer |
| Content handling | Provider-side retention/settings and endpoint options; no unsupported zero-retention promise | Appropriate product/security reviewer |
| Terms and billing | Applicable account agreement and permitted delegated key use; customer vs platform cost responsibility | Backend/product and legal owner where required |
| Lifecycle | Provider-side revocation is distinct from backend disablement; documented handoff | Backend/account owner |
| Readiness | Staging evidence, approved exact models/configuration, review date and official links | Lead + QA |

No UI, legal-review platform, or provider-account management implementation is assigned to multimodal. It supplies technical facts to the responsible team. Recheck official facts when adding a provider/model/operation or changing routing, authentication, SDK behavior, or data handling.

Provider sequence is in the plan. Do not assume that API compatibility makes an unreviewed provider supported.

## Operations and release

Status: ready for review, 2026-09-18. No deployment authorization.

### Failure handling

| Event | Multimodal behavior | Backend/platform action |
| --- | --- | --- |
| Key rejected / no permission | Safe error or rejected validation; no fallback | Review account permissions; manage replacement |
| Rate limit / quota / provider outage | Explicit category; no hidden provider/source switch | Apply approved retry/customer policy |
| Backend credential source unavailable | Fail closed; never use environment key or fake | Restore backend access |
| Key suspected exposed | Stop affected use through agreed disable/control path; preserve sanitized evidence | Security owner coordinates disable and provider-side revocation |
| Stale candidate validation | Return exact checked version; no activation | Reject stale result |
| Cancelled operation | Close local resources; no promise to undo upstream spend | Track safe partial usage if available |

Do not send keys or customer content to support. Use request ID, provider/model, safe category, timestamp, and approved scoped references. The service returns safe validation/usage metadata; backend owns persistence and platform owns retention. No seven-day recovery, 35-day backup, or 12-month audit commitment is inherited.

### Before live staging

- [ ] T1-T5 and B1-B7 approvals/evidence recorded.
- [ ] Service authentication and scoped reader permissions verified, including negative cases.
- [ ] Runtime destinations, models, timeouts, upload/concurrency limits, retry policy, and content-spooling controls recorded.
- [ ] Only approved staging keys through the agreed protected backend mechanism; separate approval before use.
- [ ] Provider enablement review completed with current official sources.
- [ ] Security owner, backend contact, release owner, and confidential reporting channel assigned.

### Release gate

Run TC-01 through TC-14 at the appropriate layers. Record actual results; mock success alone is insufficient. No unresolved critical/high credential-leakage or scope-isolation defect. Agree expected load and pass limits before measuring.

Enable for a small approved internal cohort first, check actual result/error/usage behavior and latency/resource use, then expand only with the release owner's authorization. Deployment and external changes need separate approvals.

B6 defines caller compatibility. Do not automatically remove `/process` or `/openAI`, publish a new workspace API, or start a fixed 30-day countdown.

### Rollback

Document and test the exact mechanism in the approved deployment environment: disable the new feature path or restore a known-safe release. Deny BYOK operations when disabled; never route them to the legacy shared platform key or echo fallback. Preserve backend credential state and sanitized evidence. Coordinate any existing-caller impact with the backend owner.

No new feature flags, cloud resources, or deployment tooling are created by this checklist. If the environment lacks a safe rollback mechanism, release remains blocked until its owner supplies one.
