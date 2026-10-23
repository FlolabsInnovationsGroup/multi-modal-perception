# Provider Integration Test and Acceptance Plan

Revision 2.1, 2026-09-19, with coordination corrections C1-C3 added 2026-10-16 (TC-04 split into core and adapter test files; no assertion removed). Status: **L1-L8 accepted 2026-10-23; T2.1 contract tests implemented and passing locally (71/71, Python 3.13.14), accepted by Mani 2026-10-23**; **T2.2 admission tests implemented, accepted by Mani 2026-10-23**; **T2.3 orchestrator tests implemented (120/120 total passing), accepted by Mani 2026-10-23**. No other feature test exists yet. Other named tests below are implementation deliverables, not files claimed to exist.
Requirements live in the PRD; this document defines verification, not additional platform scope.

## Test cases

| ID | Scenario | Expected evidence | Requirements |
| --- | --- | --- | --- |
| TC-01 | Adapter boundary with fake and first provider adapter | Common operations; unsupported provider/operation rejected without alternate call | PI-01, PI-04 |
| TC-02 | Untrusted caller, missing/stale context, changed scope/credential/provider/version | No unauthorized secret read or provider request; safe denial | PI-02, PI-08, PI-12 |
| TC-03 | Two scopes send identical prompts concurrently with different synthetic keys | Correct key/client/result binding; no global cache or response crossover | PI-02, PI-09 |
| TC-04 | Validation valid/rejected/model-denied/timeout/outage/rate/quota | Correct version-bound result; indeterminate is not invalid; no activation | PI-03, PI-07, PI-11 |
| TC-05 | Successful and failed replacement, stale validation result | Exact version reported; backend fixture preserves old active key on failure; live backend proves atomic activation | PI-03, PI-05 |
| TC-06 | Disabled/deleted/pending credential; disable or rotate racing invocation | No new use after agreed admission boundary; pending permitted only for authorized validation; in-flight behavior documented | PI-02, PI-05 |
| TC-07 | Missing/invalid/expired/revoked/rate/quota/timeout/provider failure | No alternate key/source/model/provider/region/endpoint, no echo success; spy on all transports | PI-06 |
| TC-08 | Synthetic canary key/content in SDK, reader, serializer, log/trace and error paths | No secret/content in captured diagnostics, caches, files, queues, outputs other than intended success content | PI-07, PI-08, PI-09 |
| TC-09 | Provider URL/header override, redirect to unapproved destination | Request rejected or safe failure; no key sent to unapproved host | PI-10 |
| TC-10 | Text-only, audio-only, combined input, empty input, provider metadata | Current result/model/file_type behavior preserved or explicitly approved difference; unsupported formats denied | PI-04, PI-12 |
| TC-11 | Usage absent, zero, text and transcription usage, provider request ID | Missing is unavailable not zero; no fabricated totals; IDs bounded/sanitized | PI-07 |
| TC-12 | Payload/upload/time/concurrency boundaries, SDK retries, cancellation | Agreed limits enforced; no unbounded reads/retries, no hidden duplicate calls, clients released, no upload spooling left behind | PI-08, PI-09, PI-11 |
| TC-13 | Backend store/auth outage, real least-privilege denial, stale reader state | Fail closed; no environment-key/mock fallback; scoped real adapter matches fake contract | PI-02, PI-05, PI-12 |
| TC-14 | Route exposure, migration, limited enablement and rollback | BYOK unreachable without trusted service context; no legacy bypass; rollback disables feature without switching keys | PI-06, PI-12 |

## Layers and execution

1. T2: pure unit/contract tests with fake credential reader, fake adapters, and synthetic content, including the core validation path (`test_validation.py`). No network, database, actual key, GPU, or model downloads.
2. T3: first-provider tests with mocked SDK transport and explicit call-count assertions; verify both SDK error mapping and retries, including provider probes and outcomes (`test_openai_validation.py`). T3 may run alongside T2.2/T2.3 after the reviewed T2.1 checkpoint (C1); record its evidence separately from T2/T4 evidence.
3. T4: route/handler regression and boundary tests under mocked dependencies. Preserve MiniCPM work; do not treat model benchmarks as BYOK coverage.
4. T5: agreed backend contract tests, service-authentication denial, actual state/version behavior. Use an approved non-production environment.
5. T6: end-to-end with separately approved staging credentials and minimal synthetic content, leakage/limits/concurrency tests, then release checklist.

Inspect existing tooling first. Standard-library tests may be enough for early modules; adding pytest/httpx or any other package requires dependency approval. Do not install tooling just to run this plan. Record a missing check rather than invent success.

