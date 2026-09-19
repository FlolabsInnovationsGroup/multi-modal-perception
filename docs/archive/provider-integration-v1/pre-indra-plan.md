> **SUPERSEDED — HISTORICAL ONLY (2026-09-18).** Do not use this document to direct implementation. All approval and phase statements below belong to the previous scope. See [current documentation](../../provider-integration/README.md).

# BYOK Credential Broker Delivery Plan

## Document control

| Field | Value |
| --- | --- |
| Status | Active implementation tracker |
| Product specification | `docs/byok-credential-broker-prd.md` |
| Current phase | Phase 0 — security and architecture gate |
| Current implementation state | Target architecture not implemented |
| Last updated | 2026-08-08 |
| Status authority | Human-approved evidence only |

## How to use this plan

This file defines delivery order and status; it does not replace the PRD. Work only on tasks whose entry criteria are satisfied. Complete tasks in order unless a human approves a change with documented rationale.

Status values are `Not started`, `In progress`, `Blocked`, `Ready for review`, and `Complete`. `Complete` requires named evidence. AI may propose a status update but must not record human approval that did not occur.

## Current-state baseline

Verified repository findings:

- FastAPI exposes unauthenticated `/health`, `/process`, and `/openAI` routes.
- OpenAI usage is based on a process-global client and one environment key.
- An in-memory cross-request prompt cache has no tenant boundary.
- Provider exceptions can produce a silent input-echo response.
- There is no authentication, tenancy, PostgreSQL persistence, migration framework, audit system, test suite, Terraform, CI/CD, or deployment definition in this repository.
- The companion frontend is outside this repository.

The existing service is a prototype baseline, not a secure BYOK implementation.

## Global delivery rules

- Follow root `AGENTS.md` and all mandatory approval gates.
- OpenAI is first; Anthropic, Gemini, and Azure OpenAI are later roadmap phases.
- Do not use real credentials until approved staging infrastructure and the real-credential gate exist.
- Do not combine dependency approval, schema approval, AWS approval, deployment approval, or Git approval.
- Every completed task updates the traceability matrix with code, tests, and evidence.
- Any material architecture change requires an ADR and human approval.
- No phase may bypass unresolved critical threat-model findings.

## Phase 0 — Security and architecture gate

**Goal:** Validate the security boundary, tenancy design, AWS design, provider obligations, delivery controls, and implementation sequence before code or infrastructure work.

**Entry criteria:** Approved PRD and read-only repository baseline. Met.

| ID | Task | Status | Required evidence |
| --- | --- | --- | --- |
| P0-01 | Establish repository AI instructions and document governance | Complete | `AGENTS.md`, `CLAUDE.md`, `docs/README.md` |
| P0-02 | Record current data flow and target trust boundaries | Ready for review | `docs/architecture/byok-data-flow.md` |
| P0-03 | Produce threat model and abuse-case review | Ready for review | `docs/architecture/byok-threat-model.md` |
| P0-04 | Define AWS topology, IAM, KMS, network, persistence, deletion, and recovery design | Ready for review | `docs/architecture/byok-aws-design.md` |
| P0-05 | Confirm product and service role permissions | Ready for review | `docs/architecture/byok-role-permission-matrix.md` |
| P0-06 | Review OpenAI provider terms/data controls and establish later-provider review template | Ready for review | `docs/architecture/byok-provider-terms-review.md` |
| P0-07 | Record the approved architectural constraints | Ready for review | ADR-001 through ADR-005 |
| P0-08 | Establish requirement-to-task/test/evidence traceability | Ready for review | `docs/requirements/byok-traceability-matrix.md` |
| P0-09 | Assign human owners and resolve blocking placeholders | Not started | Named product, security, architecture, legal, operations, and AWS owners |
| P0-10 | Obtain the Phase 0 architecture/security/legal gate decision | Not started | Dated human approval or documented changes required |

**Exit criteria:** P0-02 through P0-09 reviewed; all critical threats have an accepted control or explicit risk decision; provider obligations reviewed; architecture and security approvers explicitly authorize Phase 1 planning.

**Gate:** Phase 0 document creation is not approval to install dependencies, create schemas/migrations, provision AWS, use credentials, or deploy.

## Phase 1 — Authentication and tenancy foundation

