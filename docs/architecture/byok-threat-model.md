# BYOK Credential Broker Threat Model

## Document control

| Field | Value |
| --- | --- |
| Status | Draft for security review |
| Method | Asset/trust-boundary analysis, STRIDE, and abuse cases |
| PRD basis | Sections 6, 8, 12, 14, 17, and 18 |
| Last updated | 2026-08-08 |

## Security objectives

1. A provider credential is usable only for its owning workspace and approved policy.
2. Database or backup compromise alone cannot recover credential values.
3. The public API and ordinary application roles cannot retrieve or decrypt provider secrets.
4. Plaintext credentials never cross the broker boundary or enter logs, traces, queues, caches, errors, or responses.
5. Provider choice, model, region, and credential source are explicit and auditable.
6. A failed BYOK request never silently transfers cost or data to a platform key or another provider.
7. Disablement and deletion stop new use according to the documented lifecycle.
8. Customer content is transient in the platform and not persisted.

## Actors

- Legitimate member, workspace administrator, and organization owner.
- Compromised or malicious member.
- Compromised administrator account.
- External unauthenticated attacker.
- Attacker with a database dump or backup.
- Compromised public API workload.
- Compromised broker workload.
- Malicious or unavailable provider/network party.
- Operator or support user with excessive access.
- CI/CD or observability system accidentally collecting secrets.

## Assets and impact

| Asset | Confidentiality impact | Integrity impact | Availability/cost impact |
| --- | --- | --- | --- |
| Provider API key | Provider account takeover and customer exposure | Unauthorized model use | Direct customer charges, quota exhaustion |
| Membership and role | Tenant information exposure | Privilege escalation | Workspace lockout |
| Workspace policy/model catalog | Data sent to wrong provider/model/region | Undisclosed fallback or routing | Unexpected cost/outage |
| Prompt/audio/response | Customer-content disclosure | Response manipulation | Business/privacy harm |
| Audit/usage data | Operational intelligence exposure | Evidence tampering | Incident-response and billing disputes |
| IAM/KMS/broker identity | Broad secret compromise | Unauthorized credential operations | Platform-wide outage/cost |

## STRIDE threat register

| ID | Category | Threat or abuse case | Primary controls | Verification | Residual risk |
| --- | --- | --- | --- | --- | --- |
| TM-01 | Spoofing | Forged, expired, wrong-audience, or non-MFA Cognito token | Standards-based JWT validation; issuer/audience/token-use/expiry checks; MFA policy; deny by default | Token-negative tests | Token revocation timing and Cognito configuration errors |
| TM-02 | Elevation | Member calls owner/admin credential API | Central RBAC; role matrix; route-level policy; audit | Role matrix tests for every endpoint | Compromised admin retains authorized destructive power |
| TM-03 | Information disclosure | IDOR accesses another workspace's credential metadata or usage | Membership lookup; tenant-scoped queries; composite FKs; RLS | Cross-workspace adversarial tests | RLS/policy misconfiguration |
| TM-04 | Information disclosure | Database/backup exposes provider keys | Secret values only in Secrets Manager; RDS stores opaque ARN; KMS separation | Schema inspection; restore inspection; IAM denial | Correlated metadata remains sensitive |
| TM-05 | Information disclosure | Key leaks through request logs, exception, trace, analytics, replay, or support tool | Body logging disabled; field allowlists; redaction; no raw HTTP dumps; frontend exclusions | Automated canary secret scans | Unknown third-party instrumentation defaults |
| TM-06 | Elevation | Public API retrieves or decrypts a secret directly | API IAM explicit deny/absence; only broker role has resource-scoped access; KMS via-service conditions | IAM simulation and live denial tests | Broker compromise remains high impact |
| TM-07 | Spoofing | Untrusted service calls broker | Private inbound; workload identity; authenticated/authorized internal request; anti-replay controls | Unauthorized caller/replay tests | Identity-system compromise |
| TM-08 | Tampering | Caller swaps workspace, credential, provider, or model identifiers after authorization | Server-derived bindings; broker revalidation; signed/authenticated internal context; transactional policy lookup | Parameter-tampering tests | TOCTOU during concurrent policy changes |
| TM-09 | Information disclosure | Broker returns plaintext key to API or includes it in error | Broker contract never returns credential; normalized errors; safe serializers | Contract and error-path scans | Runtime memory/process compromise |
| TM-10 | Denial/cost | Attacker validates repeatedly or exhausts provider quota | Rate limits, authorization, validation cooldown, quotas, alarms, audit | Rate/abuse tests | Authorized admin can still create cost |
| TM-11 | Tampering/cost | Invalid BYOK silently falls back to platform key/provider | Explicit workspace policy; no-fallback default; response metadata identifies actual source | Invalid/disabled/quota/outage tests | Human misconfiguration of explicit fallback later |
| TM-12 | SSRF | User-controlled endpoint reaches metadata, loopback, or private network | No arbitrary endpoints; provider allowlist; HTTPS; redirect/DNS controls; provider-only egress | URL/redirect/DNS adversarial tests | Provider DNS/CDN changes require maintenance |
| TM-13 | Tampering | Concurrent rotations create two active credentials or lose working key | Unique active constraint; transaction/locking; validate-before-switch | Concurrency and rollback tests | Provider revokes old key externally during rotation |
| TM-14 | Repudiation | Admin denies adding, rotating, disabling, or deleting a credential | Actor/request/workspace audit; immutable export; synchronized time | Audit integrity/replay tests | Compromised identity can perform authorized action |
| TM-15 | Information disclosure | Secrets Manager names/tags reveal tenant or key fragments | Opaque random naming; no customer/key data in names, descriptions, or tags | Resource metadata inspection | ARN itself remains confidential metadata |
| TM-16 | Availability | KMS, Secrets Manager, broker, RDS, or provider outage | Multi-AZ RDS; health/alarms; explicit normalized outage; no fallback; runbooks | Failure injection and recovery tests | External provider/AWS regional dependency |
| TM-17 | Information disclosure | Customer content persists in cache/database/log/backup | Remove response cache; no content columns; body logging disabled; retention scans | Repository/schema/log/backup scans | Provider may retain data under its own terms |
| TM-18 | Tampering | Model identifier bypasses catalog or calls unapproved capability | Server model catalog, workspace allowlist, capability validation | Unknown-model/capability tests | Catalog staleness |
| TM-19 | Denial | Oversized audio/body consumes memory or provider cost | Content length/type limits, streaming upload strategy, timeouts, concurrency controls | Boundary/load tests | Legitimate large inputs may be rejected |
| TM-20 | Elevation | Operator/support personnel view or use customer key | No plaintext UI/API; least-privilege operational roles; break-glass audit | Operator access tests | AWS account-level administrator risk |
| TM-21 | Tampering | Deleted/disabled credential used by stale cache or in-flight lookup | No cross-request secret cache; state recheck before retrieval; deletion semantics | Disable-race tests | Already-sent provider request may complete |
| TM-22 | Supply chain | Dependency/CI compromise exfiltrates secrets | Pinned/reviewed dependencies, minimal build secrets, scanning, isolated deploy role | Dependency and pipeline review | Upstream zero-day risk |

