# Provider Integration Delivery Plan

Revision 2.1, 2026-09-19, with coordination corrections C1-C3 added 2026-10-16. Replaces the old all-platform Phase 0-7 plan. Local design L1-L8 was accepted as written by the lead (Mani) on 2026-10-23; see the review record.
Current state (2026-10-23): T1 L1-L8 accepted.

- **Core track complete and shared:** T2.1-T2.3 accepted by Mani. On origin, T2.1 is `a13d32d` (a rewrite of `8227c8e` with an identical tree) and T2.2-T2.3 is `e240bd2`.
- **Taken over locally (not pushed):** the T3 takeover, the Python 3.12 environment docs (`9e62cd6`) and the cherry-picked adapter draft (`6050f9b`, author Sukhpreet).
- **T3 complete:** T3.1 and T3.2 implemented and accepted by Mani on 2026-10-23, committed locally together (not pushed; no independent reviewer).
- **T4.1 implemented and accepted by Mani on 2026-10-23** (uncommitted; no independent reviewer).
- **T4.2 and review fix F1 accepted by Mani on 2026-10-23** (no independent reviewer). R1-R4 fixed; full suite **194/194** in `.venv`; R5-R9 are recorded follow-ups. T4.1, T4.2 and F1 are committed locally together (not pushed).
- **Still to do:** the M1 sign-off decision (not yet given). M2 stays blocked on B1-B7.
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
| Python 3.12 environment | Lead (Mani) approved on 2026-10-23 | Python 3.12.10 installed for the user via winget; project `.venv` from the unchanged `requirements.txt`; versions recorded below |
| T3 takeover | Lead (Mani) decided on 2026-10-23; adapter owner unavailable | Mani owns T3.1-T3.2; draft `f7fde62` reused with credit via a separately approved cherry-pick; her branch untouched; no independent reviewer (recorded risk) |
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
| T1 | Review scope, L1-L8 local contract, and acceptance cases; lead + backend liaison | Revision 2.1 documents available | L1-L8 accepted 2026-10-23 (Mani, lead); TC expectation tables accepted and backend contact named (Indra Araujo (backend team lead)) by Mani on 2026-10-23 | Accept/amend each L decision, first-provider sequence and named owners; identify backend contact and live-only blocked decisions |
| T2 | Synthetic provider-module scaffold and contract tests; integration engineer | T1 approves local scope; task edit plan approved | In progress: T2.1 accepted and shared 2026-10-23; Core track complete: T2.1, T2.2 and T2.3 accepted 2026-10-23 (Mani); T2.2/T2.3 committed locally, not pushed | Fake credential reader and fake provider, safe typed results, denial tests; no external I/O |
| T3 | First provider adapter and validation mapping using mocked transport; provider engineer | T1 accepted and the T2.1 checkpoint implemented, tested and reviewed; may then run alongside T2.2/T2.3; chosen provider and methods reviewed; dependency action approved if needed | In progress: **taken over by Mani 2026-10-23**; draft cherry-picked as `6050f9b`; Complete: T3.1 and T3.2 accepted 2026-10-23 (Mani; no independent reviewer); committed locally, not pushed | Provider-specific unit tests, bounded calls, usage/error mapping, request-scoped client cleanup |
| T4 | Processing-path integration behind a fail-closed boundary; integration engineer + QA | T2 and T3 both pass review and are combined; local handler contract/compatibility assumptions approved in T1; no exposed API change | Complete: T4.1, T4.2 and review fix F1 accepted 2026-10-23 (Mani; no independent reviewer); committed locally, not pushed; R5-R9 follow-ups | Text/audio parity, preserved fields, no shared-key/cache/echo path in new flow, local fail-closed handler and bypass tests; externally reachable integration deferred to T5/T6 |
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
| Adapter (T3) | Mani since 2026-10-23 (originally the teammate on `Sumukhi_First_Multi_Model_Branch`, now unavailable) | `services/provider_integration/adapters/__init__.py`, `adapters/openai.py`; `test_openai_adapter.py`, `test_openai_transport.py`, `test_openai_validation.py` |

Do not edit the other track's files without coordinating first. Record T2/T4 evidence separately from T3 evidence and reconcile both during integration.

**T3 takeover (2026-10-23).** The adapter owner is unavailable, and the lead (Mani) took over T3.1-T3.2.

- **Reuse with credit.** The draft `f7fde62` on `origin/Sumukhi_First_Multi_Model_Branch` is reused with credit: it is brought onto `Mani's_First_Multi_Model_Branch` by a separately approved cherry-pick that keeps her authorship. It is then reworked against the shared interfaces and the findings in `docs/reviews/2026-10-16-t3.1-openai-adapter-review.md`. Her branch is left untouched; no force push or rewrite.
- **Combining the tracks.** With one owner on one branch, "combined" in step 4 above means T3 is committed on the core branch. There is no separate branch merge.
- **Guardrails kept for T3.** The adapter-track rules still apply:
  - adapter tests use shared types and mocked transport only, independent of the orchestrator;
  - SDK preflight and dated official sources come before coding;
  - no dependency or model changes without approval;
  - T3 evidence is labelled separately;
  - core files change only through an agreed interface change.
