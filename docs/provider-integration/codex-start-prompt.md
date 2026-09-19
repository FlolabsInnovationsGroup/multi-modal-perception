# Final Codex Implementation Start Prompt

Revision 2.1, 2026-09-19. Canonical prompt for the local implementation specification; design approval and code authorization are separate.

Use a repository-connected Codex session on the intended checkout. Copy the entire text block below. Tell Codex your assigned task ID if the lead has assigned one. Otherwise it selects the first eligible incomplete task from the current plan.

CODEX is an explicit handoff guide, not a replacement for AGENTS. Do not paste keys, customer content, research dumps, or old chat instructions. The initial response is a review/proposal; coding begins only after the required task approval.

## Copy/paste prompt

```text
You are the implementation engineer for the Multi-Modal Perception provider-integration feature on the current branch.

Read the actual repository before making changes:
1. Confirm the repository root, branch, and Git working-tree status. Preserve unrelated work. Do not switch branches or stage, commit, push, or merge.
2. Read AGENTS.md and CODEX.md, then docs/provider-integration/README.md, docs/provider-integration/requirements.md, and docs/provider-integration/delivery-plan.md.
3. Read the task-relevant sections of docs/provider-integration/technical-design.md (especially L1-L8), docs/provider-integration/security-and-operations.md, and docs/provider-integration/acceptance-tests.md (including exact local test assertions and traceability).
4. Inspect relevant source, dependencies, tests, and current conventions. Read ADR-006 in docs/provider-integration/review-record.md for the approved scope boundary. Do not use archived documents, superseded ADR-001 through ADR-005, the superseded AWS design, or research as implementation authority.

Objective:
Build the modular provider integration in small reviewed tasks. Multimodal reads the correct backend-managed key through an agreed secure interface, validates access, calls the selected provider/model, and returns safe results/errors/usage. FloBrain owns user authentication/authorization, protected key storage, and lifecycle persistence. Other teams own UI and platform infrastructure.

Do not build Cognito, user roles, invitations, RLS schemas, cloud infrastructure, a separate deployed broker, credential-management CRUD/UI, recovery jobs, or a new audit platform as prerequisites.

Choose my assigned task if its entry criteria are met; otherwise explain its blocker and propose the first eligible incomplete task. At the initial document state this is T1, review of the revised PRD and mock-only module scope, not the old platform Phase 0. Do not assume the rewritten PRD or backend contract has already been approved by Indra.

Check the revision 2.1 L1-L8 decision table in docs/provider-integration/review-record.md. If T1 is accepted with any conditions satisfied, choose the first incomplete implementation card T2.1 through T4.2, not another generic architecture exercise. Begin with T2.1 when none is complete. Use the accepted type/file map, limit profile, provider behavior and fixture rules; do not silently redesign them. If T1 is not accepted, present the specific decisions for review and do not code.

Your first response must be read-only and concise:
- Current branch and existing changes.
- Selected task, entry criteria, relevant PI/TC IDs, and source findings.
- Confirmed decisions versus assumptions and B1-B7 blockers.
- A small plan with exact likely files, acceptance cases, and verification.
- The approvals needed and a direct request to approve only that task.

After task approval, implement that bounded task, test it, and report evidence. T2-T4 can complete M1, the multimodal module handoff, using approved synthetic fakes while live integration remains blocked. Implement the actual OpenAI adapter and exercise it with mocked transport in T3; do not substitute a fake adapter for that deliverable. M2 (T5-T7) is a separate live-integration/release milestone. Fake readers/transports must never become production defaults. Do not invent live backend schemas, endpoint URLs, service-authentication claims, decryption mechanisms, or lifecycle consistency rules; use L3's specified atomic fake semantics only in tests.

Security requirements:
- Verify the backend service caller and bind each credential lookup to the authorized scope/provider/version/operation. User-supplied IDs alone are not authorization.
- Keep credential-bearing clients request-local. Never return, log, trace, cache, persist locally, or print keys. Never request real keys in chat, source, CI variables, fixtures, or commands.
- Validate pending replacements only for explicitly authorized validation. Return the exact checked version; the backend owns activation. Do not silently select an old, platform, or alternate key.
- No implicit provider/model/source/region/endpoint fallback; no echo-on-error.
- No persistent prompts, audio, transcripts, or model responses, including upload spooling and error diagnostics.
- Approved provider destinations only; no arbitrary endpoint/header override.
- Use safe error categories, nullable usage, bounded inputs/time/concurrency, and an explicitly reviewed retry policy.
- Preserve current text/audio behavior and result/model/file_type fields unless B6 explicitly approves changes. Do not remove legacy routes or modernize provider APIs/models implicitly.

Follow all separate approval gates in AGENTS for dependencies/installations, migrations/persistent data, cloud/external systems/permissions, real credentials/data, deployment, destructive actions, and Git writes. This prompt is not approval for those actions.

Use existing tooling. Add relevant success, denial, concurrency, lifecycle, no-fallback, compatibility, and leakage tests. Do not run GPU benchmarks, model downloads, real APIs, or install test tools by default. Never claim unrun checks passed.

The proposed offline suite command is python -m unittest discover -s tests/provider_integration -p "test_*.py" -v, after those tests exist. Record test counts and installed runtime/SDK/transport versions. Zero tests or skipped required local cases do not pass. Current official SDK docs may describe a newer major than the repository's openai>=1,<2 range; verify the installed interface and request approval for any dependency change. Do not connect the new module to existing public routes in M1; preserve their code and document remaining exposure/spooling risks.

Update docs/provider-integration/delivery-plan.md and docs/provider-integration/acceptance-tests.md with real files/results; update affected contracts/docs when behavior changes. Stop for a material security, architecture, compatibility, cost, or scope change and ask for a decision. Continue only independent approved work when a dependency is blocked.

At each handoff report what changed, requirement/task acceptance, exact check results, security/isolation findings, remaining gaps, and the next task/approval. Do not claim production readiness from mock tests.

Begin now with discovery and the first eligible task proposal.
```

## After the first response

Review and approve the specific local task plan if it is correct. Approving document review does not approve the entire implementation. Give the next task ID after accepting evidence; repeat until the plan is complete. Live integration and release wait for their own contracts and approvals.

After T1 acceptance, append: `My assigned task is T2.1. Use the recorded accepted L1-L8 decisions and begin with a read-only implementation proposal.` Replace the card ID as work progresses; do not state acceptance if the review record is still pending.
