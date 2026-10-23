# Provider Integration Delivery Plan

Revision 2.1, 2026-09-19, with coordination corrections C1-C3 added 2026-10-16. Replaces the old all-platform Phase 0-7 plan. Local design L1-L8 was accepted as written by the lead (Mani) on 2026-10-23; see the review record.
Current state: T1 L1-L8 accepted; **T2.1 implemented, tested and accepted by Mani on 2026-10-23**, committed locally (not pushed, so the shared checkpoint is not yet shared); T2.2 onward not started.
Authority: [feature PRD](requirements.md), [AGENTS](../../AGENTS.md).

## Verified baseline

Rechecked during consolidation at `d73ab6779d5a6a267cd042e1208be9af80b2d932`:

- FastAPI exposes `/health`, `/process`, and `/openAI`; no service authentication guard is implemented.
- `services/openai_service.py` uses a global environment key, credential-bearing singleton, prompt-only response cache, and input echo on generation failure.
- Both processing routes return `result`, `model`, and `file_type`; text, audio, and combined inputs exist.
- Route handlers log raw exception strings. Audio uploads are read into memory after framework upload handling; non-retention must also examine temporary-file spooling.
- MiniCPM evaluation/test scripts exist. They are not a dedicated, isolated provider-integration security suite.
- No backend credential reader, database contract, credential lifecycle integration, IaC, or BYOK test suite was found. Absence in this repository says nothing about FloBrain backend's implementation.
- Preserve unrelated MiniCPM work. Historical research is now kept once in the archive.

Recheck this baseline before coding; it is not a permanent description of the repository.

## Approval record

| Decision | Evidence | Effect |
| --- | --- | --- |
| Documentation scope revision | User approved the proposed documentation-only revision in this conversation on 2026-09-18 | Shorter provider-independent PRD, backend ownership separation, aligned supporting docs |
| Codex handoff | Same user explicitly requested CODEX instead of CLAUDE | Replace Claude-specific guide; keep AGENTS |
| Revised PRD wording / local module contract | L1-L8 accepted as written by the lead (Mani) on 2026-10-23; Indra's PRD acceptance still pending | T1 L1-L8 accepted; T2.1 eligible after its own edit-plan approval |
| Python 3.13 test exception | Lead (Mani) approved on 2026-10-23 | T2.1 tests may run on installed Python 3.13.14, standard library only, no installs; re-run on 3.11/3.12 before M1 sign-off |
| Backend live integration contract | Not supplied / not approved | T5 blocked |
| Documentation consolidation and Notion V2 publication | User explicitly approved the proposed cleanup/publication plan on 2026-09-18 | Merge active documents, archive superseded material, remove the confirmed research duplicate, publish under the existing V2 page; no code or Git writes |
| Feature code, dependency changes, live credentials, deployment, Git writes | Not approved by documentation approval | Obtain task/action-specific approvals |
| M1 implementation-specification completion | User approved the documentation-only plan on 2026-09-19 | Specify L1-L8, task slices, tests and handoff locally; no code, Notion update or Git writes |
| Coordination corrections C1-C3 | Requesting user (core owner) instructed and approved the documentation-only update on 2026-10-16 | C1 parallel T2/T3 tracks after a reviewed T2.1 checkpoint; C2 split validation tests; C3 old-version denial after rotation. Not T1 acceptance; no code, Git writes or installs |

Indra's comments dated August 15 and September 6 are review input; do not label this rewritten package as approved by her.

## Task sequence — local module, then live integration

Assign a human owner before starting a task. Role labels below are suggested responsibilities, not appointments.