- **No independent reviewer.** The two-person review cross-check no longer exists. Mitigations: mutation checks, a separate code review of the adapter before M1, and a request for an independent reviewer (for example the original PRD reviewer) because the adapter handles real keys. M1 sign-off records whether that review happened.

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

Card status: **T2.1 accepted 2026-10-23 by Mani** (evidence below; shared as `8227c8e`); **T2.2 and T2.3 accepted 2026-10-23 by Mani** (committed locally, not pushed); all other cards **not started** (T3.1 has only the pre-checkpoint draft described above). Paths below are relative to `services/provider_integration/` and `tests/provider_integration/` unless explicitly stated. Every card needs its own edit-plan approval; accepting T1 is design approval, not unlimited coding authorization. Update status with actual evidence, not the existence of these cards.

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

### T2.2 evidence — 2026-10-23 (core track)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani (core owner). Edit plan approved by the lead on 2026-10-23, including the reader denial-code mapping recorded in technical design L3. Reviewer decision: **accepted by Mani on 2026-10-23**; the gaps listed below remain open |
| Scope | Test-only fakes and admission tests. **No production code changed** (`git diff -- services` empty) |
| Requirements / tests | PI-02, PI-03, PI-05, PI-08, PI-09, PI-12. Reader/verifier-level portions of TC-02, TC-03, TC-05, TC-06 and TC-13 |
| Environment | Python 3.13.14 (approved exception), standard library only, no installs. `asyncio.Barrier` requires Python 3.11 or later, which the convention already requires |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **86 discovered / 86 passed / 0 failed / 0 errors / 0 skipped** (71 T2.1 + 15 T2.2) |

**Files added**
- `tests/provider_integration/fakes.py`: `FakeClock`, `PauseGate`, `FakeContextVerifier`, `FakeCredentialStore` (atomic reader with test-only `add_pending`/`rotate`/`disable`/`delete` and `backend_accepts`), plus a network guard that allows only loopback.
- `tests/provider_integration/test_admission.py`

**Additional checks**
- **Stability:** `test_admission.py` passed 10 of 10 repeated runs. Ordering is fixed with pause gates and barriers, not sleeps.
- **First-run failures:** the first full run had 2 failures. Both were assertion mistakes in the new tests (they assumed no other lease was held), not defects in the fakes. I fixed the assertions and re-ran.
- **Mutation check:** ten deliberate defects in the fakes each made `test_admission.py` fail:
  - pending admitted for invoke
  - admission without the lock
  - secret cached per record
  - provider/source mismatch ignored
  - lease never released
  - rotation leaving the old version active
  - backend accepting stale results
  - context targets unchecked
  - expiry unchecked
  - verifier ignoring the binding

**Gaps and risks**
- The orchestrator re-check of a tampered reader snapshot, and the "zero provider calls" assertions, are T2.3.
- Handler-level untrusted-context tests are T4.1.
- Real backend atomicity is M2 (B4).
- The fakes simulate the backend contract; they are not backend evidence.
- Results must be re-run on 3.11/3.12 before M1 sign-off.

### T2.3 evidence — 2026-10-23 (core track)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani (core owner). Edit plan approved by the lead on 2026-10-23, with decisions D1-D5 (recorded in the technical design and review record). Reviewer decision: **accepted by Mani on 2026-10-23**; the gaps listed below remain open |
| Scope | New production file `services/provider_integration/orchestrator.py`. Test additions to `fakes.py` (`ScriptedAdapter`/`ScriptedSession`, `TamperingReader`, `RaisingReader`, `Harness`, `FAST_LIMITS`). New `test_orchestrator.py`, `test_limits.py`, `test_validation.py`. No other production file changed; no routes, handler or wiring |
| Requirements / tests | PI-01, PI-03, PI-04, PI-06, PI-07, PI-09, PI-11. Core portions of TC-02, TC-03, TC-04 (core half per C2), TC-05, TC-07, TC-08, TC-10, TC-11, TC-12 |
| Environment | Python 3.13.14 (approved exception), standard library only, no installs. `asyncio.timeout`/`timeout_at` require Python 3.11 or later, which the convention already requires |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **120 discovered / 120 passed / 0 failed / 0 errors / 0 skipped**: `test_contracts` 71, `test_admission` 15, `test_orchestrator` 15, `test_limits` 11, `test_validation` 8 |

**Additional checks**
- **Stability:** 10 repeated full runs, all OK.
- **Warnings:** `python -X dev -W always` reported no warnings, un-awaited coroutines or unclosed resources.
- **First-run failures:** the first full run had 2 failures. Floating-point rounding made the remaining time passed to a step slightly above its call limit. Fixed in the orchestrator by passing `min(call limit, remaining)` and classifying overall-deadline timeouts by which limit was binding. Re-run clean.
- **Mutation check:** fifteen deliberate orchestrator defects each made the suite fail:
  - lease re-check skipped
  - a hidden generation retry
  - input echoed on failure
  - capacity never released
  - capacity unchecked
  - generation after a failed transcription
  - empty generation accepted
  - key-containing output accepted
  - local denial reported as `rejected`
  - rate limit treated as a rejection
  - usage dropped on error
  - request ID not sanitized
  - context targets unchecked
  - text byte limit missing
  - transcript not stripped

  The first hidden-retry mutation was invalid (it never ran); a corrected version was caught.
