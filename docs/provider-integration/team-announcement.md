# Discord Team Announcement

Revision 2.1, 2026-09-19. Send these three messages in order only after revision 2.1 Notion publication is verified and the local revision has been committed/shared through the approved Git workflow. Both remain pending. This document does not claim that a push happened. Each message must remain below Discord's 2,000-character limit; paste only the message body. No Discord posting is performed by this documentation task.

## Message 1 — What changed

Team — our provider-integration documents are now organized into one current package, based on Indra's review.

Our feature is to read the correct backend-managed API key, validate provider access, call the selected model, and return safe results/errors/usage. We are not building a new authentication, key-management, UI, or cloud platform.

The short PRD defines the feature; the updated architecture specifies our module, exact internal interfaces, limits and first OpenAI adapter. Overlapping documents are consolidated and old platform designs are historical only. This is a documentation update, not completed feature code.

Review here:
https://app.notion.com/p/3dfa1576955180cc8b3dec232eef64d3

In the repository, start at docs/provider-integration/README.md. It explains every document and the reading order.

This package is ready for review; it is not a claim that Indra has approved all rewritten details or that feature code is finished. Please comment with the section and requirement/task ID so we can reconcile feedback into the repository.

There is no blanket “merge main first” step. Check the actual branch/status before working. Final merge and release remain separate reviewed decisions.

## Message 2 — Documents and first assignments

All current feature documents are in docs/provider-integration/:

• README.md — start here and understand each document.
• requirements.md — what the feature must do (PRD).
• delivery-plan.md — task order, roles, approvals and progress.
• technical-design.md — architecture, L1-L8 implementation decisions and live boundaries.
• security-and-operations.md — risks, provider checks, incidents and rollout.
• acceptance-tests.md — planned cases and evidence/traceability.
• review-record.md — Indra's feedback, decisions and verification.
• codex-start-prompt.md — complete AI kickoff prompt.
• team-announcement.md — these messages.

AGENTS.md and CODEX.md stay at the repository root as working rules/navigation. Old material in docs/archive/ is background, not coding instructions.

First assignments to confirm:
1. Lead: T1 — accept/amend L1-L8, confirm OpenAI-first scope and name owners.
2. Integration engineer: T2.1–T2.3 — types, fake credential boundary, orchestration and tests.
3. Provider engineer: T3.1–T3.2 — actual OpenAI adapter tested with simulated responses.
4. QA: review TC-01–TC-14 and synthetic fixtures.
5. Integration contact: record B1–B7 answers when available, without taking on the backend's implementation.

We can finish M1, our tested multimodal module, using fakes/mocks after local approval. M2 is actual backend integration and release; it needs the real contract and separate evidence. Missing live details do not require us to build the backend.

## Message 3 — Start with Codex

Open the intended repository checkout in Codex. Paste the full prompt from docs/provider-integration/codex-start-prompt.md and add your assigned task ID.

Quick start:

"Read AGENTS.md, CODEX.md, and docs/provider-integration/codex-start-prompt.md. Follow that full prompt. Use my assigned task if eligible; otherwise select the first eligible incomplete task in docs/provider-integration/delivery-plan.md. Begin with read-only discovery and propose a small plan for my approval. Do not edit, install, use real credentials, change external systems, or perform Git writes yet."

Codex should explain the task, affected files, requirements/tests and blockers before coding. T1 reviews the concrete L1-L8 decisions. After acceptance is recorded, add "My assigned task is T2.1" to the prompt; Codex should propose that card, not redesign the architecture.

Approve one bounded task, inspect the diff and test results, update the plan and acceptance evidence, then move on. Assign file ownership before parallel work so multiple sessions do not redesign the same interfaces.

Never paste real API keys into AI, Discord, source, fixtures, CI variables or terminal commands. Never allow silent key/provider fallback. Mock test success is not production readiness.

Please confirm owners and the T1 review first, then begin the smallest approved code task.
