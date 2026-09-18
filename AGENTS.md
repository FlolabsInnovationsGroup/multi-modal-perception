# Multi-Modal Perception Repository Instructions

## Scope and authority

Applies to the entire repository. Follow system/platform rules, the current explicit human decision, this file, the current feature PRD, the active plan, accepted current ADRs, and task-specific contracts, in that order. Research and superseded documents are background only. Report material conflicts rather than silently choosing a design.

The current feature is **provider integration**, not a new authentication, tenancy, UI, or cloud platform. The user approved revising the documentation around Indra Araujo's review on 2026-09-18. That approval does not approve an unknown backend integration contract, the newly drafted specifications in advance, feature implementation, or deployment.

## Read before work

1. Read this file, `CODEX.md`, `docs/README.md`, and `docs/PLAN.md`.
2. Read `docs/byok-credential-broker-prd.md` and only the current contracts, tests, and source relevant to the assigned task.
3. Inspect Git status, repository layout, README, dependencies, configuration, and tests read-only. Preserve unrelated changes.
4. Identify the first relevant incomplete task whose entry criteria are met. If assigned a different task, explain unmet dependencies.
5. Separate verified facts, proposals, open decisions, and evidence. Never claim a draft is approved or planned tests have passed.
6. Do not load `docs/archive/`, superseded ADR-001 through ADR-005, the superseded AWS design, or `docs/research/` as implementation instructions.

## Workflow

Understand -> propose a small plan -> obtain human approval -> implement only that scope -> verify -> report.

The first response for a new implementation task is read-only: state scope, relevant requirement/task IDs, likely files, tests, risks, and approval gates. Wait for approval before editing. Approval of one task does not authorize unrelated changes. Stop for a material architecture, security, data-handling, compatibility, cost, or scope change.

## Mandatory separate approval gates

Obtain explicit approval immediately before:

- Adding, removing, or changing dependencies, tools, runtimes, extensions, or plugins.
- Installing software or materially changing the development environment.
- Deleting files/data, overwriting material user work, resetting work, force operations, or other destructive actions.
- Creating or applying database/schema/data migrations or modifying persistent data.
- Creating/changing cloud resources, permissions, networking, secrets, credentials, billing, or external systems.
- Using real credentials, private customer content, or production data.
- Deploying, publishing, releasing, or changing staging/production.
- Creating/switching branches, staging, committing/amending, pushing, opening/merging PRs, tagging, or rewriting Git history.

State the exact action, purpose, effect, main risk, rollback or safer alternative. Approval applies only to the named action. Read-only checks and synthetic local tests do not imply live-system authorization.

## Responsibility boundary

Multimodal owns a modular provider integration, scoped credential reading through the agreed backend interface, credential validation, provider execution, safe errors, and usage returned to the backend.

FloBrain backend owns user authentication/authorization, ownership policy, credential submission/storage and lifecycle persistence. UI and platform infrastructure remain with their owners. Multimodal must still authenticate its service caller and enforce the trusted request-to-credential binding; do not trust arbitrary user-supplied IDs.

Do not create Cognito, membership/RBAC tables, RLS, a separate ECS broker, Secrets Manager/KMS resources, credential-management CRUD/UI, recovery jobs, or a platform model catalog database as prerequisites. These old implementation choices are superseded, not deployed systems to remove.

The real storage, retrieval/decryption, service-authentication, and lifecycle consistency mechanisms are unresolved in `docs/contracts/backend-provider-integration.md`. Use synthetic fakes for approved local tasks; never invent production schemas, endpoints, credentials, or authorization claims.

## Security invariants

- Never expose provider keys through public responses, logs, traces, errors, metrics, URLs, prompts, support tools, fixtures, CI output, queues, or cross-request caches.
- Never ask a human to paste a real key into chat, source, or command history. Use obvious synthetic placeholders, e.g. `test-provider-key-redacted`.
- Resolve only the exact credential/version bound to trusted backend context; deny missing, mismatched, inactive, disabled, deleted, or unapproved state before provider use.
- Credential validation is a separate internal operation: validating a pending replacement must not activate it or permit normal invocation.
- Minimize plaintext lifetime to one in-flight operation and close request-scoped clients. Do not claim Python guarantees memory zeroization.
- Do not silently switch credential, source, provider, model, endpoint, deployment, or region. Do not echo input as a successful fallback.
- Do not persist or cache prompts, audio, transcripts, or model responses. Include upload spooling, SDK diagnostics, and failure paths in verification.
- Use approved adapter configuration for destinations. Never send a key to an arbitrary request-supplied URL or redirect.
- Return safe allowlisted errors and metadata, not raw SDK exceptions or request/response dumps.
- Backend ownership is not evidence that its controls already exist. Live integration must fail closed until the contract and denial tests are approved.

## Implementation and verification

Use existing Python 3.11/3.12, FastAPI/Pydantic conventions unless a change is approved. Keep provider-specific code behind a small adapter boundary; do not build speculative multi-provider infrastructure. Provider order belongs in the plan.

Preserve current text/audio behavior and `result`, `model`, `file_type` compatibility unless an explicit API change is approved. Do not remove or expose routes under a guessed migration policy. MiniCPM evaluation scripts are not BYOK security tests and must not be run as a default check if they need downloads, GPUs, paid APIs, or external data.

Use existing tooling first. Propose any missing dependency separately. Cover success, invalid credentials, scoped-access denial, no fallback, safe errors, concurrency, updated/disabled versions, and leakage. Never weaken tests just to make a build pass.

Update `docs/PLAN.md` and `docs/requirements/byok-traceability-matrix.md` with actual files/results. Update affected contracts, README, security guidance, and ADRs with behavior changes. Verify time-sensitive provider facts with dated official sources before implementation.

## Completion report

Report outcome against requirement/task IDs; changed files and behavior; decisions/trade-offs; exact checks/results; problems and fixes; credential/scope isolation review; unverified items and risks; next task and approval gates. Missing required checks or unresolved critical security boundaries prevent claiming production readiness.
