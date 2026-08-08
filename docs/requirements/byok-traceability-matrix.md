# BYOK Requirements Traceability Matrix

## Document control

| Field | Value |
| --- | --- |
| Status | Active tracker; implementation evidence pending |
| Requirement source | `docs/byok-credential-broker-prd.md` |
| Delivery source | `docs/PLAN.md` |
| Last updated | 2026-08-08 |

## Usage

This matrix gives stable project identifiers to the PRD's major requirements. The PRD remains authoritative. When a task is implemented, replace `Pending` evidence with concrete file paths, migration/IaC identifiers, test names, command results, and review records.

Do not mark a row `Verified` because code was written. Verification requires the listed acceptance evidence and applicable human gate.

Status values: `Specified`, `Implementing`, `Ready for review`, `Verified`, `Blocked`, or `Deferred`.

## Product, identity, and tenancy

| ID | PRD source | Requirement | Plan task(s) | Required verification/evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BYOK-001 | 5, 6.1 | Invite-only organizations containing workspaces | P1-02, P1-05 | Invitation expiry/single-use tests; organization/workspace API tests; audit events | Specified |
| BYOK-002 | 5.2–5.3 | Owner, workspace-admin, and member RBAC | P0-05, P1-06 | Complete endpoint/role allow-deny matrix | Specified |
| BYOK-003 | 6.1, 8 | Cognito authentication with mandatory MFA | P1-04 | Signature/issuer/audience/token-use/expiry/MFA negative tests | Specified |
| BYOK-004 | 5, 9 | PostgreSQL-authoritative membership and roles | P1-02, P1-03, P1-06 | Schema/migration review; stale/missing membership tests | Specified |
| BYOK-005 | 9, 14, 17 | Tenant isolation through application auth, constraints, and forced RLS | P1-03, P1-06, P1-07 | IDOR tests; composite FK tests; RLS tests using application role | Specified |
| BYOK-006 | 6.1, 10 | Authenticated versioned `/v1` administration APIs | P1-02, P5-01 | OpenAPI and contract tests; unauthenticated denial | Specified |

## Credential lifecycle and secret protection

| ID | PRD source | Requirement | Plan task(s) | Required verification/evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BYOK-010 | 6.2, 7.1, 10.2 | Credential value is write-only; metadata GET is masked | P3-02, P5-01 | Response/schema tests; synthetic canary scan | Specified |
| BYOK-011 | 6.2, 8 | Browser holds key only during TLS submission; no storage/analytics/replay | P5-03, P5-04 | Frontend contract review and browser instrumentation tests | Specified |
| BYOK-012 | 6.2, 8, 9 | Secret value only in Secrets Manager under customer-managed KMS key | P2-02, P2-04, P3-01 | Terraform/policy review; DB/backup inspection | Specified |
| BYOK-013 | 8.4, 14 | Only broker retrieves provider secrets; public API cannot decrypt | P2-03, P2-04 | IAM simulation and staging denied-action tests | Specified |
| BYOK-014 | 6.2, 8 | Plaintext retrieved once per in-flight request; no cross-request cache or return | P4-04 | Broker contract tests; memory/log/trace review; cache absence | Specified |
| BYOK-015 | 6.2, 9 | One active credential per workspace/provider | P3-01 | Partial unique constraint and concurrency tests | Specified |
| BYOK-016 | 6.3 | Disclosed minimal validation for each enabled capability | P3-03 | Validation contract, rate/cost disclosure, provider mock/staging tests | Specified |
| BYOK-017 | 6.4 | Atomic rotation; failed validation preserves previous active version | P3-04 | Concurrent rotation, validation failure, and transaction rollback tests | Specified |
| BYOK-018 | 6.5 | Disablement prevents new use immediately | P3-05 | Disable/invocation race tests and audit evidence | Specified |
| BYOK-019 | 6.5, 12.4 | Seven-day deletion recovery; backup limitation disclosed | P3-05, P6-02, P6-04 | Delete/restore exercise and retention configuration | Specified |

## Provider policy and invocation