Use values such as `test-provider-key-redacted`. Assertions, snapshots, and failure reports must not print real keys. No keys in CI variables, source, commands, chat, screenshots, or fixtures. Approved live secret delivery must use the agreed backend mechanism.

## Acceptance and evidence

For each case record test file/function, environment, exact command, result, requirement IDs, date, and reviewer in the traceability section below.

Mock pass != live backend pass. For T5/T6, specifically prove service caller verification and credential ownership/version checks against the actual integration. Backend lifecycle implementation is tested jointly, not rebuilt here.

Release requires applicable cases passing, B1-B7 resolved, exact limits/configuration recorded, provider enablement checked, no unresolved critical/high leakage or scope-isolation defect, and explicit release/deployment authorization. There is no inherited numeric AWS SLO or 100-request load target; agree the relevant load and pass limits before measuring.

## Local milestone versus release

M1 accepts only the local/mock portions of the cases, including simulated denial and lifecycle boundaries. TC-05/06 real atomic lifecycle behavior, TC-13 real reader permissions, and TC-14 actual service exposure/rollback remain for M2. Record local and live results separately; a simulated backend guarantee is not verified backend behavior.

### Executable local acceptance specification

All filenames below are proposed under `tests/provider_integration/`. Use obvious synthetic keys and content, deterministic scripted provider responses, injected clock/deadlines and async barriers. Never use actual user data to make a fixture realistic. Assertions report only sanitized summaries, not transport call dumps. Every case must fail if the protected behavior is deliberately broken; a test checking only a fake's canned output is insufficient.

| Case / proposed tests | Required M1 assertions | Additional M2 evidence |
| --- | --- | --- |
| TC-01 `test_contracts.py::test_capability_matrix`, `test_openai_adapter.py::test_selected_models` | Only configured operation/model pairs accepted; unsupported choice causes zero provider calls; fake and real adapter satisfy same protocol | Account/model availability and approved live configuration |
| TC-02 `test_admission.py::test_denial_matrix`, `test_handler.py::test_untrusted_context` | Change each scope/ref/version/source/provider/target/kind separately; unknown evidence, expired context, malicious reader snapshot denied; unverified request: zero reader/provider calls; mismatched reader return: zero provider calls | Real verifier integrity, expiry/replay and actual backend authorization denial |
| TC-03 `test_isolation.py::test_two_scopes_same_prompt` | Barrier-overlap two identical prompts with A/B keys and distinct answers; each transport sees only its own key; answers/client instances not shared; repeat request invokes again (no response cache) | Concurrent live boundary coverage using approved staging fixtures |
| TC-04 (core, T2.3) `test_validation.py::test_validation_orchestration` | Validation is separate from invocation; exactly one probe per validation request, never both capabilities implicitly; no customer input passed to the session; no activation; pending version admitted only for validate, and the result carries the exact checked version; local saturation/timeout indeterminate after trusted validation; fake adapter only | Approved live probe/cost policy and account responses |
| TC-04 (adapter, T3.2) `test_openai_validation.py::test_probe_and_outcome_matrix` | L6 status mapping table parameterized; text exactly one probe <=8 output-token budget; audio exactly one in-memory one-second silent WAV; no customer input; successful empty audio transcript is valid; mocked transport only | Approved live probe/cost policy and account responses |
| TC-05 `test_admission.py::test_replacement_and_stale_result` | Pending v2 validates with v2 in result while v1 remains active; failure/timeout doesn't change v1; deletion/replacement during probe yields stale version-bound result; simulated backend rejects it; no activation method on production module | Actual backend atomic activation/stale-result rejection |
| TC-06 `test_admission.py::test_admission_change_order` | Each disabled/deleted/expired/unknown state denied; pending denied for invoke but allowed validate; lock/barrier proves admitted-before-disable may finish, admitted-after denied; old v1 after rotation denied rather than upgraded; cleanup releases lease | Same ordering against actual shared lifecycle authority |
| TC-07 `test_orchestrator.py::test_no_fallback_matrix` | For every failure class, spy all adapters/readers/transports: no alternative selection, no automatic second attempt, no success echo; failure at transcription means zero generation calls | Live failures and rollback cannot select platform/legacy route |
| TC-08 `test_leakage.py::test_canary_all_exits` | Key/content canaries absent in repr/serialization, errors, captured logs, trace hooks, filesystem/temp output and non-content results; key serialization raises; returned key-containing text fails safely; exceptions containing canaries never escape; cancellation checked | Full framework/SDK/agent telemetry and hosting configuration inspection |
| TC-09 `test_openai_transport.py::test_destination_redirect_and_environment` | Requests never honor supplied URL/header overrides or malicious SDK env base/proxy settings; approved host only; 301/302/307/308 give safe failure and zero second request; TLS verification enabled | Approved egress/TLS/proxy configuration and denial at live boundary |
| TC-10 `test_handler.py::test_input_projection_matrix` | Text-only, audio-only, combined, whitespace text, empty audio and successful empty transcript follow L4 exactly; both empty fail; audio requires two allowed targets; preserve three legacy success fields; failed result cannot project to PerceptionOutput | Consumer contract and multipart handling/route migration |
| TC-11 `test_contracts.py::test_usage_and_safe_ids` | Absent usage stays null, explicit zero stays zero, steps remain separate; negative/malformed usage rejected or treated unavailable; don't derive audio tokens; invalid/oversized/key-containing IDs dropped; prior transcription usage survives generation failure | Real provider metadata shape and backend mapping |
| TC-12 `test_limits.py::test_limits_and_cleanup`, `test_openai_transport.py::test_response_cap` | L5 N-1/N/N+1 byte boundaries; unknown config fields/negative/zero limits rejected; 8 operations admitted, ninth immediately denied before reader; deadline at every phase; response stream N+1 aborted before parser; no retries; close/release on every exit including cancellation/cleanup error | Platform concurrency/memory budget, HTTP pre-parser limit, no disk spooling and actual safe rollback |
| TC-13 `test_handler.py::test_unconfigured_and_reader_outage` | Missing live verifier/reader returns denial; simulated source outage returns safe unavailability; environment key never read and fakes never auto-selected | Least-privilege real read/decrypt denial, actual store outage and real-state checks |
| TC-14 `test_import_safety.py::test_no_public_wiring`, `test_handler.py::test_no_bypass` | Import needs no key/network; module doesn't register routes; no input field selects fakes; every exported handler uses verifier before reader; verify existing routes remain unchanged and disconnected, not declared secure | Real route exposure, no legacy bypass, reviewed migration/enablement/rollback |

