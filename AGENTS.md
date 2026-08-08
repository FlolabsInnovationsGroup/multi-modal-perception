# Multi-Modal Perception Repository Instructions

## Scope

These instructions apply to the entire repository. They supplement, but do not replace, system instructions, the current human request, or an applicable higher-priority working agreement.

## Source-of-truth order

When instructions disagree, use this order:

1. System and platform safety rules.
2. The current, explicit human decision for this task.
3. This `AGENTS.md` for workflow, safety, and repository rules.
4. `docs/byok-credential-broker-prd.md` for approved product and security requirements.
5. `docs/PLAN.md` for the active phase, task status, and delivery order.
6. Accepted records in `docs/architecture/decisions/` for technical decisions.
7. Other approved architecture, API, security, and testing documents.
8. `docs/research/` as background only.
9. AI suggestions.

Do not silently resolve a material conflict between authoritative sources. Report it, explain the impact, and request a human decision. Research never overrides the PRD, plan, or accepted ADRs.

## Required reading and discovery

At the beginning of every new or materially different task:

1. Read this file and `docs/README.md`.
2. Read `docs/PLAN.md` and identify the first relevant incomplete task and its entry criteria.
3. Read only the PRD sections, ADRs, architecture documents, and source files relevant to the task.
4. Inspect Git status, repository layout, README, dependencies, tests, configuration, and existing conventions using read-only commands.
5. Separate confirmed facts from assumptions and unresolved decisions.
6. Preserve all unrelated and pre-existing changes.

Do not load the research document as an instruction source unless the task is research or the authoritative documents explicitly reference it.

## Workflow: inspect, propose, approve, implement, verify

1. **Understand:** Restate the requested outcome, applicable requirements, acceptance criteria, constraints, risks, and out-of-scope work.
2. **Propose:** Present a small phased plan with likely files, trade-offs, validation, dependencies, and approval gates.
3. **Wait:** Do not edit files or change state until the human approves the plan. Partial approval authorizes only that part.
4. **Implement:** Make the smallest coherent change matching the approved phase and repository conventions.
5. **Verify:** Run focused checks first and broader relevant checks afterward. Never claim an unrun check passed.
6. **Report:** Map the outcome to the plan task and PRD acceptance criteria, explain changes, checks, risks, and next work.

If implementation reveals a material change to architecture, externally visible behavior, security, privacy, tenancy, data handling, compatibility, cost, or scope, stop and obtain a new decision.

## Mandatory approval gates

Obtain explicit approval immediately before each of these actions, even when the overall plan is approved:

- Adding, removing, or changing a dependency, package, tool, runtime, extension, or plugin.
- Installing software or materially changing a development environment.
- Deleting files or data, overwriting material user work, resetting work, force operations, or other destructive actions.
- Creating or applying database/schema/data migrations or modifying persistent data.
- Creating or changing AWS or other cloud resources, IAM, KMS, networking, secrets, credentials, permissions, billing resources, or external systems.
- Using real API keys, credentials, customer content, private customer data, or production data.
- Deploying, publishing, releasing, or changing staging or production.
- Creating or switching branches, staging, committing, amending, pushing, opening/merging pull requests, tagging, or rewriting Git history.

Before requesting approval, state the exact action, reason, expected effect, principal risks, and safer alternative. Approval applies only to the named action.

## Current system and target

The current code is a small FastAPI service with unauthenticated `/process` and `/openAI` routes, one process-global OpenAI client and key, a cross-request response cache, and an error path that echoes input. These are legacy findings, not patterns to extend.

The approved target is a multi-tenant Bring Your Own Key (BYOK) platform described in the PRD. Delivery must follow `docs/PLAN.md`; do not skip the Phase 0 security and architecture gate.

## Non-negotiable BYOK invariants