| ID | Deliverable and suggested owner | Entry criteria | Status | Exit evidence |
| --- | --- | --- | --- | --- |
| T1 | Review scope, L1-L8 local contract, and acceptance cases; lead + backend liaison | Revision 2.1 documents available | L1-L8 accepted 2026-10-23 (Mani, lead); still open: separate TC-table acceptance, named backend contact | Accept/amend each L decision, first-provider sequence and named owners; identify backend contact and live-only blocked decisions |
| T2 | Synthetic provider-module scaffold and contract tests; integration engineer | T1 approves local scope; task edit plan approved | In progress: T2.1 accepted 2026-10-23 (Mani); T2.2/T2.3 not started | Fake credential reader and fake provider, safe typed results, denial tests; no external I/O |
| T3 | First provider adapter and validation mapping using mocked transport; provider engineer | T1 accepted and the T2.1 checkpoint implemented, tested and reviewed; may then run alongside T2.2/T2.3; chosen provider and methods reviewed; dependency action approved if needed | Not started (pre-checkpoint draft exists; see Parallel tracks) | Provider-specific unit tests, bounded calls, usage/error mapping, request-scoped client cleanup |
| T4 | Processing-path integration behind a fail-closed boundary; integration engineer + QA | T2 and T3 both pass review and are combined; local handler contract/compatibility assumptions approved in T1; no exposed API change | Not started | Text/audio parity, preserved fields, no shared-key/cache/echo path in new flow, local fail-closed handler and bypass tests; externally reachable integration deferred to T5/T6 |
| T5 | Implement actual backend reader and service authentication; backend liaison + integration engineer | B1-B7 resolved and approved; needed dependencies/access separately approved | Blocked: backend contract missing | Contract tests against approved backend environment; credential scope/version/state and denial evidence |
| T6 | End-to-end security, regression, limits, and operational checks; QA + backend owner | T4/T5 complete; approved staging-only credential use | Not started | Test plan passes; security findings addressed; enablement/release checklist accepted |
| T7 | Controlled enablement and handoff; lead + operations owner | T6 evidence accepted; separate deployment approval | Not started | Monitored limited rollout, safe rollback exercise, caller migration and release decision |

T2-T4 may use synthetic fakes without T5, after their own approvals. They must remain local/test-only: an unavailable live resolver/authenticator denies access; mocks must not be selectable by production callers or a permissive default. T4 can prepare a handler without publishing a new production route.

Do not implement FloBrain auth, storage, credential CRUD, or UI to unblock T5.

### Parallel tracks and shared checkpoint (C1, 2026-10-16)

1. T1 acceptance is recorded first.
2. The core owner implements T2.1. T2.1 becomes the **shared checkpoint** only after it is implemented, tested, reviewed and shared through a separately approved Git action.
3. From that checkpoint, the core track (T2.2, T2.3) and the adapter track (T3.1, T3.2) may run concurrently. Neither track may rely on a shared-interface change until both owners have agreed it and the checkpoint is updated.
4. T4.1 starts only after both T2 and T3 have passed review and their branches are combined through an approved Git action. T4.2 follows T4.1.

File ownership stated by the requesting user on 2026-10-16 (role labels; the lead records named people):

| Track | Owner | Files |
| --- | --- | --- |
| Core (T2, T4) | Integration engineer / core owner | `services/provider_integration/__init__.py`, `types.py`, `ports.py`, `errors.py`, `config.py`, `orchestrator.py`, `handler.py`, `wiring.py`; `tests/provider_integration/__init__.py`, `fakes.py` and the core tests (`test_contracts.py`, `test_admission.py`, `test_orchestrator.py`, `test_limits.py`, `test_validation.py`, `test_handler.py`, `test_isolation.py`, `test_leakage.py`, `test_import_safety.py`) |
| Adapter (T3) | Provider engineer / adapter owner | `services/provider_integration/adapters/__init__.py`, `adapters/openai.py`; `test_openai_adapter.py`, `test_openai_transport.py`, `test_openai_validation.py` |

Do not edit the other track's files without coordinating first. Record T2/T4 evidence separately from T3 evidence and reconcile both during integration.

