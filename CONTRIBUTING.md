# Contributing to Provider Integration

Read [AGENTS](AGENTS.md), [CODEX](CODEX.md), the [docs index](docs/provider-integration/README.md), [PRD](docs/provider-integration/requirements.md), and [plan](docs/provider-integration/delivery-plan.md).

## Workflow

1. Agree a task ID and human owner. Inspect the current branch, source, dependencies, and tests.
2. Propose a small change and acceptance cases; obtain task approval before editing.
3. Implement only the approved scope, using synthetic fakes where the live contract is unavailable.
4. Run focused checks, then relevant broader checks. Never run GPU/model-download/provider-paid scripts by default.
5. Update plan and traceability with actual evidence, and report remaining risks.
6. Obtain separate approval for dependencies/installations, migrations/data, external/cloud changes, real keys/data, deployment, deletion, and Git writes as specified by AGENTS.

## Scope and teamwork

Do not implement backend user authentication, role administration, credential CRUD, UI, cloud infrastructure, or recovery jobs to bypass an unresolved handoff. Backend ownership still requires authenticated service calls and verified credential bindings.

Assign files/tasks before concurrent work. Each teammate uses the same current document revision and gives Codex the assigned task ID. Do not let multiple sessions independently redesign the shared contract.

Preserve unrelated work. Historical research is kept once in the archive; do not create new competing instruction copies. A branch is not shared merely because local documents changed; approved commit/push/review is a separate handoff. Do not assume main/branch divergence from old chat messages.

## Tests and review

MiniCPM evaluation scripts exist; they are not the provider-integration security suite. T2 proposes an isolated test structure using existing tooling. Installing a new test framework requires approval.

Cover [TC-01 through TC-14](docs/provider-integration/acceptance-tests.md) as relevant: scoped access, validation, version changes, error mapping, no fallback, leakage, request isolation, limits, and compatibility. Test with synthetic placeholders, never real keys in fixtures or output.

Reviewers verify requirement IDs, approved contract assumptions, current result/model/file_type behavior, no accidental provider/API modernization, test results, and remaining live-integration blockers. An unrun check must be labeled unrun.