- **Scope:** `git diff -- services main.py api schemas.py requirements.txt minicpm_test_case` is empty for tracked files; `orchestrator.py` is the only new production file.

**Gaps and risks**
- The real OpenAI adapter and its transport (response byte cap, redirects, TLS) are T3.
- Handler, wiring, verifier deadline and legacy projection are T4.1.
- Logging, filesystem leakage and full isolation are T4.2.
- These are local double-based results, not live evidence.
- Results must be re-run on 3.11/3.12 before M1 sign-off.
- The shared interface is unchanged from the `8227c8e` checkpoint. The adapter owner still has to confirm `StepOutput`/`ProbeOutcome`/`ProviderOperationError` and the D1/D4 semantics before building on them.

### Environment setup and T3.1 SDK preflight — 2026-10-23

**Approval and setup**
- **Approval:** the lead (Mani) approved installing Python 3.12.10 and creating a project `.venv` from the pinned `requirements.txt`. `requirements.txt` was not changed and no lockfile was created; `.venv/` is already git-ignored.
- **Install:** a first manual install attempt left no Python 3.12 on this PC, so the approved fallback was used: `winget install --id Python.Python.3.12 --version 3.12.10 -e --source winget --scope user`. The package came from the Microsoft winget repository (publisher Python Software Foundation), installer `https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe`, with winget reporting "Successfully verified installer hash" (manifest SHA256 `67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb`). python.org lists 3.12.10 (2025-04-08) as the newest 3.12 release with a Windows installer.
- **Environment created:** `py -3.12 -m venv .venv`, then `.venv\Scripts\python -m pip install -r requirements.txt` (pip 25.0.1, not upgraded).
- **Dependency check:** `pip check` reported no broken requirements.

**Installed versions (`pip freeze`)**

| Package | Version |
| --- | --- |
| Python | 3.12.10 (64-bit) |
| openai | **1.109.1** (resolved from `>=1.0.0,<2.0.0`) |
| httpx | **0.28.1** |
| httpcore | 1.0.9 |
| pydantic / pydantic_core | 2.6.1 / 2.16.2 |
| fastapi / starlette / uvicorn | 0.109.2 / 0.36.3 / 0.27.1 |
| python-dotenv / python-multipart | 1.0.1 / 0.0.27 |
| requests / urllib3 / certifi | 2.34.2 / 2.8.0 / **2026.10.23** |
| anyio / sniffio / h11 / idna / jiter / distro / tqdm / click / colorama / typing_extensions / annotated-types / charset-normalizer | 4.15.1 / 1.3.1 / 0.16.0 / 3.20 / 0.18.0 / 1.9.0 / 4.70.1 / 8.5.0 / 0.4.6 / 4.16.0 / 0.8.0 / 3.5.2 |

Note: `certifi 2026.10.23` was published the same day it was installed. It is an indirect dependency of `requests`, which only the GPU benchmark uses. Watch for a quick follow-up release.

**Python 3.12 regression run (T2.1-T2.3)**
- Command: `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v`
- Result: **120 discovered / 120 passed / 0 failed / 0 errors / 0 skipped**; 3 further repeats OK; no warnings under `-X dev -W always`.
- This satisfies the 3.11/3.12 re-run condition for T2.1-T2.3. The final T4.2 full-suite run must also use this environment.

**T3.1 SDK preflight (read-only, no client created, no network)**