**Goal:** Build invite-only organizations/workspaces, Cognito token validation with mandatory MFA, authoritative memberships, and enforceable RBAC.

**Entry criteria:** Phase 0 exit approval; dependency proposal approved; schema design approved; migration action separately approved.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P1-01 | Propose dependency and environment changes | Not started | Versions, rationale, security/cost impact, approval |
| P1-02 | Define API and persistence contracts for users, organizations, workspaces, memberships, and invitations | Not started | PRD sections 5, 9, and 10 |
| P1-03 | Create migration framework and initial schema after migration approval | Not started | Constraints, rollback, RLS preparation |
| P1-04 | Implement Cognito JWT validation and mandatory-MFA enforcement | Not started | Issuer, audience/client, signature, expiry, token use, MFA claims |
| P1-05 | Implement invitation and membership lifecycle | Not started | Invite-only onboarding, expiry, single use, audit |
| P1-06 | Implement centralized RBAC and workspace authorization | Not started | Owner/admin/member matrix and deny-by-default |
| P1-07 | Enable and test PostgreSQL tenant isolation/RLS | Not started | Cross-workspace denial under adversarial tests |

**Exit criteria:** Authentication, membership, RBAC, relational constraints, and RLS tests pass; no unauthenticated access to new `/v1` workspace APIs; migration and rollback evidence recorded.

## Phase 2 — AWS Credential Broker foundation

**Goal:** Provision the private broker boundary and secure secret storage through reviewed Terraform.

**Entry criteria:** Phase 1 complete; Terraform and AWS resource proposal approved; accounts, region, budget, IAM, and network owners resolved.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P2-01 | Design Terraform module interfaces and environment separation | Not started | Reproducibility, state security, naming, tags, rollback |
| P2-02 | Implement network, ECS, RDS, Cognito, KMS, Secrets Manager, logging, and alarms in Terraform | Not started | No resource creation until separate apply approval |
| P2-03 | Implement private service authentication between API and broker | Not started | Deny untrusted callers and replay |
| P2-04 | Enforce IAM/KMS/Secrets Manager least privilege | Not started | Application API cannot read/decrypt; broker is resource-scoped |
| P2-05 | Enforce approved-provider egress and private AWS service access | Not started | VPC endpoints, HTTPS, DNS/redirect policy, no arbitrary egress |

**Exit criteria:** Terraform validation/security review passes; IAM negative tests are designed; cost estimate accepted; an approved staging apply and rollback test complete.

## Phase 3 — OpenAI credential lifecycle

**Goal:** Add write-only OpenAI credential ingestion, validation, versioning, rotation, disablement, and deletion.

**Entry criteria:** Phase 2 staging foundation verified; approved synthetic/staging credential and real-credential action approval.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P3-01 | Implement credential metadata and version schema | Not started | Tenant ownership, one active version, safe metadata only |
| P3-02 | Implement write-only create and metadata-only retrieval | Not started | No plaintext read-back; redaction and request-body logging disabled |
| P3-03 | Implement disclosed minimal OpenAI validation | Not started | Capability-specific, rate-aware, safe error handling |
| P3-04 | Implement atomic rotation | Not started | Failed validation preserves prior active version |
| P3-05 | Implement immediate disablement and scheduled deletion | Not started | Seven-day recovery window and audit trail |

**Exit criteria:** Lifecycle, concurrency, tenant-isolation, secret-leakage, and recovery tests pass with only approved staging credentials.

## Phase 4 — Brokered OpenAI invocation

**Goal:** Replace global credential execution with request-scoped, authorized provider execution through the broker.

**Entry criteria:** Phase 3 complete; provider adapter contract reviewed; model catalog seeded through an approved process.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P4-01 | Implement normalized provider adapter interface | Not started | Validation, text, transcription, usage, errors, provider request IDs |
| P4-02 | Implement model catalog and workspace allowlist | Not started | No arbitrary model identifiers |
| P4-03 | Implement `/v1/workspaces/{workspace_id}/process` | Not started | Authn, membership, policy, credential source, broker call |
| P4-04 | Remove process-global credential/client assumptions from new flow | Not started | Request-scoped client execution and plaintext lifetime |
| P4-05 | Remove cache and silent echo behavior from provider execution | Not started | Safe normalized failures and no content retention |
| P4-06 | Implement usage and safe operational events | Not started | No prompts, audio, transcripts, responses, or secrets |

