# ADR-003: Provider Adapters, Model Catalog, and No Implicit Fallback

## Status

Accepted by PRD; OpenAI adapter first. Later providers require separate approval and review.

## Context

Providers differ in authentication, endpoints, deployment/model identifiers, capabilities, request parameters, errors, usage, retention, and regional controls. Accepting arbitrary identifiers or silently switching credentials/providers can change cost, data processing, compliance, and behavior without customer consent.

## Decision

- Define a normalized provider-adapter contract for validation, generation, transcription, capability discovery, error classification, usage extraction, and provider request IDs.
- Implement OpenAI completely before adding Anthropic, Gemini, Azure OpenAI, or other providers.
- Maintain a platform provider/model catalog and workspace allowlist.
- Reject unknown or disallowed models/capabilities before secret retrieval.
- Make customer-managed versus platform-managed credential source an explicit workspace policy.
- Never automatically fall back to another credential, platform key, model, region, or provider.
- Return safe metadata identifying the actual provider/model/source category used, without revealing a key.

## Consequences

Positive:

- Provider differences stay localized and contract-tested.
- Customers have predictable data paths and cost attribution.
- Catalog/policy checks reduce unsupported and arbitrary invocation risk.

Costs/risks:

- Catalog maintenance and provider API changes require operational ownership.
- An outage or invalid BYOK key is surfaced rather than hidden by a fallback, reducing availability for that request but preserving consent.
- A unified contract must not erase important provider semantics.

## Rejected alternatives

- Provider-specific logic scattered through routes/services: difficult to secure and extend consistently.
- Arbitrary model IDs/endpoints: creates policy bypass and SSRF/support risks.
- Automatic platform-key fallback: transfers cost and data without explicit consent.
- Two-provider initial PoC: increases security and test scope before the core boundary is proven.

## Verification

- Adapter contract tests and provider error mapping.
- Unknown/disallowed model and capability tests.
- Invalid, disabled, deleted, revoked, quota, rate-limit, timeout, and outage tests prove no fallback.
- Audit/response metadata matches the actual provider/model/source.