### Commands and evidence for implementation

Use an already approved Python 3.11/3.12 environment. Approved exception (lead, 2026-10-23): T2.1 standard-library tests may run on the installed Python 3.13.14 with no installations. Record that version with the results, and re-run on 3.11/3.12 before M1 sign-off. **Update 2026-10-23:** an approved Python 3.12.10 `.venv` now exists. T2.1-T2.3 re-ran there with 120/120 passing (see the delivery plan's environment section). From now on, use `.venv\Scripts\python` for all runs, including T3 and the final T4.2 suite. Proposed command after test files exist:

```text
python -m unittest discover -s tests/provider_integration -p "test_*.py" -v
```

Run from repository root. Include `tests/__init__.py` and `tests/provider_integration/__init__.py` if package imports require them; no test-runner dependency is needed. T3 transport tests use the installed SDK/transport; a missing/incompatible installation is a reported prerequisite, not a silent skipped test. Standard-library mock patches replace network constructors/transports with deny-by-default stubs; only explicit in-memory mock dispatch is permitted.

For each task record Python and installed OpenAI/HTTP-transport versions, exact command, discovered test count, pass/fail/skip count and TC coverage. Zero discovered tests is a failure. At final M1 acceptance, no required local test may be skipped. A small card runs its relevant tests plus completed-card regression; T4.2 runs the whole suite. This command has NOT been run during documentation work because the feature test suite does not exist yet.

### M1 sign-off checklist

Status evaluated 2026-10-23. An item is ticked only where it is actually true.

- [x] T1 accepted L1-L8 and assigned owners/reviewer; T2.1 through T4.2 evidence accepted. *(T1, T2.1-T4.2 and review fix F1 accepted by Mani, who is owner and reviewer; there was no independent reviewer. TC-table acceptance and backend contact are still open from T1.)*
- [x] All fourteen local cases above (TC-04 through both its core and adapter rows) covered by actual tests, with counts and commands; no missing required checks. *(194 tests in `.venv` after F1, 0 skipped; see the T2.1-T4.2 and F1 evidence.)*
- [x] No credential cross-use, fallback, persistent content or secret leakage in tested paths; no unresolved critical/high findings. *(Tested paths are clean. R1-R4 were fixed by F1. The remaining R5 is a low-severity contract hardening and R6-R9 are cleanup; no human security review has been done.)*
- [x] Adapter exercised via mocked transport, not merely replaced entirely by a fake; installed versions recorded. *(Real SDK over `httpx.MockTransport`; versions in the environment section.)*
- [x] New module imports without secrets/network; existing unauthenticated routes not connected to it. *(`test_import_safety.py`.)*
- [x] Exact backend handoff B1-B7, legacy risks, provider/live limitations and next approvals documented. *(Delivery plan: M1 handoff package.)*
- [ ] Human reviewer/date/commit or working-tree checkpoint recorded. No inference of live/production readiness. *(Pending M1 sign-off.)*

## Documentation-only revision checks

Check local Markdown links, required requirement/task/test references, superseded notices, no active Claude instructions, no active old platform prerequisites, prompt/plan agreement, and preservation of application code/dependencies. These checks validate this documentation revision only, not feature behavior.

## Traceability and evidence

Revision 2, 2026-09-18. Old AUTH/CRED/VAL/ROT/DEL/POL/SRC/INV IDs are historical; use current PI-01 through PI-12.
Status: **T2.1, T2.2 and T2.3 local evidence recorded 2026-10-23; adapter, handler and live cases not run.** Partial means only the core type/config/import portion is covered; the full case still needs later cards.

| Requirement | Plan task | Planned tests | Implementation evidence | Result |
| --- | --- | --- | --- | --- |
| PI-01 modular providers | T2, T3 | TC-01 | T2.1: provider config/ports (`test_capability_matrix`). T2.3: unsupported target/adapter capability denied before the reader. T3.1: `test_selected_models` | Partial: T2.1 + T2.3 + T3.1 pass 2026-10-23 (3.12 .venv) |
| PI-02 correct scoped credential | T2, T4, T5 | TC-02, TC-03, TC-06, TC-13 | T2.1: exact Binding/Target/context types. T2.2: `test_admission.py` denial, verifier, state and isolation tests against the fakes. T4.1: handler verifies before admission, defensive context re-check, untrusted-field rejection (`test_untrusted_context`, `test_misbehaving_verifiers_are_denied`, `test_parse_failures`). B1-B4 pending | Partial: T2.1-T4.1 pass 2026-10-23 (3.12 .venv); live verifier/reader M2 |
| PI-03 validation | T2, T3, T5 | TC-04, TC-05 | T2.2: reader/backend version tests. T2.3: core validation path (`test_validation.py`). T3.2: adapter probes and outcome matrix (`test_openai_validation.py`); B5 pending | Partial: T2.2 + T2.3 (3.13) + T3.2 (3.12 .venv) pass 2026-10-23 |
| PI-04 selected model interaction | T3, T4 | TC-01, TC-10 | T2.3: exact configured targets and L4 composition. T3.1: L6 request shapes. T4.1: handler projection matrix and legacy `result/model/file_type` (`test_input_projection_matrix`, `test_end_to_end_with_real_adapter`); models deprecated upstream (A1) | Partial: T2.3-T4.1 pass 2026-10-23 (3.12 .venv) |
| PI-05 credential changes | T2, T5, T6 | TC-05, TC-06, TC-13 | T2.2: rotation, disable and ordering tests against the atomic fake (`test_rotation_denies_old_version`, `test_admission_change_order`); real B4 pending | Partial: simulated only, T2.2 pass 2026-10-23 (3.13) |
| PI-06 no fallback | T3, T4, T6 | TC-07, TC-14 | T2.3: `test_no_fallback_matrix`. T3.1: no env key/base URL, zero SDK retries. T4.1: deny-all unconfigured wiring; no request field selects fakes (`test_unconfigured_and_reader_outage`, `test_no_bypass`). Legacy route echo unchanged and disconnected | Partial: T2.3-T4.1 pass 2026-10-23 (3.12 .venv); legacy bypass/rollback M2 |
| PI-07 results/errors/usage | T2, T3, T4 | TC-04, TC-08, TC-11 | T2.1: result/validation invariants, fixed messages, usage/ID sanitizing. T2.3: per-step usage, safe failure codes. T3.1: L6 error matrix with A2 and provider usage mapping (`test_error_mapping_matrix`, `test_transcription_usage_shapes`); B6 wire format pending | Partial: T2.1 + T2.3 + T3.1 pass 2026-10-23 (3.12 .venv) |
| PI-08 secret protection | T2-T6 | TC-02, TC-08, TC-12 | T2.1: `SecretValue`/`CredentialLease` redaction and serialization refusal, hidden exception chains. T3.1: no key/body in adapter errors; debug logging fails closed. T4.2: `test_leakage.py` canaries across all exits (logs, warnings, asyncio handler, file writes, serialization), with positive control; B1/B3 pending | Local pass 2026-10-23 (3.12 .venv); live telemetry/hosting M2 |
| PI-09 isolation/non-retention | T2, T4, T6 | TC-03, TC-08, TC-12 | T2.2/T2.3 reader- and orchestrator-level isolation. T3.1/T3.2 per-lease clients and per-session guard. T4.2: full-stack `test_isolation.py` (barrier overlap, interleaved invoke/validate, rotation mid-flight) and no file writes in `test_leakage.py`; legacy cache/spooling risks remain | Local pass 2026-10-23 (3.12 .venv); live concurrency M2 |
| PI-10 approved destinations | T3, T5, T6 | TC-09 | T2.1: https-only destination config. T3.1: configured destination only; env base URL/proxy ignored. T3.2: destination guard, all redirect codes, production transport settings, header hygiene (`test_openai_transport.py`) | Partial: T2.1 + T3.1 + T3.2 pass 2026-10-23 (3.12 .venv); live egress M2 |
| PI-11 bounded execution | T2-T6 | TC-04, TC-12 | T2.1: accepted L5 profile and config validation. T2.3: byte limits, capacity, deadlines, single attempts, bounded cleanup (`test_limits.py`). T3.2: response-body cap before parsing (`test_response_cap` and related); live B5/B7 pending | Partial: T2.1 + T2.3 + T3.2 pass 2026-10-23 |
| PI-12 integration/compatibility | T1, T4-T7 | TC-02, TC-10, TC-13, TC-14 | T2.1 import safety; T2.2 reader outage; T4.1 handler/wiring and legacy projection. T4.2: `test_import_safety.py` (clean-env subprocess, SDK import-time reads pinned, no routes, legacy routes unchanged and disconnected). B1-B7 and API agreement pending | Local pass 2026-10-23 (3.12 .venv); live contract M2 |

### Evidence format

Append task ID, owner, date, approved scope, requirement IDs, code/test file paths and functions, exact commands, environment, results, security observations, remaining gaps, and reviewer decision. Never include key values or customer content.

A successful mock test can satisfy the local portion of a requirement, but it does not satisfy T5/T6 backend authorization, state consistency, or live secret isolation. Keep separate evidence entries.

### T2.1 evidence — 2026-10-23

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T2.1. Mani (core owner). Approved edit plan of 2026-10-23: types, ports, errors, config, package init, test package init and `test_contracts.py` |
| Environment | Python 3.13.14 on Windows 10, standard library only. This is the approved exception; re-run on 3.11/3.12 before M1 sign-off |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **71 discovered / 71 passed / 0 failed / 0 errors / 0 skipped** |
| Reviewer decision | Accepted by Mani on 2026-10-23; 3.11/3.12 re-run still required before M1 sign-off |

**Coverage (core portions only)**

| Case | Tests |
| --- | --- |
| TC-01 | `test_capability_matrix`, `test_empty_configuration_enables_nothing` |
| TC-02 | `BindingTests`, `TargetAndContextTests`: exact field equality, no case-folding, expiry boundary, frozenset-only targets |
| TC-08 | `SecretValueTests`, `CredentialLeaseTests`, `test_content_absent_from_repr`, `test_result_content_absent_from_repr`, `test_chained_exceptions_are_hidden` |
| TC-11 | `test_usage_and_safe_ids`, `test_constructor_rejects_negative_bool_and_malformed` |
| TC-12 (config only) | `LimitProfileTests`, including N-1/N/N+1 deadline boundaries and zero/negative/unknown fields |
| TC-14 (import only) | `ImportSafetyTests`: subprocess import with no `OPENAI_API_KEY` and sockets disabled; no SDK, adapter or dotenv modules loaded; source scan |

**Security observations**
- Module-level patches deny socket connections throughout the suite.
- Only synthetic `test-provider-key-...` canaries are used.
- Ten deliberate defects applied to a scratch copy each made the suite fail (listed in the delivery plan).

**Gaps**
- No admission, orchestration, adapter, handler, logging-capture or filesystem tests exist yet.
- TC-03 through TC-07, TC-09, TC-10 and TC-13 are not run.
- This is not live, backend or production evidence.

### T2.2 evidence — 2026-10-23

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T2.2. Mani (core owner). Approved edit plan of 2026-10-23: `fakes.py` and `test_admission.py`; no production code |
| Environment | Python 3.13.14 on Windows 10, standard library only (approved exception) |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **86 discovered / 86 passed / 0 failed / 0 errors / 0 skipped** (15 new in `test_admission.py`). `test_admission.py` passed 10 of 10 repeated runs |
| Reviewer decision | Accepted by Mani on 2026-10-23; 3.11/3.12 re-run still required before M1 sign-off |

**Coverage (reader and verifier portions only)**

| Case | Tests |
| --- | --- |
| TC-02 | `test_denial_matrix`: each scope/ref/version/source/provider/target change, case-variant scope, empty targets, expired and non-verified context. `test_verifier_denial_matrix`: unknown/unhashable/revoked/expired evidence, every binding field, kind and targets. `test_unverified_request_never_reaches_reader`: zero reader calls |
| TC-03 | `test_two_scopes_concurrent_isolation`: barrier overlap, each scope sees only its own synthetic key, a fresh `SecretValue` per admission |
| TC-05 | `test_replacement_and_stale_result`: pending v2 validates as v2 while v1 stays active; a timeout leaves v1 active; deleting v2 mid-probe gives a v2-bound result that the simulated backend refuses. `test_production_module_has_no_lifecycle_actions` |
| TC-06 | `test_state_matrix` (states × invoke/validate); `test_admission_change_order` and both gate-ordered concurrency tests; `test_rotation_denies_old_version` (C3); `test_lease_released_on_every_exit`; `test_cancel_while_waiting_records_no_admission` |
| TC-13 | `test_outage_and_no_fallback`: outage and missing record fail closed with a canary `OPENAI_API_KEY` present; the fakes never read the environment |

**Security observations**
- A network guard denies every non-loopback connect and DNS lookup during the module.
- Fake keys must use the `test-provider-key-` prefix, and real-looking values are refused.
- Exception renderings contain no key.

**Gaps**
- Not yet covered: the orchestrator's re-check of a malicious reader snapshot, and the "zero provider calls" assertions (T2.3).
- Handler-level denial is T4.1.
- Real verifier/reader behavior is M2.

### T2.3 evidence — 2026-10-23

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T2.3. Mani (core owner). Approved edit plan of 2026-10-23: `orchestrator.py`, fakes additions, `test_orchestrator.py`, `test_limits.py`, `test_validation.py`; decisions D1-D5 |
| Environment | Python 3.13.14 on Windows 10, standard library only (approved exception) |
| Command | `python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **120 discovered / 120 passed / 0 failed / 0 errors / 0 skipped**. 10 repeated full runs OK; no warnings under `-X dev -W always` |
| Reviewer decision | Accepted by Mani on 2026-10-23; 3.11/3.12 re-run still required before M1 sign-off |

**Coverage (core portions only)**

| Case | Tests |
| --- | --- |
| TC-02 | `test_tampered_lease_never_reaches_provider` (other version/scope, pending state, narrower targets, non-lease: zero sessions); `test_denied_before_reader` (zero reader and provider calls) |
| TC-03 | `test_two_scopes_same_prompt_isolated` (barrier overlap, own key and answer, repeat request invokes again); `test_one_session_and_admission_per_request` |
| TC-04 core (C2) | `test_validation.py`: `test_single_probe_valid_result`, `test_probe_outcome_matrix`, `test_local_failures_are_indeterminate`, `test_reader_and_lease_failures_are_indeterminate`, `test_probe_and_overall_timeouts`, `test_capacity`, `test_no_customer_content_and_no_activation` |
| TC-05 core | `test_pending_version_validates_as_itself` |
| TC-07 | `test_no_fallback_matrix`: 14 failure classes × 2 stages; one attempt; no other adapter; zero generation after a failed transcription; no echo |
| TC-08 core | Key/content canaries absent from results for SDK-style exceptions, reader/open/close failures and key-containing output |
| TC-10 core | `test_input_composition_matrix`: audio-only, text+audio, empty transcript, `file_type` |
| TC-11 core | `test_usage_survives_generation_failure`, `test_usage_is_sanitized`, plus the usage expectations in the no-fallback matrix |
| TC-12 core | `test_limits.py`: text/audio/transcript/prompt/generation N-1/N/N+1 including multi-byte; shared non-queuing capacity of 8; admit, step and overall deadlines; bounded cleanup; single attempts |

**Security observations**
- A network guard is active in every new module.
- Only synthetic keys are used.
- The scripted adapter captures calls in test memory with content and key fields excluded from repr.

**Gaps**
- Adapter transport and response-size cap (T3.2).
- Handler/wiring (T4.1).
- Logging/filesystem/full isolation (T4.2).
- No live evidence.

### T3.1 evidence — 2026-10-23 (adapter track)

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T3.1. Mani (after takeover). Approved plan of 2026-10-23 with A1-A6: `adapters/openai.py` rewrite and `test_openai_adapter.py` |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1; real SDK over `httpx.MockTransport` with the network guard |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **137 discovered / 137 passed / 0 failed / 0 errors / 0 skipped** (17 in `test_openai_adapter.py`); 5 repeated full runs OK; 14/14 adapter mutations detected |
| Reviewer decision | Accepted by Mani on 2026-10-23 (no independent reviewer) |

**Coverage (adapter portions)**

| Case | Tests |
| --- | --- |
| TC-01 | `test_selected_models`, `test_constructor_requires_explicit_configuration` |
| TC-07 | `test_error_mapping_matrix` (every L6 row with A2, including timeouts, connection errors, redirects and malformed success), `test_single_attempt_without_sdk_retries` |
| TC-08 (adapter) | Key and body canaries absent from errors, usage and tracebacks; `test_debug_logging_fails_closed` |
| TC-09 (core) | `test_no_environment_inheritance` (env key/base URL/org/project/proxy/TLS canaries; owned client `trust_env=False`, `follow_redirects=False`, `verify=True`); the 302 case is a single request |
| TC-10 (adapter) | `test_generation_request_shape`, `test_transcription_request_shape` |
| TC-11 (adapter) | `test_transcription_usage_shapes`, `test_usage_absent_and_request_id_filtering` |
| Cleanup and isolation | `test_one_client_per_session_and_always_closed` |

**Gaps:** T3.2 probes and the response cap; integration T4; live evidence.

### T3.2 evidence — 2026-10-23 (adapter track)

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T3.2. Mani. Approved plan of 2026-10-23 with B1-B6: guarded transport, probes, `test_openai_transport.py`, `test_openai_validation.py` |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1 |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **157 discovered / 157 passed / 0 failed / 0 errors / 0 skipped** (13 transport + 7 adapter validation new); 5 repeated full runs OK; 15/15 T3.2 mutations detected |
| Reviewer decision | Accepted by Mani on 2026-10-23 (no independent reviewer) |

**Coverage (adapter portions)**

| Case | Tests |
| --- | --- |
| TC-04 adapter (C2) | `test_openai_validation.py::test_probe_and_outcome_matrix` (L6 table with A2 for both probes, one request each), `test_text_probe_request`, `test_audio_probe_request`, `test_probe_success_criteria`, `test_pending_lease_and_no_activation`, `test_oversized_probe_response_is_indeterminate` |
| TC-09 adapter | `test_openai_transport.py::test_destination_redirect_and_environment` (301/302/307/308, single request), `test_guard_blocks_unapproved_urls_before_sending`, `test_blocked_request_is_internal_error`, `test_production_transport_settings`, `test_header_hygiene`, `test_forced_organization_never_sent_end_to_end` |
| TC-12 adapter | `test_response_cap` (N-1/N/N+1, declared and streamed), `test_oversized_stream_stops_early`, `test_declared_oversize_is_not_read`, `test_error_bodies_are_capped`, `test_cap_counts_each_request_separately`, `test_compressed_response_refused` |

**Gaps:** combined orchestrator + real adapter (T4); live evidence (M2).

### T4.1 evidence — 2026-10-23 (integration)

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T4.1. Mani. Approved plan of 2026-10-23 with C1-C6: `handler.py`, `wiring.py`, `test_handler.py` (plus the scoped `test_contracts.py` scan change described in the delivery plan) |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1, pydantic 2.6.1 |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **172 discovered / 172 passed / 0 failed / 0 errors / 0 skipped** (14 handler + 1 contracts new); 5 repeated full runs OK; 14/14 T4.1 mutations detected |
| Reviewer decision | Accepted by Mani on 2026-10-23 (no independent reviewer) |

**Coverage (local portions)**

| Case | Tests |
| --- | --- |
| TC-02 | `test_untrusted_context` (unknown/unhashable/revoked/expired evidence, each binding field, wrong kind: verifier only, zero reader/provider calls), `test_misbehaving_verifiers_are_denied` (raising, hanging, wrong binding, non-context, wrong kind), `test_parse_failures` (unknown fields such as `authorized`, `base_url`, `api_key`, `mode`, `headers`; zero verifier calls) |
| TC-10 | `test_input_projection_matrix` (text, audio, combined, whitespace text, empty audio per C3, empty transcript; exactly `result/model/file_type`), `test_audio_requires_both_allowed_targets`, `test_failures_cannot_be_projected`, `test_raw_text_limit_checked_before_strip` |
| TC-13 | `test_unconfigured_and_reader_outage` (deny-all default with a canary `OPENAI_API_KEY`; outage fails closed for invoke and validate), `test_build_handler_composes_real_adapter_without_test_seam` |
| TC-14 (local) | `test_no_bypass` (verify always before admit; no env/fakes/FastAPI references; `api/` and `main.py` untouched), `test_wiring_import_does_not_load_sdk`, `test_contracts.py::test_wiring_imports_adapters_only_lazily` |
| Deadline / combined | `test_deadline_includes_verification`, `test_end_to_end_with_real_adapter` |

**Gaps:** T4.2 leakage/isolation/import-safety suite and M1 sign-off; live route exposure, legacy bypass and rollback are M2.

### T4.2 evidence — 2026-10-23 (M1 regression)

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | T4.2. Mani. Approved plan of 2026-10-23 with E1-E5: `test_isolation.py`, `test_leakage.py`, `test_import_safety.py`; AI code review; M1 handoff docs |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1, pydantic 2.6.1 |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Result | **185 discovered / 185 passed / 0 failed / 0 errors / 0 skipped**; 5 repeated full runs OK; 7/8 T4.2 mutations detected (the survivor is covered by the T2.1 error-class layer) |
| Reviewer decision | Accepted by Mani on 2026-10-23 (no independent reviewer); R1-R4 fixed by F1, R5-R9 follow-ups |

**Coverage**

| Case | Tests |
| --- | --- |
| TC-03 | `test_isolation.py::test_two_scopes_same_prompt`, `test_interleaved_invoke_and_validate`, `test_rotation_mid_flight` |
| TC-08 | `test_leakage.py::test_canary_all_exits` (9 scenarios), `test_validation_and_boundary_paths`, `test_cancellation_leaks_nothing`, `test_debug_logging_fails_closed_without_logging_content`, `test_secret_objects_refuse_serialization`, positive control `test_watch_detects_leaks` |
| TC-14 (local) | `test_import_safety.py::test_no_public_wiring`, `test_import_ignores_credential_environment`, `test_package_defines_no_routes_or_fakes`, `test_legacy_routes_unchanged_and_disconnected` |

**Local acceptance summary (M1).** All fourteen TC rows have local evidence:

| Cases | Where |
| --- | --- |
| TC-01, TC-02, TC-08, TC-11, TC-12 | T2.1 |
| TC-02, TC-03, TC-05, TC-06, TC-13 | T2.2 |
| TC-03, TC-04 (core), TC-05, TC-07, TC-08, TC-10, TC-11, TC-12 | T2.3 |
| TC-01, TC-07, TC-09, TC-10, TC-11 | T3.1 |
| TC-04 (adapter), TC-09, TC-12 | T3.2 |
| TC-02, TC-10, TC-13, TC-14 | T4.1 |
| TC-03, TC-08, TC-14 | T4.2 |

Every M2 column in the case table remains not run.

### Review fix F1 evidence — 2026-10-23 (R1-R4)

**Summary**

| Item | Detail |
| --- | --- |
| Task / owner / scope | F1. Mani. Approved fix plan of 2026-10-23 for AI review findings R1-R4 |
| Environment | `.venv` Python 3.12.10, openai 1.109.1, httpx 0.28.1 |
| Command | `.venv\Scripts\python -m unittest discover -s tests/provider_integration -p "test_*.py" -v` |
| Red (before fixes) | The 10 new or updated tests: 15 failures + 8 errors, each for the expected reason |
| Green (after fixes) | **194 discovered / 194 passed / 0 failed / 0 errors / 0 skipped**; 5 repeated runs OK; 6/6 reverse mutants and 8/8 regression mutants detected |
| Reviewer decision | Accepted by Mani on 2026-10-23 (no independent reviewer) |

**Tests**

| Finding | Tests |
| --- | --- |
| R1 | `test_orchestrator.py::CleanupCancellationTests` (cancel during cleanup for invoke and validate, repeated cancellation, capacity not exhausted) |
| R2 | `test_openai_transport.py::GuardClassificationTests` (concurrent requests classified independently, no outcome state) and the updated `test_guard_blocks_unapproved_urls_before_sending` |
| R3 | `test_contracts.py::ErrorSerializationTests` |
| R4 | `test_orchestrator.py::ClockValidationTests` |

R5-R9 are recorded follow-ups (marked skipped in the review findings).

### Documentation revision evidence

Scope revision and CODEX handoff were authorized by the requesting user on 2026-09-18. Review disposition: [Indra review resolution](review-record.md). Current documents are ready for team review; acceptance of their detailed wording/contract is pending.

Documentation validation results are recorded in [revision verification](review-record.md). They are not application or security-test results.
