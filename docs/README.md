# Provider Integration Documentation

Revision 2, 2026-09-18. The approved task is a documentation revision based on Indra's review. Rewritten specifications are **ready for team review**, not automatically approved for production implementation.

## Read these first

| File | What it tells you |
| --- | --- |
| [AGENTS.md](../AGENTS.md) | Repository workflow, safety rules, approval gates |
| [CODEX.md](../CODEX.md) | How to begin with Codex |
| [Feature PRD](byok-credential-broker-prd.md) | What the feature must do and which team owns it |
| [PLAN.md](PLAN.md) | Task order, dependencies, assignments, current progress |
| [Backend contract](contracts/backend-provider-integration.md) | What multimodal needs from FloBrain; unresolved integration choices |
| [Provider module contract](contracts/provider-module.md) | Proposed small internal interface; not a public API commitment |
| [Test plan](testing/provider-integration-test-plan.md) | Cases and evidence needed to accept the work |
| [AI kickoff prompt](ai/implementation-start-prompt.md) | Copy/paste instructions for a repository-connected Codex session |

For implementation, read the first four and only the supporting documents relevant to the task. Do not paste the whole documentation tree into every prompt.

## Supporting documents

- [Data flow](architecture/byok-data-flow.md): request and credential boundaries.
- [Threat checklist](architecture/byok-threat-model.md): scoped risks and tests.
- [Team responsibility matrix](architecture/byok-role-permission-matrix.md): team ownership, not application RBAC.
- [Provider enablement review](architecture/byok-provider-terms-review.md): technical/provider-policy checks before live use.
- [ADR-006](architecture/decisions/ADR-006-provider-integration-scope.md): approved scope revision and explicitly unresolved mechanisms.
- [Traceability matrix](requirements/byok-traceability-matrix.md): requirement -> task -> test -> evidence.
- [Review resolution](reviews/indra-review-resolution.md): old-vs-reviewed PRD comparison and answers.
- [Operations and release checklist](operations/provider-integration.md): failure handling, staged verification, rollback.
- [Discord announcement](team/discord-announcement.md): ready-to-send message sequence.

## Authority and status

System/platform rules -> current human decision -> root AGENTS -> current PRD -> active plan -> accepted current ADRs -> approved task contracts. Material contradictions require a human decision. CODEX is a navigation guide, not a second authority.

- **Ready for review / Proposed:** drafted, not signed off.
- **Approved scope:** a named human decision about boundaries, not proof of implementation.
- **Not started / In progress / Blocked:** task state; include the reason when blocked.
- **Complete:** actual acceptance evidence exists.
- **Superseded / Historical / Reference:** must not direct new implementation.

PRD review and backend-contract approval are distinct. The user approved rewriting the documents, not the unspecified backend design. Record subsequent approvals in the plan; never invent Indra's acceptance.

## Superseded material

The old all-platform Phase 0-7 plan is replaced. [Historical PRD](archive/pre-indra-prd.md) and [historical plan](archive/pre-indra-plan.md) retain the earlier content for comparison only.

The AWS design and ADR-001 through ADR-005 are marked superseded. Their older status sections are historical text, not current approval. Research, including local copies, is background only. No old Cognito/RDS/ECS/Secrets Manager design may become a prerequisite through an old link.

The legacy PRD filename is retained for link compatibility; it does not require a separately deployed broker. The previous Claude-specific guide has been replaced with CODEX at the user's request.

## Ready to start means

Ready to review scope and then propose a bounded local task using synthetic fakes. It does not mean backend access, credentials, dependencies, code, or production are approved. Follow the current plan rather than the archived kickoff prompt or previous chat instructions.
