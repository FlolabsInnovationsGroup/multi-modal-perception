# Codex Start Here

This is the project's explicit Codex handoff guide. [AGENTS.md](AGENTS.md) remains the shared repository instruction source; this file does not override it.

Codex discovers `AGENTS.md` through its documented instruction mechanism. Do not assume a file named `CODEX.md` is automatically loaded. The kickoff prompt explicitly requests this file; no global Codex configuration change is required. See [official instruction discovery guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md), checked 2026-09-18.

## Start a session

1. Open the intended repository checkout/branch. Verify it with read-only Git checks.
2. Read [AGENTS.md](AGENTS.md), [documentation index](docs/README.md), [feature requirements](docs/byok-credential-broker-prd.md), and [plan](docs/PLAN.md).
3. Copy the complete prompt from [implementation-start-prompt.md](docs/ai/implementation-start-prompt.md).
4. Supply your assigned task ID if the team has assigned one. Otherwise start with the first eligible incomplete task.
5. Review Codex's small proposed plan and approve only that task. Do not paste credentials.

The feature reads and validates backend-managed credentials and calls selected providers. It does not build FloBrain authentication, user roles, credential-management screens, or cloud infrastructure.

Initial work is review and then approved synthetic/mock-based implementation. Real backend access is blocked until the backend contract is agreed. Old platform Phase 0-7 tasks and ADR-001 through ADR-005 are superseded; do not revive them.