**Exit criteria:** Functional and adversarial invocation tests pass; invalid/disabled/deleted/rate-limited credentials never cause fallback; platform overhead meets the staged performance gate.

## Phase 5 — Product APIs and companion UI contract

**Goal:** Complete versioned management APIs and a frontend-safe contract for credential, policy, audit, and usage experiences.

**Entry criteria:** Phase 4 stable API behavior; frontend owner assigned.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P5-01 | Publish and validate the OpenAPI contract | Not started | PRD section 10, normalized errors, write-only fields |
| P5-02 | Implement policy, audit, and usage APIs | Not started | Tenant scoping, pagination, safe metadata |
| P5-03 | Specify and review companion UI states | Not started | Masking, validation, rotation, disable/delete confirmations |
| P5-04 | Verify frontend secret-handling controls | Not started | No storage, analytics, replay, support, or body logs |

**Exit criteria:** API contract tests pass; companion frontend team accepts the contract; security review confirms credential fields cannot be persisted or revealed.

## Phase 6 — Hardening and operational readiness

**Goal:** Make the system supportable, recoverable, auditable, and measurable.

**Entry criteria:** Product flows complete in staging.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P6-01 | Implement safe dashboards, metrics, alerts, and immutable audit export | Not started | SLOs, secret-safe labels, evidence retention |
| P6-02 | Complete incident, compromise, revocation, backup/restore, and break-glass runbooks | Not started | Named owners and exercised procedures |
| P6-03 | Execute adversarial and secret-leakage test program | Not started | IDOR, RLS, IAM/KMS denial, logs, traces, backups |
| P6-04 | Execute load, availability, recovery, and rollback tests | Not started | 100 concurrent requests and 250 ms p95 platform overhead target |
| P6-05 | Complete production security and operational review | Not started | No unresolved critical/high risk without acceptance |

**Exit criteria:** Release acceptance criteria in PRD section 17.7 pass, runbooks are exercised, restore and rollback evidence exists, and owners accept residual risk.

## Phase 7 — Controlled rollout and legacy migration

**Goal:** Release safely through feature flags and retire unauthenticated legacy routes.

**Entry criteria:** Phase 6 approval; deployment action separately approved; design partners and support plan confirmed.

| ID | Task | Status | Acceptance focus |
| --- | --- | --- | --- |
| P7-01 | Internal feature-flag rollout | Not started | SLO/security monitoring and rollback |
| P7-02 | Selected design-partner rollout | Not started | Tenant isolation, support, provider terms, consent |
| P7-03 | Announce and monitor 30-day legacy migration | Not started | Caller inventory and customer communication |
| P7-04 | Remove public legacy routes after approval | Not started | No remaining callers; rollback tested |
| P7-05 | General-availability decision | Not started | Product, security, legal, operations, and SLO signoff |

**Exit criteria:** Approved production rollout, legacy endpoints retired, rollback path retained, and success metrics reported.

## Human decisions and ownership register

| Decision/owner | Needed by | Status |
| --- | --- | --- |
| Product owner | Phase 0 exit | `TBD` |
| Architecture approver | Phase 0 exit | `TBD` |
| Security approver and reporting channel | Phase 0 exit | `TBD` |
| Legal/provider-terms reviewer | Phase 0 exit | `TBD` |
| Operations/incident owner | Phase 2 | `TBD` |
| Database/migration owner | Phase 1 | `TBD` |
| AWS accounts and primary region | Phase 2 | `TBD` |
| Cost budget and alarm thresholds | Phase 2 | `TBD` |
| Approved MFA factors and recovery policy | Phase 1 | `TBD` |
| Approved OpenAI project/data controls/models | Phase 3 | `TBD` |
| Frontend contract owner | Phase 5 | `TBD` |
| Design partners and rollout dates | Phase 7 | `TBD` |

## Status update rules

For every task moved to `Complete`, record in the traceability matrix:

- Requirement identifiers and acceptance criteria.
- Implementation files and migration/IaC identifiers.
- Automated and manual tests with results.
- Security review evidence.
- Human approval when an exit gate requires it.

If evidence is unavailable, use `Ready for review`, `Blocked`, or `Not started`; never use `Complete` for planned work.
