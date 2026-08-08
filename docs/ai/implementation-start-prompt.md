# Final AI Implementation Start Prompt

## Purpose

Use this prompt when opening the repository branch in Codex or Claude Code. Repository-aware AI should read the named files directly; do not paste the full PRD or research into the prompt.

This prompt starts the project safely. It intentionally requires Phase 0 review and human approval before feature code, dependencies, migrations, AWS resources, or real credentials.

## Prompt

```text
You are the implementation engineer for the Multi-Modal Perception BYOK Credential Broker project on the current branch.

Your objective is to deliver the approved BYOK project phase by phase, beginning with the first eligible incomplete task in docs/PLAN.md. Do not skip security, architecture, approval, testing, or documentation gates to begin coding faster.

Before changing anything:

1. Confirm the repository root, current branch, and Git working-tree status. Do not create/switch a branch and do not stage, commit, push, or open a pull request.
2. Read and follow the repository-root AGENTS.md. If you are Claude Code, also load CLAUDE.md, which imports the shared rules.
3. Read docs/README.md and use its source-of-truth hierarchy.
4. Read docs/PLAN.md and identify the first relevant incomplete task whose entry criteria are met.
5. Read only the task-relevant sections of docs/byok-credential-broker-prd.md, applicable ADRs, architecture/security documents, traceability rows, source files, dependencies, tests, and repository conventions.
6. Treat docs/research/ as non-authoritative background. Do not use its model, pricing, provider, storage, streaming, tool-calling, or custom-endpoint ideas when they conflict with the PRD, plan, or ADRs.
7. Inspect the current code read-only and verify the documented baseline. Preserve all unrelated and pre-existing work.

Important current facts to verify rather than blindly assume:

- The service is a small FastAPI prototype with unauthenticated legacy routes.
- It currently uses a process-global OpenAI credential/client, an unsafe cross-request response cache, and a silent input-echo fallback.
- Authentication, tenancy, PostgreSQL, migrations, tests, Terraform, audit, and deployment foundations are not yet implemented.
- The target is OpenAI-first BYOK using Cognito, PostgreSQL/RLS, a private ECS Credential Broker, AWS Secrets Manager, a customer-managed KMS key, explicit workspace provider/model policy, approved endpoints, and no silent fallback.

Your first response must not edit files. It must contain:

- The active branch and working-tree findings.
- The active plan phase/task and whether its entry criteria are met.
- The relevant PRD requirement IDs/sections and ADRs.
- Current-code findings that affect the task.
- Confirmed requirements, assumptions, open questions, risks, and out-of-scope items.
- A small ordered implementation or review plan with likely files and validation for each step.
- Every action that needs separate approval.
- A direct request for approval of only the proposed phase.

Phase-start rule:

- The documentation package marks Phase 0 artifacts as Ready for review, not human-approved.
- Begin with P0-09/P0-10: help the human assign required owners, review the Phase 0 documents for contradictions or missing controls, and produce the exact Phase 0 approval checklist/decision.
- Do not begin Phase 1 code until a human explicitly approves the Phase 0 exit gate and the plan records that evidence.

Mandatory separate approvals immediately before the action:

- Add/remove/change any dependency, tool, runtime, or development environment.
- Create or apply a schema/data migration or modify persistent data.
- Create/change/apply Terraform, AWS resources, IAM, KMS, networking, Secrets Manager, Cognito, RDS, ECS, logging, alarms, billing resources, or external systems. Drafting reviewed IaC files may be part of an approved source-edit phase, but applying them requires its own approval.
- Use real credentials, customer content, private customer data, or production data.
- Deploy, publish, release, or change staging/production.
- Delete/overwrite material work or perform a destructive action.
- Create/switch branches, stage, commit/amend, push, open/merge a PR, tag, or rewrite Git history.

Non-negotiable security behavior:

- Never request, display, paste, log, test with, or store a real API key in source, prompts, chat, fixtures, CI variables, .env files, terminal history, screenshots, analytics, logs, traces, exceptions, queues, caches, or output.
- Credential values are write-only. No read-back API or support path is allowed.
- PostgreSQL contains only opaque secret references and safe tenant metadata; credential values live only in Secrets Manager under the approved KMS design.
- Only the private broker can retrieve credential values and call approved provider endpoints.
- Authorize authentication, active membership, role, workspace policy, provider/model allowlist, credential source, and credential binding before retrieval/invocation.
- No arbitrary model identifiers or endpoints in the initial release.
- No implicit platform-key, credential, model, region, or provider fallback.
- Do not persist prompts, audio, transcripts, or model responses.
- Use safe normalized errors and allowlisted telemetry only.
- Failed rotation preserves the previous active credential; disablement blocks new use immediately.

Implementation rules after approval:

- Implement only the approved task/phase and stop if a material architecture, security, behavior, data, compatibility, cost, or scope change appears.
- Use the smallest coherent, maintainable change matching existing conventions and accepted ADRs.
- Add success, denial, failure, cross-tenant, concurrency, and secret-leakage tests appropriate to the task.
- Run focused checks first and broader relevant checks afterward. Never claim an unrun test passed.
- Update docs/PLAN.md and docs/requirements/byok-traceability-matrix.md only with evidence-backed status.
- Update README, API docs, ADRs, threat model, runbooks, and security guidance when behavior changes.

At the end of every approved task, report:

1. Outcome and acceptance criteria.
2. Changed files and behavior.
3. Decisions and trade-offs.
4. Exact verification commands/results.
5. Security and tenant-isolation review.
6. Problems/root causes/fixes.
7. Unverified items, limitations, and residual risks.
8. Required next task and its approval gates.

Start now with read-only discovery and the Phase 0 review/approval preparation. Do not edit until I approve your first proposed plan.
```

## Expected first outcome

The AI should inspect the branch, confirm that Phase 0 documents are drafts awaiting human review, identify the named-owner/decision placeholders, present a review checklist, and request approval. It should not immediately install packages, create migrations, provision AWS, use an API key, or refactor the OpenAI service.

After Phase 0 is explicitly approved, reuse the same prompt or instruct the AI to continue with P1-01. P1-01 must first present the dependency/environment proposal and request the separate dependency approval.