Observed state on 2026-10-16 (read-only check, no fetch): remote branch `origin/Sumukhi_First_Multi_Model_Branch` has commit `df613b0` ("T3.1: add OpenAI adapter with mocked tests", 2026-10-11). It came before any T2.1 checkpoint and uses temporary local result types. It is a **pre-checkpoint draft, not accepted T3 evidence**. It also adds `services/provider_integration/__init__.py`, a core-owned file that imports the adapter when the package is imported. Agree how to resolve this before the tracks are combined, because L1 import safety (TC-14) requires that only the adapter imports the provider SDK.

Rechecked on GitHub on 2026-10-23: the branch's T3.1 commit now appears as `f7fde62`, which has the same file content as `df613b0` (`git diff` between them is empty). There have been no later commits and there is no open pull request from that branch.

## Two separate completion milestones

**M1 — Multimodal module ready for handoff (T1-T4).** The team can finish its independently testable part using synthetic credential readers and mocked provider transports. Acceptance requires the applicable local portions of TC-01 through TC-14, the selected adapter, text/audio handler compatibility, safe outputs, denial/leakage/no-fallback tests, and an explicit list of unresolved live assumptions. Record evidence in [acceptance tests](acceptance-tests.md). T4 does not publish a new route or change an existing caller contract.

**M2 — Live integration/release ready (T5-T7).** Requires the actual credential access and service authentication contract, joint lifecycle tests, approved staging evidence, and release authorization. B1-B7 block their corresponding live work, not completion of M1. Missing mechanisms are dependencies to hand off, not a request for multimodal to build backend identity/storage.

The team may accurately report "multimodal module complete; live integration pending" after M1 evidence is accepted. It must not report the end-to-end feature as production-ready from mocks.

## First provider and future work

Retain **OpenAI as the proposed first implementation slice** because it already provides text generation and transcription here. T1 confirms this sequence. Do not modernize API families or replace model defaults implicitly.

Anthropic, Gemini, Azure OpenAI, and other integrations are future tasks selected by the lead after the first slice. The PRD remains independent of that order. Each addition must declare supported capabilities, approved destinations, authentication, errors, limits, and test evidence; universal provider support is not promised.

## Decisions needed

B1-B7 are specified in the [backend contract](technical-design.md). L5 now proposes exact local timeout, input, concurrency and retry limits; L6 specifies validation probes. T1 must accept/amend them before implementation. They are not production promises; B5/B7 reconcile live limits and validation cost policy.

The old 99.9% availability / 250 ms overhead / 100-concurrency targets and fixed 30-day route retirement are not carried forward as approved commitments. T1/T6 agree realistic measurements and release limits; B6 controls compatibility. This is not permission to disable security or abruptly remove routes.

## Implementation-sized task cards

Card status: **T2.1 accepted 2026-10-23 by Mani** (evidence below; committed locally, not pushed); all other cards **not started** (T3.1 has only the pre-checkpoint draft described above). Paths below are relative to `services/provider_integration/` and `tests/provider_integration/` unless explicitly stated. Every card needs its own edit-plan approval; accepting T1 is design approval, not unlimited coding authorization. Update status with actual evidence, not the existence of these cards.

