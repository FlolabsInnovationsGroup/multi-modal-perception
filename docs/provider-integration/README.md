# Provider Integration — Start Here

V2 / revision 2.1 · 2026-09-19 · **Multimodal implementation specification ready for team review; feature implementation not started.**

Publication status: the earlier consolidated package is published under Notion V2. This local revision 2.1 has NOT been republished; Notion currently shows the preceding revision. Publication evidence is recorded in the review record. Feature implementation and Indra's acceptance remain pending.

We are adding a modular way for the multimodal service to read the correct backend-managed API key, check provider access, call the selected model, and return safe results. We are not building a second authentication, storage, or cloud platform.

## Read in this order

For a first review, read this page, Requirements, and Delivery plan. Engineers then read the relevant Technical design, Security, and Acceptance sections. Use the Review record to check how Indra's feedback was addressed. You do not need to read the historical archive to begin.

| Document | Question it answers | Who uses it and when |
| --- | --- | --- |
| [1. Requirements](requirements.md) | What must the feature do, and what is outside our responsibility? | Everyone; the short PRD is the product source of truth, with PI-01–PI-12 requirement IDs. |
| [2. Delivery plan](delivery-plan.md) | What do we do first, who owns it, and what counts as complete? | Lead and developers; T1–T7 tasks, proposed roles, approvals, local M1 and live M2 milestones. |
| [3. Architecture and technical design](technical-design.md) | What exactly do we build and how does it fit together? | Developers and integration reviewer; diagram, L1-L8 internal types, files, lifecycle, compatibility, limits, OpenAI slice and B1–B7 live boundaries. |
| [4. Security and operations](security-and-operations.md) | What could go wrong, how do we prevent it, and what happens on failure? | Developers, QA, security/release owners; threat controls, provider review, incident and rollback checks. |
| [5. Acceptance tests](acceptance-tests.md) | How will we prove the feature works safely? | Developers and QA; TC-01–TC-14 cases plus requirement-to-task-to-test traceability and actual evidence. |
| [6. Review record](review-record.md) | What changed after Indra's review, why, and what is still unapproved? | Indra and reviewers; R01–R33 responses, ADR-006 decision, migration map and documentation checks. |
| [7. Codex start prompt](codex-start-prompt.md) | What exactly do we give AI to begin an assigned task? | Each developer; one copy/paste prompt that starts with repository inspection and a task proposal. |
| [8. Team announcement](team-announcement.md) | How do we explain the update and first assignments on Discord? | Lead; three ready-to-send messages after the revision is shared. |

This Start Here page is the ninth active feature document. Separate files are used for different jobs, not as competing instructions. Requirements define behavior; the plan orders work; the design explains interfaces; tests prove it. Repeating a requirement ID in a test is traceability, not a second requirement.

## The five root guides

| File | Purpose | Why it stays at the repository root |
| --- | --- | --- |
| [README.md](../../README.md) | Repository overview, existing service behavior, environment and feature entry point | Helps any visitor understand this repository, not just this feature. |
| [AGENTS.md](../../AGENTS.md) | AI workflow, safety rules, approval gates and reporting | Repository-wide instruction source. |
| [CODEX.md](../../CODEX.md) | Short explicit Codex navigation guide | Points Codex to the current package; it does not replace AGENTS. |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | Human teamwork, task ownership, review and evidence workflow | Shared collaboration rules across tasks. |
| [SECURITY.md](../../SECURITY.md) | Confidential reporting and security-policy entry point | Makes reporting visible without reading feature internals. |

## How to start coding with AI

1. Use the intended branch/checkpoint containing this layout. Confirm Git status; do not assume local edits are already on the remote.
2. Give Codex repository access, not nine pasted documents. Paste the complete [start prompt](codex-start-prompt.md) and append your assigned task ID.
3. Codex reads AGENTS, CODEX, this index, the PRD and plan, then only the relevant supporting sections. Do not attach the archive as instructions.
4. Review its proposed files, assumptions and tests. Approve the bounded task before it edits.
5. Review the diff and actual test evidence, update task/traceability status, then choose the next task. Dependencies, live keys, external changes, deployment and Git writes have separate approval gates.

At the current state, T1 is the review step. After local scope approval, T2–T4 can deliver **M1: our multimodal module, tested with fakes/mocks, ready for handoff**. T5–T7 deliver **M2: actual backend integration and release** after the required live contract exists. We do not need to build the backend's platform to finish M1, and mocks do not prove M2.

## What is ready for review now?

The short PRD defines scope. The technical design now supplies concrete local implementation decisions L1-L8 rather than leaving types, limits, validation probes and test doubles unspecified. The plan breaks implementation into T2.1–T4.2 cards; tests specify exact local pass conditions and the offline command. The first code task after accepted T1 review is **T2.1: types, ports, errors and configuration**.

Reviewers accept or amend L1-L8 and assign people; the AI then implements a bounded approved card. M1 includes real orchestration and an actual OpenAI adapter, tested with simulated transport—not only toy fake implementations. Remaining B1-B7 questions concern the real integration boundary and are explicitly handed off. The package does not pretend all multimodal live-integration work is finished by M1.

No new competing document is needed. Detailed engineering material stays in the design/tests so the PRD remains short. Local revision 2.1 is ready for this review, not pre-approved, implemented, committed, pushed or live.

## Review instructions for Indra and the team

Review the [Requirements](requirements.md) for scope and clarity first. Then accept/amend L1-L8, the OpenAI-first proposal, acceptance cases and named owners in T1. Use the decision table in the [review record](review-record.md). For a comment, include the document/section and PI, T, TC, R, L or B identifier where relevant.

Record a decision with reviewer, date, approved scope, conditions and evidence link. Documentation cleanup/publication approval is not approval of implementation or an unspecified backend design. Do not mark Indra's review accepted or resolve her original comments without her decision.

Authority: system/platform rules → current explicit human decision → AGENTS → Requirements → Delivery plan → accepted decisions in Review record → approved task-specific design/security/test sections. CODEX and announcements are navigation, not competing authorities. Escalate material conflicts.

## One source, one review mirror

The repository is the editable implementation source. [Notion V2](https://app.notion.com/p/3dfa1576955180cc8b3dec232eef64d3) is the readable review mirror, not a second independent specification. After an accepted review, update the repository first and republish the affected page with its revision/status. Notion edits/comments are review input until reconciled.

[Historical archive](../archive/provider-integration-v1/README.md) contains the original PRD/plan, superseded AWS design and ADRs, and one research document. None directs current coding. The [migration map](review-record.md) explains where previous files went.

The local repository checkout is the canonical local copy. The previously mentioned Downloads folder was not present during this cleanup; no separate Downloads copy was created or synchronized.
