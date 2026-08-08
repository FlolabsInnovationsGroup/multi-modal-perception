# Contributing

## Start here

Before working on this repository, read:

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/PLAN.md`
4. The task-relevant sections of `docs/byok-credential-broker-prd.md`
5. Applicable ADRs and architecture documents

The PRD defines what must be built. The plan defines when it is built. ADRs define accepted technical decisions. Research is background only.

## Workflow

1. Choose one task ID from the first eligible incomplete phase in `docs/PLAN.md`.
2. Inspect the relevant code and existing tests without changing state.
3. Write task acceptance criteria and map them to PRD identifiers.
4. Propose a small implementation plan and identify approval gates.
5. Obtain approval before editing.
6. Implement the smallest coherent change.
7. Add or update tests and documentation.
8. Run focused checks, then broader relevant checks.
9. Update the plan and traceability matrix.
10. Provide the completion report required by `AGENTS.md`.

Do not combine unrelated refactors, formatting, dependency changes, migrations, infrastructure, and feature behavior into one change.

## Approval-sensitive work

Separate human approval is required immediately before dependencies, environment installations, migrations, persistent data changes, AWS/IAM/KMS/network changes, real credentials, deployment, and every Git operation listed in `AGENTS.md`.

Documentation or source-edit approval does not authorize a later migration, deployment, or Git operation.

## Branches and reviews

- Work on the branch selected by the human. Do not create or switch branches without approval.
- Keep changes scoped to a plan task.
- Describe the threat and tenant-isolation impact in reviews.
- Link changed behavior to PRD requirements and acceptance tests.
- Identify breaking behavior and legacy-route effects explicitly.
- Do not stage, commit, push, or open a pull request without the corresponding approval.

## Tests

The repository does not yet have an established automated test suite. Creating the test framework or adding test dependencies requires a dependency approval. Once approved, each feature phase must add the tests specified in the PRD and traceability matrix.

At minimum, security-sensitive changes require coverage for:

- Valid and invalid authentication.
- Role and workspace authorization.
- Cross-tenant denial and IDOR attempts.
- Credential lifecycle and concurrent rotation.
- No credential disclosure in any response or captured log.
- Provider error normalization.
- No platform-key or alternate-provider fallback.
- Denied IAM, KMS, or Secrets Manager operations.

Use synthetic credentials and data. Real keys are forbidden in fixtures, `.env` files, CI variables, terminal commands, and test output.

## Documentation

- Update `README.md` for current behavior and setup changes.
- Update `docs/PLAN.md` only with evidence-backed status.
- Update the traceability matrix when code or tests satisfy a requirement.
- Add an ADR for a material architectural choice or reversal.
- Verify time-sensitive provider claims against official sources at implementation time.
- Do not copy large research documents into prompts when the approved requirement is already in the PRD.

## Review checklist

- Scope and acceptance criteria are explicit.
- No unrelated user work was changed.
- No dependency or approval gate was bypassed.
- Authentication and authorization occur before tenant resource access.
- Secrets cannot enter responses, logs, traces, caches, queues, or persistence.
- Failure cannot cause an undisclosed fallback.
- Tests cover success, denial, failure, and boundary cases.
- Documentation and traceability match the implementation.
- Remaining risks and unrun checks are reported honestly.