## High-priority abuse cases

### Cross-workspace credential use

An authenticated user changes `workspace_id` or `credential_id` to a tenant they do not belong to. The API must reject before metadata access; RLS and broker binding checks provide independent defenses. Audit safe denial metadata without revealing whether the target exists.

### Credential exfiltration through diagnostics

An attacker submits a malformed key that causes an SDK, proxy, or exception handler to dump authorization headers or request bodies. The broker must use safe exception mapping and field-allowlisted logging. Tests should inject a synthetic canary and search responses, logs, traces, database records, and artifacts.

### Compromised administrator

An attacker with a valid workspace-admin session adds their key, rotates the customer key, or disables service. Mandatory MFA and auditing reduce risk but cannot remove authorized power. Notifications, validation rate limits, owner-visible events, short sessions, and incident revocation are defense-in-depth candidates requiring product approval.

### Database-only compromise

The attacker obtains live tables and backups. They may learn tenant/provider associations and secret ARNs, but must not obtain credential values or KMS permissions. Opaque identifiers, secret-store separation, encrypted backups, and IAM boundaries limit impact.

### Broker compromise

The broker is the highest-value workload because it can retrieve active secrets. Resource-scoped IAM, provider-only egress, minimal runtime surface, no shell/debug endpoints, short-lived task credentials, alerting, and rapid revocation limit blast radius. A broker compromise remains a critical residual risk and requires an exercised runbook.

## Security test requirements

- Token forgery, wrong issuer/audience/client, expiry, missing MFA, and replay scenarios.
- Complete role/endpoint matrix, including absent membership and disabled user.
- IDOR and cross-tenant access for every tenant-owned identifier.
- RLS tests using the application's database role, not an owner/bypass role.
- IAM/KMS/Secrets Manager live denial tests for application and operator roles.
- Synthetic canary scans of HTTP responses, logs, traces, database, backups, test output, and crash paths.
- Rotation concurrency, validation failure, transaction failure, and disable/delete races.
- Arbitrary model/endpoint, redirect, DNS, private-address, and provider-host failure tests.
- Invalid, disabled, deleted, revoked, rate-limited, quota, timeout, and provider-outage no-fallback tests.
- Load/abuse limits for bodies, audio, validation, and concurrent provider calls.
- Backup restore, deletion recovery, audit immutability, alarm, and incident exercises.

## Risks requiring human acceptance before production

- Compromised broker or AWS account administrator can potentially access many customer credentials.
- Provider-side retention and regional processing depend on each customer's provider project and contractual controls.
- A request already sent upstream may incur cost after local cancellation or credential disablement.
- Mandatory MFA recovery and administrator account recovery create social-engineering and availability risk.
- Metadata retained for audit and backups remains sensitive even without plaintext keys or customer content.
- A 99.9% SLO depends on AWS and provider availability; no silent fallback means some provider outages correctly surface to customers.

## Review and maintenance

Security and architecture approvers must review this model at Phase 0 exit. Update it when adding a provider, endpoint mode, data type, streaming, tools, region, new trust boundary, or material AWS/IAM change. Critical or high risks require a control, a verified mitigation plan, or explicit risk acceptance.
