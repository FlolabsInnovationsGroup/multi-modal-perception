# Provider Integration Security Checklist

Status: ready for scoped review, 2026-09-18. Replaces the broad platform threat model.
Assets: provider keys, trusted authorization context, scoped credential references, transient content, and safe operational metadata.

| Risk | Required scoped control | Test / owner |
| --- | --- | --- |
| Forged backend caller or caller-supplied "authorized" field | Real service authentication and fresh bound context before reader/provider use | TC-02; joint B3 |
| Cross-customer reference substitution | Bind scope/provider/version/operation to context and verify reader result; deny enumeration | TC-02/03; joint B2 |
| Key exposure through diagnostics | Secret-safe types; no raw exceptions, bodies, auth headers, repr, request dumps, or trace payloads | TC-08; multimodal |
| Backend storage compromise or excessive reader permissions | Backend-approved encryption/decryption and least privilege; no guessed plaintext store | TC-13; backend B1 |
| Reuse of disabled or replaced key | No cross-request secret cache; agreed atomic admission/version semantics | TC-05/06; joint B4 |
| Stale validation activates wrong version | Result bound to exact candidate; backend rejects stale result and owns activation | TC-05; backend + multimodal |
| Hidden cost or data routing | Never switch key/source/provider/model/destination/region, including on error | TC-07; multimodal |
| SSRF or key sent to attacker | Configured destinations only, reviewed TLS/redirect behavior, no endpoint/header override | TC-09; multimodal + platform |
| Cross-request cached content/client | Remove global response cache from new flow; request-local secret-bearing clients | TC-03/08; multimodal |
| Temporary audio/content retention | Check framework spooling, failure cleanup, diagnostics, and upload limits | TC-08/12; multimodal + platform |
| Quota exhaustion / retries / resource exhaustion | Bounded validation/invocation, concurrency/input limits, no unreviewed SDK retries | TC-04/12; joint B5/B7 |
| Unauthenticated legacy route bypass | New credential path requires verified service context on every reachable entry point | TC-14; joint B3/B6 |
| Backend outage selects legacy environment key | Fail closed, never fall back to fake/global credentials | TC-13; multimodal |
| Provider failure leaked as raw details or echo success | Safe categories and explicit failure; no raw SDK details | TC-07/08; multimodal |

## Residual risks and boundaries

- A compromised credential-reading service can expose keys in its memory. Request-local handling reduces exposure; it does not guarantee physical zeroization.
- Backend authentication/storage decisions remain unknown. Do not claim database-only compromise cannot recover keys until B1's actual design proves that.
- Already-admitted provider operations may finish and incur cost after disablement/cancellation. B4 defines and tests the admission boundary.
- Provider retention and permissions depend on the chosen offering/account; this service's non-retention promise does not control the provider.
- "Internal service" does not mean automatically trusted. Production must not expose a key-reading path without B3 enforcement.

T1 reviews the local fake/module design. T5/T6 review the actual trust boundary and unresolved risks. Do not turn this checklist into an obligation for multimodal to implement the backend's identity, recovery, database, or infrastructure platform.