| Card | Entry / suggested owner | Proposed files and concrete work | Required exit evidence |
| --- | --- | --- | --- |
| T2.1 | T1 L1-L8 accepted; integration engineer | `__init__.py`, `types.py`, `ports.py`, `errors.py`, `config.py`; exact L2 types, secret safety, configuration validation and L5 profile | `test_contracts.py`: required/unknown fields, enum/bounds, secret repr/serialization, exact target checks; TC-01/02/08/11 |
| T2.2 | T2.1 accepted; integration engineer | `fakes.py`, `test_admission.py`; fake verifier, atomic scoped reader, test-only lifecycle actions and barriers | TC-02/03/05/06/13: exact-version denials, expiry, rotation/disable order, pending validation only; no real I/O |
| T2.3 | T2.2 accepted; integration engineer | `orchestrator.py`, `test_orchestrator.py`, `test_limits.py`, `test_validation.py`; session lifecycle, deadlines, shared capacity, separate validation | TC-04/07/08/10/11/12: call order/count, cancellation, no fallback, partial usage and cleanup; TC-04 core validation assertions in `test_validation.py`; fake adapter only |
| T3.1 | T1 accepted and reviewed T2.1 checkpoint (may run alongside T2.2/T2.3); provider engineer | Record SDK/transport versions and official API check in test evidence; add `adapters/openai.py` and `test_openai_adapter.py` | Mocked generation/transcription exactly match L6; no env fallback, explicit model/destination/timeouts/retries; TC-01/04/07/10/11 |
| T3.2 | T3.1 accepted; provider engineer + QA | Extend adapter and `test_openai_transport.py`, `test_openai_validation.py`; bounded response transport, no redirects, probes and status mapping | TC-04/07/08/09/12: TC-04 adapter probe/outcome assertions in `test_openai_validation.py`; one probe/call, synthetic WAV only, response-byte cap before deserialization, deny alternate host; no installed-package changes without approval |
| T4.1 | T2 and T3 accepted and combined; integration engineer | `handler.py`, `wiring.py`, `test_handler.py`; internal verified handler, deny-all default, legacy-success projection | TC-02/10/13/14: fields/text/audio composition match L4, no public routes registered, no fake selectable at runtime |
| T4.2 | T4.1 accepted; QA + integration engineer | `test_isolation.py`, `test_leakage.py`, `test_import_safety.py`; complete local regression and handoff evidence in these documents | All local TC cases in acceptance matrix pass; import without key/network; old routes unchanged and not described as safe; M1 reviewer sign-off |

