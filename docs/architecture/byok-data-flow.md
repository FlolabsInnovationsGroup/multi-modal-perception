# Provider Integration Data Flow

Status: proposed technical flow for team review, 2026-09-18.
Replaces the earlier all-platform broker flow. No AWS topology is selected.

## Current code

Caller -> unauthenticated FastAPI route -> global OpenAI client/environment key -> provider.
Generation also uses a prompt-only response cache and echoes input on failure. Both routes return result/model/file_type. This is a baseline to change, not a safe BYOK design.

## Target logical flow

```text
User -> FloBrain backend (user authentication, authorization, credential selection)
                    |
                    | authenticated service request + bound scope/reference + content
                    v
          Multimodal request boundary
                    |
                    +-> CredentialReader -> backend-managed protected storage/interface
                    |      exact permitted version/state; request-local secret
                    v
           Selected provider adapter -> approved provider endpoint
                    |
                    v
          result + safe metadata -> FloBrain backend -> User
```

The reader protocol and service authentication are unresolved B1-B3, not implied by the arrows. An internal function boundary does not require another deployed service. Backend-managed storage may contain an encrypted credential or a secure reference; no plaintext database design is authorized.

## Invocation order

1. Verify the backend caller/context; validate input limits and selected supported provider/model/operation.
2. Resolve the exact scoped credential/version through the approved reader. Verify returned ownership/provider/state against trusted context.
3. Apply the agreed admission/state consistency rule immediately before provider use; B4 must cover races, not only sequential checks.
4. Create request-local provider execution. Transcribe audio if requested, then generate the response with that authorized configuration.
5. Return actual result plus safe metadata/usage. On failure return a normalized error, not an echo or another key/provider.
6. Close clients/streams and release secret/content references on every exit path. Never cache across requests.

## Validation path

Backend selects a candidate version -> authenticated validation request -> scoped reader permits that pending version only for validation -> adapter checks specified capability with approved synthetic data -> version-bound validation result -> backend decides whether to activate.

Validation does not save keys, grant ownership, register users, activate replacements, or start a scheduler. No separate customer write-only credential route is created in this repository.

## Boundaries to verify

| Boundary | Owner/control | Evidence |
| --- | --- | --- |
| User -> backend | Backend user auth and authorization; not implemented here | Backend contract approval |
| Backend -> multimodal | Authenticated caller, fresh bound context, no bypass through old routes | TC-02, TC-14 |
| Multimodal -> credential source | Least-privilege exact lookup, protected retrieval, state/version consistency | TC-02, TC-05, TC-06, TC-13 |
| Adapter -> provider | Approved destination/configuration, bounded execution, request-scoped secret | TC-07, TC-09, TC-12 |
| Runtime -> diagnostics | Allowlisted metadata only; no raw bodies/headers/exceptions | TC-08, TC-11 |

Multimodal stores no credential values or interaction content. FloBrain owns lifecycle metadata and its retention policy; the platform owner owns logging retention and deployment. Provider-side data handling requires separate verification.