| Area | Finding |
| --- | --- |
| `AsyncOpenAI.__init__` parameters | `api_key`, `organization`, `project`, `webhook_secret`, `base_url`, `websocket_base_url`, `timeout`, `max_retries`, `default_headers`, `default_query`, `http_client` |
| Environment reads in `openai._client` | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID`, `OPENAI_WEBHOOK_SECRET`; each is read when the argument is not supplied |
| `httpx.AsyncClient` defaults | `verify=True`, `follow_redirects=False`, `trust_env=True` (picks up proxy/TLS environment settings). `openai._base_client` references `follow_redirects`; `httpx.MockTransport` is available |
| `chat.completions.create` | Accepts `messages`, `model`, `max_tokens` (and `max_completion_tokens`), `temperature`, `store`, `stream`, `timeout`, `extra_*` |
| `audio.transcriptions.create` | Accepts `file`, `model`, `response_format`, `language`, `prompt`, `temperature`, `stream`, `timeout` |
| Exceptions | `APIError` fields: `status_code`, `code`, `type`, `param`, `body`, `request_id`, `response`. Status classes: 400 `BadRequestError`, 401 `AuthenticationError`, 403 `PermissionDeniedError`, 404 `NotFoundError`, 409 `ConflictError`, 422 `UnprocessableEntityError`, 429 `RateLimitError`; `InternalServerError` has no fixed status. `APITimeoutError` subclasses `APIConnectionError`, so timeouts must be classified first |

**Implications for T3.1/T3.2** (to be covered in their plans, not yet implemented):
- Always pass the key and the configured destination explicitly.
- Organization/project settings must not be inherited from the environment: verify how the SDK treats an explicit value versus `None`, and strip or deny those headers in the owned transport if needed.
- Use an owned `httpx.AsyncClient` with `trust_env=False`, `follow_redirects=False`, `verify=True`, and set the SDK's `max_retries=0`.
- The installed SDK supports the L6 request fields (`max_tokens`, `store`, `response_format`) without a dependency change.
- The official OpenAI documentation re-check (last done 2026-09-19) is still to be done in the T3.1 plan.

### T3.1 evidence — 2026-10-23 (adapter track, owner Mani after takeover)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani. Edit plan approved by the lead on 2026-10-23 with decisions A1-A6 (A2: HTTP 403 -> `ACCESS_DENIED` / indeterminate). Reviewer decision: **accepted by Mani on 2026-10-23**; no independent reviewer (see T3 takeover); the gaps listed below remain open |
| Scope | Rewrote `services/provider_integration/adapters/openai.py` on the shared ports (draft `f7fde62` by Sukhpreet, reused with credit). Replaced `tests/provider_integration/test_openai_adapter.py` (her 4 tests; her status cases are kept in the new matrix). `adapters/__init__.py` unchanged. **No core files changed**; no shared-interface change |
| Requirements / tests | PI-01, PI-04, PI-06, PI-07, PI-08, PI-10. Adapter portions of TC-01, TC-07, TC-08, TC-10, TC-11 and the environment/redirect core of TC-09 |
| Environment | `.venv`: Python 3.12.10, openai 1.109.1, httpx 0.28.1 (see the environment section). All network access is denied by the test guard; the SDK talks only to `httpx.MockTransport` |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **137 discovered / 137 passed / 0 failed / 0 errors / 0 skipped**: contracts 71, admission 15, orchestrator 15, limits 11, validation 8, OpenAI adapter 17 |

**Additional checks**
- **Stability:** 5 repeated full runs, all OK.
- **Warnings:** `-X dev -W always` reported no warnings, un-awaited coroutines or unclosed resources. asyncio debug mode prints slow-callback notices for the SDK's first call; these are informational.
- **First-run errors:** 2 errors were in the new tests. Replacing `httpx.AsyncClient` with a mock broke the SDK's `isinstance` check. Fixed by recording through a real `httpx.AsyncClient` subclass. Adapter code was unchanged by the fix.
- **Mutation check:** fourteen deliberate adapter defects each made `test_openai_adapter.py` fail:
  - environment key fallback
  - SDK retries = 2
  - following redirects
  - `trust_env` on
  - inherited organization/project
  - `store=true`
  - request ID taken from the body `id`
  - 403 mapped as a capability rejection (no A2)
  - timeouts classified after connection errors
  - debug logging allowed
  - fixed upload filename
  - request ID not sanitized
  - clients never closed
  - unknown 5xx unmapped
- **Python versions:** the system Python 3.13 has no `openai`, so the adapter test module cannot be imported there. Use `.venv`.

**What the adapter now does**
- One `AsyncOpenAI` per lease, with the lease key and `config.destination` passed explicitly.
- `max_retries=0`, and an owned `httpx.AsyncClient(trust_env=False, follow_redirects=False, verify=True)`.
- Environment-derived organization/project are cleared (A4).
- Opening a session fails closed while the openai/httpx/httpcore loggers are at DEBUG (A3).
- Requests follow L6: the configured system prompt, `max_tokens`, `temperature`, `store=False`, non-streaming; transcription uses `input.<format>` and `response_format=json`.
- Usage is copied from the reported values (chat tokens; transcription tokens or duration), with `x-request-id` filtered.
- Errors are classified with SDK exception types plus a bounded code/type. They raise `ProviderOperationError` carrying null usage and the sanitized request ID, and keep no message, body or cause.
- `validate_access` returns `UNSUPPORTED_OPERATION` until T3.2 (A6).

**Gaps**
- T3.2: validation probes, the response-byte cap before parsing, redirect/TLS/proxy transport tests, and `test_openai_transport.py` / `test_openai_validation.py`.
- No combined orchestrator + real adapter run yet (T4).
- No live API evidence.
- Models are deprecated upstream (A1, see L6).

### T3.2 evidence — 2026-10-23 (adapter track, owner Mani)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani. Edit plan approved by the lead on 2026-10-23 with decisions B1-B6. Reviewer decision: **accepted by Mani on 2026-10-23**; no independent reviewer; the gaps listed below remain open |
| Scope | Extended `services/provider_integration/adapters/openai.py` with a per-session `GuardedTransport` and the L6 validation probes. New `test_openai_transport.py` and `test_openai_validation.py`. In `test_openai_adapter.py`, the constructor tests now pass `max_response_bytes`, and the A6 placeholder test is replaced by a probe smoke test. **No core files changed**; no shared-interface change. The adapter constructor now requires `max_response_bytes` (wiring supplies L5 `max_response_body_bytes`) |
| Requirements / tests | PI-03, PI-08, PI-09, PI-10, PI-11. TC-04 adapter half (C2), TC-09 adapter, TC-12 adapter |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1; network guard active; `httpx.MockTransport` only |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **157 discovered / 157 passed / 0 failed / 0 errors / 0 skipped**: contracts 71, admission 15, orchestrator 15, limits 11, validation 8, OpenAI adapter 17, OpenAI transport 13, OpenAI validation 7 |

**Additional checks**
- **Stability:** 5 repeated full runs, all OK.
- **Warnings:** `-X dev -W always` reported no warnings or unclosed resources.
- **First-run error:** 1 error in a new test fixture. An `httpx.Response` built from gzip bytes is decoded eagerly by httpx. Fixed by streaming the fixture body; adapter code was unchanged by the fix.
- **Mutation check:** fifteen deliberate T3.2 defects each made the OpenAI test files fail:
  - stream cap disabled
  - Content-Length ignored
  - compressed responses allowed
  - destination guard off
  - organization/project headers kept
  - Accept-Encoding not forced
  - transport `trust_env` on
  - probe sends a system prompt
  - probe `max_tokens` 16
  - empty probe text treated as valid
  - 403 probe treated as rejected
  - SDK retry 1
  - overflow reported as an outage
  - a blocked request reported as an outage
  - probe uses a customer-style filename

**What T3.2 adds**
- **Guard on every request.** Only requests whose scheme, host, port and path prefix match `config.destination` are sent (B3: otherwise `INTERNAL_ERROR`, nothing sent). Organization/project headers are removed (B4) and `Accept-Encoding: identity` is forced (B2).
- **Guard on every response.**
  - A non-identity `Content-Encoding` is refused before reading.
  - A declared `Content-Length` over the cap is refused before reading.
  - Otherwise raw bytes are counted while streaming; reading stops once the cap is exceeded (B1: `PROVIDER_RESPONSE_INVALID`). This applies to error bodies too.
  - The cap is counted per request.
- **Production transport.** `httpx.AsyncHTTPTransport(verify=True, trust_env=False, retries=0)`; redirects are never followed.
- **Probes (L6, B5/B6).**
  - Text probe: user `Reply with OK.`, `max_tokens=8`, `temperature=0`, `store=False`. A non-empty reply is valid.
  - Audio probe: the in-memory 1 s silent WAV (32,044 bytes) as `input.wav`, `response_format=json`. Any text string, including empty, is valid.
  - One request per probe. Failures are returned as `ProbeOutcome`: `rejected` only for `CREDENTIAL_REJECTED` / `CAPABILITY_DENIED`, otherwise `indeterminate`.

**Gaps**
- The real adapter is not yet run under the orchestrator and handler (T4.1/T4.2).
- No live API, TLS or proxy evidence (M2).
- The models are deprecated upstream (A1).
- No independent review.

### T4.1 evidence — 2026-10-23 (integration)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani. Edit plan approved by the lead on 2026-10-23 with decisions C1-C6. Reviewer decision: **accepted by Mani on 2026-10-23**; no independent reviewer; the gaps listed below remain open |
| Scope | New `services/provider_integration/handler.py` (`Handler.process`/`validate`, the parsers, `legacy_success`) and `wiring.py` (`build_unconfigured`, `build_handler`, deny-all verifier/reader). New `tests/provider_integration/test_handler.py`. Core, adapter and legacy files are unchanged (`git diff` empty for `__init__`, types, ports, errors, config, orchestrator, adapters, `services/openai_service.py`, `api/`, `main.py`, `schemas.py`, `requirements.txt`) |
| Requirements / tests | PI-02, PI-04, PI-06, PI-08, PI-10, PI-12. Local portions of TC-02, TC-10, TC-13, TC-14 |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1, pydantic 2.6.1 (only `legacy_success` needs it) |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **172 discovered / 172 passed / 0 failed / 0 errors / 0 skipped**: contracts 72, admission 15, orchestrator 15, limits 11, validation 8, OpenAI adapter 17, OpenAI transport 13, OpenAI validation 7, handler 14 |

**Test change to an accepted file.** `test_contracts.py` (T2.1) had a scan forbidding any core module from referencing `provider_integration.adapters`. L1 assigns adapter composition to `wiring.py`, so the scan now exempts only `wiring.py` from the adapter tokens; every other token still applies to wiring. A new, stricter `test_wiring_imports_adapters_only_lazily` forbids any module-level adapter import in every core module. Wiring's docstring was reworded so the existing "no fakes reference" guard still applies unchanged.

**Additional checks**
- **Stability:** 5 repeated full runs, all OK.
- **Warnings:** `-X dev -W always` reported no warnings.
- **Defect found and fixed during the work.** `test_parse_failures` showed that `CredentialSource` (a `str` subclass) passed the parser's string check. The parser now requires exact `str` for string fields, as C1 intends.
- **Test bugs fixed.** A duplicate keyword argument in two parse cases, and a deadline test that reused an already-released gate. Both were fixed in the test only.
- **Mutation check:** fourteen deliberate defects each made the relevant tests fail:
  - binding re-check removed
  - kind re-check removed
  - unknown fields allowed
  - verifier errors propagated
  - `started_at` not passed
  - failures projectable
  - empty audio treated as audio
  - audio settings allowed without audio
  - raw text measured after stripping
  - verify timeout removed (the test hangs)
  - unconfigured verifier allows
  - wiring reads the environment
  - eager adapter import in wiring
  - wiring sets the test transport

**Combined run.** `test_end_to_end_with_real_adapter` drives handler → fake verifier/store → orchestrator → the real `OpenAIAdapter` over `httpx.MockTransport`. It covers text and audio success with legacy projection, a provider 401 → `CREDENTIAL_REJECTED`, and a valid validation probe: 5 requests, all to the configured host with the lease key; no lease or capacity left held.

**Gaps**
- Leakage (logging/trace/filesystem), full isolation and the import-safety suite are T4.2.
- No live verifier/reader/route (M2).
- Existing FastAPI upload routes still read uploads after framework handling; the new module is not connected to them and does not solve spooling (L4).

### T4.2 evidence — 2026-10-23 (integration, M1 regression)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani. Edit plan approved by the lead on 2026-10-23 with decisions E1-E5. Reviewer decision: **accepted by Mani on 2026-10-23**; no independent reviewer; findings R1-R4 fixed by F1 |
| Scope | New `tests/provider_integration/test_isolation.py` (3), `test_leakage.py` (6), `test_import_safety.py` (4). **No production code changed** (`git diff` empty for every file under `services/`, plus `api/`, `main.py`, `schemas.py`, `requirements.txt`) |
| Requirements / tests | PI-02, PI-06, PI-08, PI-09, PI-12. TC-03, TC-08 and TC-14 local portions in full, plus the final regression over all local TC rows |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1, pydantic 2.6.1. This settles the 3.11/3.12 re-run condition for the whole suite |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **185 discovered / 185 passed / 0 failed / 0 errors / 0 skipped**: contracts 72, admission 15, orchestrator 15, limits 11, validation 8, OpenAI adapter 17, OpenAI transport 13, OpenAI validation 7, handler 14, isolation 3, leakage 6, import safety 4 |

**Additional checks**
- **Stability:** 5 repeated full runs, all OK.
- **Warnings:** `-X dev -W always` reported no warnings. The leakage positive control's planted warning is excluded from that scan.
- **Positive control:** `test_watch_detects_leaks` proves that the log, warning, asyncio-handler and file-write channels each report a planted canary.

**Finding recorded during the work.** The installed SDK reads `OPENAI_LOG`, `OPENAI_API_TYPE`, `OPENAI_API_VERSION`, `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_AD_TOKEN` when imported, for its module-level client, which this package never uses. No `OPENAI_API_KEY`/base URL/org/project/webhook/`AZURE_OPENAI_API_KEY` read occurs at import. `test_import_safety.py` pins this exact set. The AD-token read is listed as a residual risk in security-and-operations.

**Mutation check:** 7 of 8 deliberate T4.2 defects were detected.
- Detected:
  - prompt logged by the orchestrator
  - SDK exception logged by the adapter
  - debug file written
  - transcript appended to the result
  - environment key read at import
  - one HTTP client shared across sessions
  - a legacy route importing the new module
- **Survived:** replacing the adapter's `from None` with `from exc`. The T2.1 error class already hides causes (defense in depth), so nothing leaked, but no test detects that single-layer change alone.

**AI code review (E5).** The code-review skill ran at high effort over `services/provider_integration`. Findings were **reported only; none fixed** (each fix needs separate approval):

| # | Severity / angle | Location | Finding |
| --- | --- | --- | --- |
| R1 | Correctness (highest) | `orchestrator.py:186-187`, `225-226` | Capacity release runs after `await self._close(stack)` in the same `finally`. A cancellation that arrives during cleanup skips the release, so the shared gate permanently loses a slot; after 8 such events every request returns `CAPACITY_EXCEEDED` |
| R2 | Altitude | `adapters/openai.py:278` (guard flags) | Guard outcomes are reported through per-session mutable flags, while the SDK already chains the `GuardViolation` as `APIConnectionError.__cause__`. Overlapping requests in one session could misclassify |
| R3 | Correctness | `errors.py:81` | `ProviderIntegrationError` / `ProviderOperationError` cannot be pickled or copied, because the default `__reduce__` passes the message where an `ErrorCode` is required |
| R4 | Correctness | `orchestrator.py:231` | A naive injected `utc_now` makes `invoke`/`validate` raise `ValueError` instead of returning a safe result |
| R5 | Correctness (low) | `adapters/openai.py:267` | httpx timeouts are per phase. Used directly, a session is not bounded to `remaining_seconds`; only the orchestrator's outer deadline bounds the total |
| R6 | Reuse | `types.py:398`, `orchestrator.py:65`, `adapters/openai.py:80` | The rejection-code set is defined three times |
| R7 | Reuse | `handler.py:83` | `_utf8_length` duplicates `orchestrator.py:80` |
| R8 | Reuse | `adapters/openai.py:442` | Positive-number validation re-implements the config helpers |
| R9 | Efficiency | `adapters/openai.py:386` | The constant silent WAV is regenerated for every audio probe |

**Gaps:**
- R1-R9 are untriaged.
- No independent human review.
- No live evidence (M2).

### Review fix F1 evidence — 2026-10-23 (findings R1-R4)

**Summary**

| Item | Detail |
| --- | --- |
| Owner / approval | Mani. Fix plan approved by the lead on 2026-10-23 (shielded cleanup, cause-chain guard classification, picklable errors, clock validation). Reviewer decision: **accepted by Mani on 2026-10-23**; no independent reviewer |
| Scope | `orchestrator.py` (R1, R4), `errors.py` (R3), `adapters/openai.py` (R2), `tests/provider_integration/fakes.py` (`ScriptedAdapter.close_gate`). New tests in `test_orchestrator.py` (6), `test_contracts.py` (1) and `test_openai_transport.py` (2). In `test_openai_transport.py::test_guard_blocks_unapproved_urls_before_sending`, the removed `guard.blocked`/`reset()` checks were replaced by `GuardViolation.kind`. No port, type, route, legacy or dependency changes |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1 |

**Test-first evidence.** The 10 new or updated tests were run on the unfixed code first: **10 run, 15 failures, 8 errors**, each for the expected reason:

| Finding | What the unfixed code did |
| --- | --- |
| R1 | Capacity never released ("condition not reached" ×3); after 8 cancellations a normal request was refused |
| R2 | The concurrent test reproduced the cross-request misclassification: a connection error was reported as `PROVIDER_RESPONSE_INVALID`; the flags existed; `GuardViolation` had no `kind` |
| R3 | `TypeError: code must be an ErrorCode` on unpickle |
| R4 | No construction-time rejection; a bad clock raised instead of failing safe |

After the fixes, the same 10 passed.

**Full suite**
- Command: `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v`
- Result: **194 discovered / 194 passed / 0 failed / 0 errors / 0 skipped**: contracts 73, admission 15, orchestrator 21, limits 11, validation 8, OpenAI adapter 17, OpenAI transport 15, OpenAI validation 7, handler 14, isolation 3, leakage 6, import safety 4.
- 5 repeated full runs OK; no warnings under `-X dev -W always` (only asyncio's informational slow-callback notices).

**Reverse check and regression**
- All 6 reverse mutants made their new tests fail again: unshielded cleanup, guard kind ignored, shared last-violation state, no `__reduce__`, clock unchecked at construction, clock readings unchecked.
- All 8 regression mutants were still detected: capacity never released, lease re-check skipped, input echo, stream cap off, destination guard off, blocked→outage, overflow→outage, error cause exposed.

**What changed**

| Finding | Change |
| --- | --- |
| R1 | Cleanup runs in a shielded task (strong reference kept) that closes the session and lease within the cleanup limit and then releases capacity. Caller cancellation still propagates immediately |
| R2 | `GuardViolation(kind)` is recovered from the SDK exception's cause/context chain (bounded, cycle-safe); the transport keeps no per-request outcome state |
| R3 | `__reduce__` rebuilds from `code` (and `usage`) only |
| R4 | `utc_now` must be callable and return aware UTC at construction. A bad reading during a request → `INTERNAL_ERROR` / `indeterminate` before any reader call. A bad reading when stamping a validation result → `indeterminate / INTERNAL_ERROR`, with `checked_at` = the request's last good reading from the same clock |

**Open follow-ups (recorded, not fixed):** R5-R9.

T3.1 preflight does not install anything. If a compatible approved environment is absent, report that and request setup approval. Current requirements are version ranges, not a lockfile; do not quietly upgrade or claim tests ran against an unspecified SDK. T3.2 may need a transport wrapper but must not introduce a separate infrastructure service.

### T1 review meeting checklist

- [ ] Confirm PI-01 through PI-12 scope and OpenAI-first slice; future providers are separately selected work.
- [x] Accept/amend L1-L8 together, including internal fields, limits, probes, no route wiring during M1, and proposed file ownership. (Accepted as written, Mani, 2026-10-23.)
- [x] Accept local TC expectations; do not demand live-backend proof for M1 or count fake proof toward M2. (Accepted by Mani, 2026-10-23.)
- [x] Assign named owner/reviewer for each next card and an integration contact; record unavailable contacts honestly. (Owner and reviewer: Mani, after the adapter owner became unavailable. Integration/backend contact: Indra Araujo (backend team lead), named 2026-10-23.)
- [x] Record reviewer/date/revision/conditions in the review record. Leave B1-B7 unresolved unless actual answers and approval exist. (Recorded 2026-10-23; B1-B7 unresolved.)
- [ ] Approve a separate bounded T2.1 implementation plan when ready. No main-branch merge, dependency installation or deployment is implicitly authorized.

After these review decisions, no additional product/architecture invention should be necessary to start T2.1. A discovered contradiction or SDK incompatibility must still be reported instead of hidden.

### M1 handoff package — 2026-10-23

**Status.** The local multimodal module (T2.1-T4.2) is implemented and tested offline (194/194). **M1 sign-off is pending.** It needs:
- the lead's M1 sign-off decision (T1-T4.2 and F1 are accepted; R5-R9 are recorded low-severity follow-ups).

The T1 leftovers were settled on 2026-10-23: TC tables accepted; backend contact Indra Araujo (backend team lead).

There was no independent reviewer. Nothing here is live, backend or production evidence.

**Contract and code**

| Item | Value |
| --- | --- |
| Contract version | Revision 2.1, with C1-C3 (coordination), T1 acceptance of L1-L8, T2.1 interface clarifications, the T2.2 reader denial-code mapping, D1-D5 (orchestrator), A1-A6 (adapter, including the A2 amendment to L6), B1-B6 (transport/probes) and C1-C6 (handler/wiring). All are recorded in the technical design and review record |
| Code checkpoint | `origin/Mani's_First_Multi_Model_Branch` at `23bd8b5` (T2.1-T3.2). T4.1 (`handler.py`, `wiring.py`, `test_handler.py`, scoped `test_contracts.py` change), T4.2 (three test files) and review fix F1 are committed locally together on 2026-10-23 (not pushed) |
| Entry points (in-process only) | `wiring.build_unconfigured()` (deny-all default); `wiring.build_handler(verifier=..., reader=..., providers=..., limits=...)`; `Handler.process` / `Handler.validate`; `handler.legacy_success` |
| Fake conformance tests for a future real reader/verifier | `test_admission.py` (denial matrix, state table, ordering, rotation, stale results, outage) and `test_handler.py::test_untrusted_context` / `test_misbehaving_verifiers_are_denied`. A real reader/verifier should pass equivalent cases |
| Limit profile | L5 as accepted (`config.LOCAL_LIMIT_PROFILE`): text 64 KiB; prompt and transcript 128 KiB each; audio 10 MiB; output 64 KiB; response body 1 MiB; deadlines 90 s / 20 s; verify and admit 5 s each; calls 30 / 60 / 15 s; connect 5 s; cleanup 2 s; 8 concurrent; zero retries; no redirects |
| Installed versions | Python 3.12.10, openai 1.109.1, httpx 0.28.1, httpcore 1.0.9, pydantic 2.6.1 (full `pip freeze` in the environment section) |