### T2.1 evidence — 2026-10-23 (core track)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani (core owner). Edit plan approved by the lead on 2026-10-23. Reviewer decision: **accepted by Mani on 2026-10-23**; the gaps listed below remain open |
| Scope | Types, ports, errors, config, package init, empty test-package init, `test_contracts.py`, and the three L2 interface clarifications recorded in the technical design. No fakes, orchestrator, handler, wiring, routes, dependencies or Git writes |
| Requirements / tests | PI-01, PI-02, PI-07, PI-08, PI-11. Local core portions of TC-01, TC-02, TC-08, TC-11, the configuration part of TC-12, and the import-safety part of TC-14 |
| Environment | Python 3.13.14 (approved exception; standard library only; no installs); Windows 10. `openai`, `pydantic` and `fastapi` are not installed and not needed by T2.1 |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v`, run from the repository root |
| Result | **71 tests discovered, 71 passed, 0 failed, 0 errors, 0 skipped** (0.177 s) |

**Files added**
- `services/provider_integration/__init__.py`
- `services/provider_integration/types.py`
- `services/provider_integration/ports.py`
- `services/provider_integration/errors.py`
- `services/provider_integration/config.py`
- `tests/provider_integration/__init__.py` (0 bytes, blob `e69de29`, identical to the adapter branch's file)
- `tests/provider_integration/test_contracts.py`

**Additional checks**
- **Mutation check:** ten deliberate defects were applied one at a time to a scratch copy, and the suite failed for each:
  - SecretValue repr leak
  - value-based secret equality
  - visible exception cause
  - BoundaryFailure accepting any code
  - timeout counted as a rejection
  - non-zero retries
  - `http` destination
  - result content in repr
  - negative usage kept
  - package init importing adapters
- **Python 3.11 syntax:** `ast.parse(feature_version=(3, 11))` passed for all new files.
- **No changes outside the new files:** `git diff --name-only` over `main.py`, `api/`, `services/openai_service.py`, `services/__init__.py`, `schemas.py`, `requirements.txt` and `minicpm_test_case/` returned nothing.
- **Nothing staged:** `git diff --cached` returned nothing.

**Gaps and risks**
- The results must be re-run on Python 3.11/3.12 before M1 sign-off.
- TC-02/08/12/14 are covered only at the type/config/import level. Admission, orchestration, logging capture, filesystem and handler checks belong to T2.2-T4.2.
- The adapter owner must agree the session/error interface (`StepOutput`, `ProbeOutcome`, `ProviderOperationError`) before relying on it.
- The checkpoint is not shared: sharing needs a separately approved commit/push.
- This is local mock-free unit evidence only, not live or production evidence.

T3.1 preflight does not install anything. If a compatible approved environment is absent, report that and request setup approval. Current requirements are version ranges, not a lockfile; do not quietly upgrade or claim tests ran against an unspecified SDK. T3.2 may need a transport wrapper but must not introduce a separate infrastructure service.

### T1 review meeting checklist

- [ ] Confirm PI-01 through PI-12 scope and OpenAI-first slice; future providers are separately selected work.
- [x] Accept/amend L1-L8 together, including internal fields, limits, probes, no route wiring during M1, and proposed file ownership. (Accepted as written, Mani, 2026-10-23.)
- [ ] Accept local TC expectations; do not demand live-backend proof for M1 or count fake proof toward M2.
- [ ] Assign named owner/reviewer for each next card and an integration contact; record unavailable contacts honestly.
- [x] Record reviewer/date/revision/conditions in the review record. Leave B1-B7 unresolved unless actual answers and approval exist. (Recorded 2026-10-23; B1-B7 unresolved.)
- [ ] Approve a separate bounded T2.1 implementation plan when ready. No main-branch merge, dependency installation or deployment is implicitly authorized.

After these review decisions, no additional product/architecture invention should be necessary to start T2.1. A discovered contradiction or SDK incompatibility must still be reported instead of hidden.

### Multimodal handoff, not backend implementation

Deliver the source module, offline tests, accepted L contract and limit profile, SDK version evidence, legacy-success mapping, and list of B1-B7 integration questions with a contact/status for each. Preserve the fake conformance tests so the future real reader/verifier can run equivalent cases. The module can reach M1 without a backend server, real key or AWS resources. M2 still includes multimodal-owned live wiring and denial tests; do not claim every multimodal responsibility ends at M1.

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

## Responsibility matrix

These are team responsibilities, not user roles implemented by this service.

| Work | Accountable team | Multimodal contribution | Handoff |
| --- | --- | --- | --- |
| User sign-in, MFA, memberships, authorization | FloBrain backend | Require trusted authorized operation context | B2/B3 |
| Credential submission and protected storage | FloBrain backend | Read only through agreed secure interface; no key-management UI/API | B1 |
| Credential ownership and provider/model/source selection | FloBrain backend | Verify scoped bindings and supported configuration | B2 |
| Credential validation | Multimodal | Provider-specific access check and version-bound safe result | B5 |
| Save replacement / atomic activation / disable / delete | FloBrain backend | Validate candidate, respect selected active state/version | B4 |
| Recovery / provider-account revocation | Backend/platform and account owner | Stop using denied credentials; provide sanitized incident evidence | Operations checklist |
| Provider adapters and inference | Multimodal | Implement, test, normalize errors/usage, prevent fallback | T2-T4 |
| Frontend and customer notices | Frontend/product | Explain validation outcomes and cost/data implications for their contract | B5/B6 |
| Service authentication and route exposure | Backend/platform with multimodal integration | Enforce the agreed service guard; test denial | B3 |
| Cloud resources, secret-store operation, observability platform | Platform/backend owners | Document runtime needs and safe telemetry fields | B1/B7 |
| Staging/release/rollback | Lead + platform/backend | Provide tested artifact and failure/rollback evidence | T6/T7 |

Named teammate assignments are not provided. The lead assigns humans to the suggested roles in the plan; AI must not invent names or commitments. Responsibility transfer does not remove security acceptance checks.