| ID | PRD source | Requirement | Plan task(s) | Required verification/evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BYOK-020 | 6.6, 11 | Platform model catalog and workspace allowlist | P4-01, P4-02 | Unknown/disallowed model and capability tests | Specified |
| BYOK-021 | 6.7 | Explicit customer-managed/platform-managed source policy | P4-03, P5-02 | Policy transition and actual-source response/audit tests | Specified |
| BYOK-022 | 6.7, 14, 17 | No automatic credential/model/provider fallback | P4-03, P4-05, P6-03 | Invalid/disabled/deleted/quota/rate/outage no-fallback matrix | Specified |
| BYOK-023 | 11, 15 | OpenAI first through normalized adapter contract | P4-01 | Adapter contract and OpenAI mock/staging tests | Specified |
| BYOK-024 | 6.8, 10.3 | Generic workspace process endpoint replaces provider-specific public use | P4-03, P7-03, P7-04 | API contract; legacy usage telemetry; migration/removal evidence | Specified |
| BYOK-025 | 10.5, 11 | Normalize authn/authz/key/quota/rate/outage/policy/config errors safely | P4-01, P4-03 | Error contract tests and raw-exception leakage scan | Specified |
| BYOK-026 | 4.2, 6.6, 14 | Arbitrary endpoints and arbitrary model IDs prohibited | P2-05, P4-02 | SSRF/redirect/DNS/private-address and unknown-ID tests | Specified |
| BYOK-027 | 11 | Extract provider request ID and usage safely | P4-01, P4-06 | Adapter parsing tests and absent/malformed usage behavior | Specified |

## Content, audit, operations, and reliability

| ID | PRD source | Requirement | Plan task(s) | Required verification/evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BYOK-030 | 6.8, 12.3 | No platform persistence of prompts/audio/transcripts/responses | P4-05, P4-06, P6-03 | Schema/cache/repository scan; content canary across logs/backups | Specified |
| BYOK-031 | 12.1–12.2 | Safe credential/security audit events | P4-06, P5-02, P6-01 | Event contract, actor/outcome tests, no-secret scan | Specified |
| BYOK-032 | 12.4 | Audit 12 months, logs 30 days, backups at most 35 days | P6-01, P6-04 | Retention configuration and expiry/restore evidence | Specified |
| BYOK-033 | 13 | 99.9% monthly availability target | P6-01, P6-04 | SLI/SLO definition, alarms, staged availability evidence | Specified |
| BYOK-034 | 13 | No more than 250 ms p95 platform overhead excluding provider latency | P6-04 | 100-concurrent-request load test with latency decomposition | Specified |
| BYOK-035 | 13, 18 | Safe metrics, dashboards, alarms, and provider/request correlation | P6-01 | Observability review and secret-safe label/cardinality tests | Specified |
| BYOK-036 | 18 | Compromise, outage, revocation, backup/restore, and break-glass runbooks | P6-02 | Named owners and tabletop/staging exercises | Specified |
| BYOK-037 | 8, 17 | Multi-AZ RDS and tested backup/restore/Terraform rollback | P2-02, P6-04 | Approved staging apply, failover/restore, rollback evidence | Specified |
| BYOK-038 | 12, 18 | CloudTrail and immutable audit export | P2-02, P6-01 | Delivery/integrity/access tests | Specified |

## Rollout and governance

| ID | PRD source | Requirement | Plan task(s) | Required verification/evidence | Status |
| --- | --- | --- | --- | --- | --- |
| BYOK-040 | 15–16 | Phase gates and separate approvals for dependencies, migrations, AWS, credentials, deployment | All phases | Approval records linked to each action | Specified |
| BYOK-041 | 15.7, 17.7 | Feature-flagged internal then design-partner rollout | P7-01, P7-02 | Workspace flag tests, SLO/security review, rollback | Specified |
| BYOK-042 | 10, 15.7 | 30-day legacy API deprecation and monitored removal | P7-03, P7-04 | Caller inventory, notice, zero callers, removal/rollback | Specified |
| BYOK-043 | 7, 12, 20 | Accurate customer UX/policy for masking, validation cost, source, deletion, and provider handling | P5-03, P5-04, P7-02 | Product/legal-approved copy and UI acceptance tests | Specified |
| BYOK-044 | 17 | Use only approved staging credentials; no real secrets in fixtures/CI/history/output | P3-03 onward | Secret scan and credential-handling review | Specified |
| BYOK-045 | 17 | Adversarial tenant, IAM/KMS, replay, admin-compromise, and leakage testing | P6-03 | Security test report with all critical findings resolved | Specified |

## Evidence record template

When a requirement becomes verified, append or link an evidence record containing:

```text
Requirement ID:
Plan task:
Implementation files:
Migration/IaC identifiers:
Automated tests and result:
Manual/security checks and result:
Approval/gate record:
Known limitations/residual risk:
Verified date and reviewer:
```

Production release requires every non-deferred release requirement to be `Verified`, with no unresolved critical risk and explicit Phase 6/7 approvals.
