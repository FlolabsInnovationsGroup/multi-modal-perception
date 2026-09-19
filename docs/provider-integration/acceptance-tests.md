# Provider Integration Test and Acceptance Plan

Revision 2.1, 2026-09-19. Status: **Ready for review against design L1-L8**. No feature test below has been run or passed yet. Named tests below are implementation deliverables, not files claimed to exist.
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

1. T2: pure unit/contract tests with fake credential reader, fake adapters, and synthetic content. No network, database, actual key, GPU, or model downloads.
2. T3: first-provider tests with mocked SDK transport and explicit call-count assertions; verify both SDK error mapping and retries.
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
| TC-04 `test_validation.py::test_probe_and_outcome_matrix` | L6 status mapping table parameterized; text exactly one probe <=8 output-token budget; audio exactly one in-memory one-second silent WAV; no customer input, no activation; successful empty audio transcript is valid; local saturation/timeout indeterminate after trusted validation | Approved live probe/cost policy and account responses |
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

Use an already approved Python 3.11/3.12 environment. Proposed command after test files exist:

```text
python -m unittest discover -s tests/provider_integration -p "test_*.py" -v
```

Run from repository root. Include `tests/__init__.py` and `tests/provider_integration/__init__.py` if package imports require them; no test-runner dependency is needed. T3 transport tests use the installed SDK/transport; a missing/incompatible installation is a reported prerequisite, not a silent skipped test. Standard-library mock patches replace network constructors/transports with deny-by-default stubs; only explicit in-memory mock dispatch is permitted.

For each task record Python and installed OpenAI/HTTP-transport versions, exact command, discovered test count, pass/fail/skip count and TC coverage. Zero discovered tests is a failure. At final M1 acceptance, no required local test may be skipped. A small card runs its relevant tests plus completed-card regression; T4.2 runs the whole suite. This command has NOT been run during documentation work because the feature test suite does not exist yet.

### M1 sign-off checklist

- [ ] T1 accepted L1-L8 and assigned owners/reviewer; T2.1 through T4.2 evidence accepted.
- [ ] All fourteen local rows above covered by actual tests, with counts and commands; no missing required checks.
- [ ] No credential cross-use, fallback, persistent content or secret leakage in tested paths; no unresolved critical/high findings.
- [ ] Adapter exercised via mocked transport, not merely replaced entirely by a fake; installed versions recorded.
- [ ] New module imports without secrets/network; existing unauthenticated routes not connected to it.
- [ ] Exact backend handoff B1-B7, legacy risks, provider/live limitations and next approvals documented.
- [ ] Human reviewer/date/commit or working-tree checkpoint recorded. No inference of live/production readiness.

## Documentation-only revision checks

Check local Markdown links, required requirement/task/test references, superseded notices, no active Claude instructions, no active old platform prerequisites, prompt/plan agreement, and preservation of application code/dependencies. These checks validate this documentation revision only, not feature behavior.

## Traceability and evidence

Revision 2, 2026-09-18. Old AUTH/CRED/VAL/ROT/DEL/POL/SRC/INV IDs are historical; use current PI-01 through PI-12.
Status: **Verification designed; feature implementation not started.** Test IDs are planned cases, not existing test functions or passing results.

| Requirement | Plan task | Planned tests | Implementation evidence | Result |
| --- | --- | --- | --- | --- |
| PI-01 modular providers | T2, T3 | TC-01 | Not implemented | Not run |
| PI-02 correct scoped credential | T2, T4, T5 | TC-02, TC-03, TC-06, TC-13 | Backend contract B1-B4 pending | Not run |
| PI-03 validation | T2, T3, T5 | TC-04, TC-05 | Module contract proposed; B5 pending | Not run |
| PI-04 selected model interaction | T3, T4 | TC-01, TC-10 | Existing text/audio baseline only; not BYOK | Not run |
| PI-05 credential changes | T2, T5, T6 | TC-05, TC-06, TC-13 | B4 coordination pending | Not run |
| PI-06 no fallback | T3, T4, T6 | TC-07, TC-14 | Legacy echo remains until approved code task | Not run |
| PI-07 results/errors/usage | T2, T3, T4 | TC-04, TC-08, TC-11 | B6 wire format pending | Not run |
| PI-08 secret protection | T2-T6 | TC-02, TC-08, TC-12 | B1/B3 pending; no new secret handling implemented | Not run |
| PI-09 isolation/non-retention | T2, T4, T6 | TC-03, TC-08, TC-12 | Legacy cache/spooling risks require code work | Not run |
| PI-10 approved destinations | T3, T5, T6 | TC-09 | Adapter/destination configuration not implemented | Not run |
| PI-11 bounded execution | T2-T6 | TC-04, TC-12 | Local L5/L6 proposed; live B5/B7 pending | Not run |
| PI-12 integration/compatibility | T1, T4-T7 | TC-02, TC-10, TC-13, TC-14 | B1-B7 and API agreement pending | Not run |

### Evidence format

Append task ID, owner, date, approved scope, requirement IDs, code/test file paths and functions, exact commands, environment, results, security observations, remaining gaps, and reviewer decision. Never include key values or customer content.

A successful mock test can satisfy the local portion of a requirement, but it does not satisfy T5/T6 backend authorization, state consistency, or live secret isolation. Keep separate evidence entries.

### Documentation revision evidence

Scope revision and CODEX handoff were authorized by the requesting user on 2026-09-18. Review disposition: [Indra review resolution](review-record.md). Current documents are ready for team review; acceptance of their detailed wording/contract is pending.

Documentation validation results are recorded in [revision verification](review-record.md). They are not application or security-test results.
