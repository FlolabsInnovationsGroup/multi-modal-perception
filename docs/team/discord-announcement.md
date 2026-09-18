# Discord Team Announcement

Send the three messages below in order **after the reviewed revision has been committed and shared through the team's approved Git workflow**. This file does not mean a commit/push has happened. Replace no branch claims from memory: teammates should verify their checkout contains revision 2 and CODEX.md. Each message is sized below 2,000 characters.

## Message 1 — What changed

Team — I’ve revised our provider-integration documentation around Indra’s review.

The main change is scope: we are adding a feature to the multimodal service, not building a new BYOK platform. Our work is to read the correct backend-managed API key, validate provider access, call the selected model, and return safe results/errors/usage.

FloBrain backend owns user authentication, permissions, protected key storage, and saving/activating/disabling/deleting credentials. UI and platform infrastructure belong to their respective teams.

The PRD is now much shorter and provider-independent. Technical contracts, tests, delivery order, and operational checks are separate. The old platform plan and AWS/identity designs are explicitly superseded; don’t use them to start coding.

This is a revised documentation package ready for team review, not a claim that the feature is implemented or that Indra has approved the rewritten text. We still need the backend credential-access contract before live integration. Approved local development can use synthetic fakes.

Please use the shared feature branch/revision for this work. We don’t need a blanket “merge main first” step. Check actual Git status before working; final integration into main remains a reviewed decision, and we should keep monitoring upstream changes.

## Message 2 — Documents and first assignments

Start at docs/README.md. The key files are:

• docs/byok-credential-broker-prd.md — what the feature must do; historical filename, smaller scope.
• docs/PLAN.md — task IDs, dependencies, and progress.
• docs/contracts/backend-provider-integration.md — the FloBrain handoff and open B1-B7 decisions.
• docs/contracts/provider-module.md — proposed internal module design.
• docs/testing/provider-integration-test-plan.md — acceptance cases.
• docs/reviews/indra-review-resolution.md — how the review was addressed.
• AGENTS.md + CODEX.md — shared working rules and Codex starting guide.
• docs/ai/implementation-start-prompt.md — the complete coding-session prompt.

First assignments to confirm:
1. Lead/reviewer: T1 — review revised scope, confirm first provider and assign owners.
2. Backend liaison: obtain the existing schema/interface and resolve B1-B7 with the backend owner. Share documentation, never actual keys.
3. Integration engineer: prepare T2’s synthetic reader/provider scaffold and tests, then implement after approval.
4. Provider engineer: prepare T3’s provider-specific validation/error mapping. OpenAI is proposed first because we already use it.
5. QA/reviewer: review TC-01–TC-14 and prepare safe fixtures and expected outcomes.

One person may cover multiple roles. Agree task/file ownership before parallel work so we don’t have several AI sessions changing the same contract.

## Message 3 — Starting with Codex

Open the repository in Codex on the intended feature checkout. Confirm it includes the shared revision, preserve existing changes, and paste the complete prompt from docs/ai/implementation-start-prompt.md. Add your assigned task ID.

For a quick start, paste:

"Read AGENTS.md, CODEX.md, and docs/ai/implementation-start-prompt.md in this repository. Follow the full implementation-start prompt. Use my assigned task if its entry criteria are met; otherwise identify the first eligible incomplete task in docs/PLAN.md. Begin with read-only discovery and a small task plan for my approval. Do not edit, install dependencies, use real keys, change external systems, or perform Git writes yet."

Codex should first explain the selected task, relevant requirements, affected files, tests, and blockers. We review that proposal before coding. At the initial revision, T1 is the first step; the old platform Phase 0 is no longer the plan.

After approval, work one task at a time, test it, update PLAN and traceability, and review the evidence before continuing. Mock-based tests let us progress locally, but they don’t prove the real backend is secure or authorize deployment.

Never paste a real API key into Codex, Discord, code, fixtures, CI variables, or terminal commands. Never let a failed key silently switch to another key/provider.

Let’s confirm the role assignments and T1 review first, then begin the smallest approved implementation task.