**Synthetic result shapes (internal, not a wire format; B6 decides HTTP)**

- **Success:** `InvocationResult(provider="openai", model="gpt-4o-mini", file_type=text, outcome=success, result="Synthetic answer", usage=(UsageEntry(generate_text, gpt-4o-mini, input_tokens=10, output_tokens=5, total_tokens=15, provider_request_id="req_chat_1"),))`. Legacy projection: `{"result": "Synthetic answer", "model": "gpt-4o-mini", "file_type": "text"}`.
- **Provider failure:** `InvocationResult(outcome=error, result=None, error_code=CREDENTIAL_REJECTED, usage=(UsageEntry(generate_text, gpt-4o-mini, provider_request_id="req_err_1"),))`. It cannot be projected.
- **Boundary failure:** `BoundaryFailure(request_id=<local UUID>, error_code=ACCESS_DENIED, outcome=error, result=None, usage=())`, with no scope, provider or model reflected.
- **Validation:** `ValidationResult(binding=<exact checked version, e.g. v2>, target=generate_text/gpt-4o-mini, status=valid|rejected|indeterminate, reason_code=..., usage=(...))`. `rejected` only for `CREDENTIAL_REJECTED` / `CAPABILITY_DENIED`.

**Known legacy and residual risks (unchanged by M1)**
- `/process` and `/openAI` remain unauthenticated and use the shared environment key, the global client, the prompt cache and echo-on-error.
- Uploads are read after FastAPI multipart handling; spooling is not solved.
- Raw exception strings are logged.
- These routes are disconnected from the new module and must not be described as safe.
- Upstream deprecations: `gpt-4o-mini` shuts down 2027-01-14 and `gpt-4o-mini-transcribe` 2027-02-26 (A1).
- The SDK's import-time environment reads are listed under "Implementation findings" in security-and-operations.

**B1-B7 handoff (backend owner and lead)**

| ID | Question | Status | Contact |
| --- | --- | --- | --- |
| B1 | Protected storage and retrieval/decryption interface for the real CredentialReader | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B2 | Source/schema of the trusted binding; customer/platform source support | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B3 | Service authentication, request integrity, expiry/replay for the real ContextVerifier | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B4 | Lifecycle states, version IDs, atomic admission/rotation ordering (the fake models one option) | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B5 | When validation is requested; probe cost/rate policy; result persistence | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B6 | Wire format, HTTP status mapping, existing-caller migration, rollback | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |
| B7 | Live limits, memory-only upload handling before spooling, telemetry/retention | Unresolved; questions drafted 2026-10-23, not yet sent | Indra Araujo (backend team lead) |

**Next approvals**
1. Done 2026-10-23: the lead accepted T4.2 and review fix F1 (R1-R4 fixed); R5-R9 remain follow-ups to schedule.
2. Commit/push of T4.1-T4.2 (Git approval).
3. M1 sign-off.
4. Republishing the Notion mirror (external publish).
5. M2 starts only after B1-B7 are answered and approved.

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