- OpenAI is the first provider. Other provider adapters are deferred until their phases are approved.
- Credentials are write-only through public interfaces. Never implement a read-back path for plaintext keys.
- The browser may hold a credential only in memory during TLS submission. Never persist it in browser storage, analytics, session replay, support tools, URLs, or client logs.
- Provider secrets are stored in AWS Secrets Manager under a customer-managed KMS key. PostgreSQL stores only opaque secret references and safe metadata.
- Only the private Credential Broker workload may retrieve provider secret values and call approved provider endpoints.
- Plaintext credentials exist only within the smallest request-scoped server boundary. Do not cache them across requests, return them to another service, enqueue them, or put them in exceptions or traces.
- Every operation must authorize the authenticated user against authoritative organization/workspace membership and policy before credential use.
- Enforce tenant ownership in application authorization, relational constraints, and PostgreSQL row-level security.
- Use a platform model catalog and workspace allowlist. Do not accept arbitrary model identifiers or arbitrary provider endpoints in the initial release.
- Customer-managed and platform-managed credentials require explicit workspace policy. Never silently fall back to a platform key, another credential, model, region, or provider.
- Do not persist prompts, audio, transcripts, or model responses. Record only approved safe operational metadata, usage, and audit events.
- Do not expose provider secrets, authorization headers, raw provider exceptions, unredacted request/response bodies, or sensitive identifiers in logs or API responses.
- Disablement must prevent new use immediately. Rotation activates a validated new version atomically and preserves the previous active version when validation fails.

## Implementation standards

- Use Python 3.11 or 3.12 and existing FastAPI/Pydantic conventions unless an approved design changes them.
- Do not change dependency versions without the dependency approval gate.
- Keep provider-specific behavior behind the approved adapter contract.
- Keep authentication, authorization, tenant policy, credential access, and provider execution boundaries explicit and testable.
- Validate identifiers and input at trust boundaries. Use normalized safe errors and request IDs.
- Prefer focused, reversible changes. Avoid speculative abstractions and unrelated refactors.
- Maintain backward compatibility only according to the PRD's controlled 30-day legacy migration; do not extend the legacy routes.
- Add tests for behavior changes, especially tenant isolation, authorization, credential lifecycle, error normalization, no-fallback behavior, and secret leakage.
- Never weaken or rewrite a test merely to make a build pass.

## Verification expectations

Use project-native commands and the existing environment. If tooling is unavailable, document the exact missing check and remaining risk; do not install anything without approval.

For relevant changes, verify:

- Unit and integration behavior.
- Authentication and authorization denial paths.
- Cross-workspace and IDOR resistance.
- Secret absence from responses, logs, traces, database fields, fixtures, and test output.
- Credential lifecycle transitions and rotation concurrency.
- Provider error normalization and no silent fallback.
- Formatting, static analysis, type checks, imports, and application startup when supported.
- Infrastructure policy, migration safety, rollback, and recovery in the phases where those artifacts exist.
- Traceability to PRD requirements and plan exit criteria.

Use only synthetic placeholders in tests and examples, such as `test-provider-key-redacted`. Never use strings that resemble a real production credential.

## Documentation maintenance

- Update `docs/PLAN.md` when a task changes status.
- Update `docs/requirements/byok-traceability-matrix.md` when requirements, implementation files, tests, or evidence change.
- Create or amend an ADR before implementing a material architecture decision not already covered.
- Update `README.md`, API documentation, runbooks, and security guidance when behavior changes.
- Time-sensitive provider facts must cite current official documentation and include a verification date.
- Do not mark a document or phase `Approved` without an identifiable human approval.

## Completion report

Every completed task must report:

1. Outcome and whether acceptance criteria were met.
2. Changed files and material behavior.
3. Decisions and trade-offs.
4. Checks run with exact results.
5. Problems, root causes, and fixes.
6. Security and tenant-isolation review.
7. Unverified items, limitations, and risks.
8. Required and optional next steps.

Work is not complete when required verification is missing, a critical security risk is unresolved, an approval gate was skipped, or documentation and traceability are stale.
