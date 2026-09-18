# Provider Integration Delivery Plan

Updated 2026-09-18. Replaces the old all-platform Phase 0-7 plan.
Current state: documentation revision prepared; feature implementation **not started**.
Authority: [feature PRD](byok-credential-broker-prd.md), [AGENTS](../AGENTS.md).

## Verified baseline

At revision baseline `211c1092551143b5b34412c1ec1604899450469d`:

- FastAPI exposes `/health`, `/process`, and `/openAI`; no service authentication guard is implemented.
- `services/openai_service.py` uses a global environment key, credential-bearing singleton, prompt-only response cache, and input echo on generation failure.
- Both processing routes return `result`, `model`, and `file_type`; text, audio, and combined inputs exist.
- Route handlers log raw exception strings. Audio uploads are read into memory after framework upload handling; non-retention must also examine temporary-file spooling.
- MiniCPM evaluation/test scripts exist. They are not a dedicated, isolated provider-integration security suite.
- No backend credential reader, database contract, credential lifecycle integration, IaC, or BYOK test suite was found. Absence in this repository says nothing about FloBrain backend's implementation.
- Preserve unrelated MiniCPM work and the pre-existing untracked research copy.

Recheck this baseline before coding; it is not a permanent description of the repository.

## Approval record

| Decision | Evidence | Effect |
| --- | --- | --- |
| Documentation scope revision | User approved the proposed documentation-only revision in this conversation on 2026-09-18 | Shorter provider-independent PRD, backend ownership separation, aligned supporting docs |
| Codex handoff | Same user explicitly requested CODEX instead of CLAUDE | Replace Claude-specific guide; keep AGENTS |
| Revised PRD wording / local module contract | Pending team review | T1 |
| Backend live integration contract | Not supplied / not approved | T5 blocked |
| Feature code, dependency changes, live credentials, deployment, Git writes | Not approved by documentation approval | Obtain task/action-specific approvals |

Indra's comments dated August 15 and September 6 are review input; do not label this rewritten package as approved by her.

## Task sequence

Assign a human owner before starting a task. Role labels below are suggested responsibilities, not appointments.

| ID | Deliverable and suggested owner | Entry criteria | Status | Exit evidence |
| --- | --- | --- | --- | --- |
| T1 | Review scope, local contract, and acceptance cases; lead + backend liaison | Revised documents available | Ready for review | Dated decision on PRD, mock-only interface, first-provider sequence; identify backend contact and blocked decisions |
| T2 | Synthetic provider-module scaffold and contract tests; integration engineer | T1 approves local scope; task edit plan approved | Not started | Fake credential reader and fake provider, safe typed results, denial tests; no external I/O |
| T3 | First provider adapter and validation mapping using mocked transport; provider engineer | T2 passes; chosen provider and methods reviewed; dependency action approved if needed | Not started | Provider-specific unit tests, bounded calls, usage/error mapping, request-scoped client cleanup |
| T4 | Processing-path integration behind a fail-closed boundary; integration engineer + QA | T3 passes; B6 compatibility decision and local handler plan approved | Not started | Text/audio parity, preserved fields, no shared-key/cache/echo path in new flow, credential checks cannot be bypassed through legacy routes |
| T5 | Implement actual backend reader and service authentication; backend liaison + integration engineer | B1-B7 resolved and approved; needed dependencies/access separately approved | Blocked: backend contract missing | Contract tests against approved backend environment; credential scope/version/state and denial evidence |
| T6 | End-to-end security, regression, limits, and operational checks; QA + backend owner | T4/T5 complete; approved staging-only credential use | Not started | Test plan passes; security findings addressed; enablement/release checklist accepted |
| T7 | Controlled enablement and handoff; lead + operations owner | T6 evidence accepted; separate deployment approval | Not started | Monitored limited rollout, safe rollback exercise, caller migration and release decision |

T2-T4 may use synthetic fakes without T5, after their own approvals. They must remain local/test-only: an unavailable live resolver/authenticator denies access; mocks must not be selectable by production callers or a permissive default. T4 can prepare a handler without publishing a new production route.

Do not implement FloBrain auth, storage, credential CRUD, or UI to unblock T5.

## First provider and future work

Retain **OpenAI as the proposed first implementation slice** because it already provides text generation and transcription here. T1 confirms this sequence. Do not modernize API families or replace model defaults implicitly.

Anthropic, Gemini, Azure OpenAI, and other integrations are future tasks selected by the lead after the first slice. The PRD remains independent of that order. Each addition must declare supported capabilities, approved destinations, authentication, errors, limits, and test evidence; universal provider support is not promised.

## Decisions needed

B1-B7 are specified in the [backend contract](contracts/backend-provider-integration.md). Exact timeout, upload, concurrency, retry, and validation-cost limits must be agreed before their implementation, not guessed as product promises.

The old 99.9% availability / 250 ms overhead / 100-concurrency targets and fixed 30-day route retirement are not carried forward as approved commitments. T1/T6 agree realistic measurements and release limits; B6 controls compatibility. This is not permission to disable security or abruptly remove routes.

## Practical first assignments

- Lead/reviewer: T1 review and confirm provider order, scope, and task ownership.
- Backend liaison: obtain the existing credential schema/interface and fill B1-B7 with the backend owner. Never request real secret values.
- Integration engineer: propose T2 files and fake-reader/adapter tests; wait for T1/task approval before editing.
- Provider engineer: prepare T3 API/validation mapping from current official docs; no live calls.
- QA/reviewer: review TC-01 through TC-14 and prepare synthetic fixtures and expected results.

People can fill multiple roles. Agree file ownership before concurrent work; avoid multiple agents editing the same task/files.

## Status updates and completion

Record owner, date, requirement IDs, changed files, exact test commands/results, and approval evidence in the traceability matrix. Do not mark implementation complete from documentation alone. If blocked, state the decision needed and continue only independent approved work.

At each handoff, include branch/working-tree facts. Do not assume this branch is synchronized with main or already shared. Staging, committing, pushing, and merging need separate approval; do not make an initial merge a prerequisite without current evidence.
