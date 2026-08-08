# BYOK Documentation Index and Governance

## Purpose

This directory contains the governed requirements, delivery plan, architecture, decisions, research, and AI handoff material for the Bring Your Own AI Provider Key (BYOK) Credential Broker project.

The documentation package makes the intended product clear, but it does not mean the target system already exists. Current implementation status is tracked only in `PLAN.md`.

## Authority order

| Priority | Source | Authority |
| --- | --- | --- |
| 1 | Current explicit human decision | Controls the present task within system and safety constraints |
| 2 | Root `AGENTS.md` | Repository workflow, security rules, and approval gates |
| 3 | `byok-credential-broker-prd.md` | Approved product and security requirements |
| 4 | `PLAN.md` | Active phase, task order, entry/exit criteria, and status |
| 5 | Accepted ADRs | Approved implementation decisions |
| 6 | Approved architecture and security documents | Detailed design and control expectations |
| 7 | Research | Background and options only |
| 8 | AI suggestions | Proposals requiring evaluation and approval |

When authoritative documents conflict materially, stop and request a human decision. Do not treat the newest timestamp or the longest document as automatically authoritative.

## Status vocabulary

- **Approved:** An identified human has accepted the document or decision for implementation.
- **Accepted by PRD:** The decision records an already-approved PRD requirement; implementation remains subject to plan gates.
- **Draft for review:** Useful design work that cannot satisfy an exit gate until a human approves it.
- **Active:** Work may proceed because its entry criteria are met.
- **Blocked:** A named dependency or decision prevents safe progress.
- **Reference:** Background material that cannot direct implementation.
- **Superseded:** Retained for history but not applicable to new work.

AI must not upgrade a document's status without explicit human approval.

## Canonical documents

| Document | Status | Purpose | When AI reads it |
| --- | --- | --- | --- |
| [`byok-credential-broker-prd.md`](byok-credential-broker-prd.md) | Approved | Complete product, UX, API, architecture, security, rollout, and acceptance requirements | Relevant sections for every BYOK task |
| [`PLAN.md`](PLAN.md) | Active tracker | Delivery order, task IDs, approvals, and progress | Every task |
| [`architecture/byok-data-flow.md`](architecture/byok-data-flow.md) | Draft for review | Components, trust boundaries, and credential/invocation flows | Security, backend, infrastructure, and API tasks |
| [`architecture/byok-threat-model.md`](architecture/byok-threat-model.md) | Draft for review | Assets, threats, abuse cases, controls, and residual risks | Every security-sensitive design or implementation task |
| [`architecture/byok-aws-design.md`](architecture/byok-aws-design.md) | Draft for review | AWS topology, IAM, KMS, networking, persistence, and operations | Infrastructure and broker tasks |
| [`architecture/byok-role-permission-matrix.md`](architecture/byok-role-permission-matrix.md) | Draft for review | Human and service permissions | Authentication, authorization, UI, and operations tasks |
| [`architecture/byok-provider-terms-review.md`](architecture/byok-provider-terms-review.md) | Draft for legal/security review | Provider data handling and terms checkpoints | Provider onboarding and rollout decisions |
| [`architecture/decisions/`](architecture/decisions/) | Accepted by PRD | Records why major technical constraints exist | Tasks affected by each decision |
| [`requirements/byok-traceability-matrix.md`](requirements/byok-traceability-matrix.md) | Active tracker | Connects PRD requirements to plan work, tests, and evidence | Planning, implementation, review, and release |
| [`research/byok-provider-integration-research.md`](research/byok-provider-integration-research.md) | Reference | Governed summary of supplied research and its conflicts | Research tasks only, unless explicitly referenced |
| [`ai/implementation-start-prompt.md`](ai/implementation-start-prompt.md) | Approved template | Safe handoff prompt for Codex or Claude | First AI session on the branch |

Repository-level supporting policies are in `../SECURITY.md` and `../CONTRIBUTING.md`.

## Required reading by work type

### Any task

Read root `AGENTS.md`, this index, `PLAN.md`, Git status, and the relevant source files.

### Product or UX

Read PRD sections 4–7, the role matrix, affected ADRs, and traceability rows.

### Authentication, tenancy, database, or API

Read PRD sections 5–10 and 14–17, the data flow, threat model, role matrix, ADR-001, and affected traceability rows.

### Credential Broker or AWS

Read PRD sections 6, 8, 9, 12–18; the AWS design; threat model; ADR-002; and the security policy.

### Provider integration

Read PRD sections 6, 10, 11, 13, 17; ADR-003 and ADR-005; provider-terms review; and only then any relevant research.

### Operations or rollout

Read PRD sections 12–20, the AWS design, threat model, provider-terms review, plan gates, and traceability matrix.

## Keeping context accurate

- Provide AI a task ID, intended outcome, affected files, relevant PRD sections, ADRs, and acceptance evidence.
- Do not paste all documentation into every prompt. Repository-aware AI should open the named files itself.
- Keep research outside the default context unless investigating an unresolved question.
- Never include real secrets or customer data in documentation, prompts, examples, screenshots, or test output.
- Update the plan and traceability matrix in the same change that completes a task.

## Human-owned placeholders

The following cannot be invented by AI and must be resolved before their associated gate:

- Security owner and confidential reporting channel.
- Product owner, architecture approver, security approver, legal reviewer, and operations owner.
- Existing primary AWS region and accounts/environment boundaries.
- Cost budget and alert thresholds.
- Approved identity/email/SMS MFA configuration.
- Approved OpenAI account/project, data controls, models, capabilities, and staging credential.
- Design-partner workspaces and rollout dates.

These placeholders do not block Phase 0 analysis, but they block the applicable implementation or production gate.
