# Provider Integration Test and Acceptance Plan

Status: **Ready for review**, 2026-09-18. No feature test below has been run or passed yet.
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

For each case record test file/function, environment, exact command, result, requirement IDs, date, and reviewer in the [traceability matrix](../requirements/byok-traceability-matrix.md).

Mock pass != live backend pass. For T5/T6, specifically prove service caller verification and credential ownership/version checks against the actual integration. Backend lifecycle implementation is tested jointly, not rebuilt here.

Release requires applicable cases passing, B1-B7 resolved, exact limits/configuration recorded, provider enablement checked, no unresolved critical/high leakage or scope-isolation defect, and explicit release/deployment authorization. There is no inherited numeric AWS SLO or 100-request load target; agree the relevant load and pass limits before measuring.

## Documentation-only revision checks

Check local Markdown links, required requirement/task/test references, superseded notices, no active Claude instructions, no active old platform prerequisites, prompt/plan agreement, and preservation of application code/dependencies. These checks validate this documentation revision only, not feature behavior.
