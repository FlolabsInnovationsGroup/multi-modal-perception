> **REFERENCE ONLY — PRE-REVIEW RESEARCH.** This entire document, including any old PRD/architecture comparison below, is historical background. It does not govern revision 2. Do not use its storage, provider, streaming, pricing, or deployment suggestions as implementation requirements. Start at the [current documentation index](../../provider-integration/README.md).

# BYOK Provider Integration Research — Governed Summary

## Document control

| Field | Value |
| --- | --- |
| Status | Reference — non-authoritative |
| Source | User-supplied research text |
| Reviewed against PRD | 2026-08-08 |
| Implementation authority | None |

> This document is background research, not an implementation instruction. If it conflicts with the approved PRD, delivery plan, accepted ADRs, or a current human decision, those sources take precedence. Provider capabilities, model names, pricing, limits, terms, and endpoint behavior are time-sensitive and must be reverified against official documentation before use.

## Research objective

The supplied research explored how a platform could securely accept user or workspace AI-provider credentials, route model requests through provider adapters, normalize responses and errors, record usage, and support a broader multi-provider roadmap.

It usefully identified these questions:

- Which providers and invocation capabilities belong in an MVP?
- How are credentials created, validated, rotated, disabled, and deleted?
- How are user, workspace, provider, model, and credential permissions bound?
- How should adapters normalize parameters, streaming, usage, cancellation, and errors?
- How are audit, observability, retries, billing attribution, and secret leakage handled?
- What additional risk is introduced by user-configured endpoints?

## Findings retained by the approved PRD

- Credentials require password/payment-grade handling.
- Full credentials are write-only and never returned by management APIs.
- Authorization must bind credential use to the authenticated workspace.
- One active credential per workspace/provider reduces initial routing and rotation complexity.
- Provider adapters should contain provider-specific authentication, request, response, usage, and error behavior.
- A platform model catalog and capability model are safer than unchecked provider identifiers.
- Credential validation should distinguish local format checks from disclosed online capability validation.
- Provider errors need normalized categories without raw secret-bearing exceptions.
- Usage data is operational attribution and may not equal the provider's final invoice.
- Silent platform-key or cross-provider fallback creates cost, data-path, and compliance risk.
- Arbitrary endpoints introduce SSRF, redirect, DNS-rebinding, private-network, and metadata-service risk.
- Logs, traces, queues, caches, and exception objects must not contain credentials.
- Plaintext lifetime should be minimized; garbage-collected runtimes cannot guarantee immediate memory erasure.

## Authoritative resolutions of research conflicts

| Research option or statement | Approved resolution | Authority |
| --- | --- | --- |
| Implement two providers in the PoC | Implement OpenAI completely first; later adapters are separate phases | PRD sections 4, 11, 15, and 21 |
| Store encrypted credential material in the database using application-managed envelope encryption | Store provider values in AWS Secrets Manager under a customer-managed KMS key; PostgreSQL stores only opaque references and safe metadata | PRD sections 6, 8, and 9; ADR-002 |
| Credential scope may be a user or workspace | Credential ownership is organization/workspace-based for the approved release | PRD sections 5, 6, and 9 |
| Streaming is mandatory in the MVP | Preserve current generation and transcription behavior first; streaming is not an initial BYOK release requirement unless separately approved | PRD goals, APIs, adapter contract, and deferred roadmap |
| Tool calling is part of the adapter MVP | Defer tool execution and its permission model | PRD non-goals and deferred roadmap |
| Custom deployment mode is now the only required mode | Initial release supports registered official provider endpoints and catalogued models; arbitrary custom endpoints are deferred | PRD sections 4, 6, and 21; ADR-005 |
| Model IDs and endpoints may be user-provided | Use platform model catalog plus workspace allowlist; do not accept arbitrary endpoint/model pairs | PRD sections 6.6 and 11 |
| Provider model/pricing table can guide implementation | Excluded from implementation authority because it is unverified and time-sensitive | Document governance policy |
| Provider-side retry may be broadly implemented | Retry only classified transient failures, honor provider guidance, and avoid replay after output or side effects begin | PRD adapter and reliability requirements |

## Useful future design topics

These topics remain possible later work but are not approved for the initial OpenAI BYOK implementation:

- Anthropic, Gemini, Azure OpenAI, and additional provider adapters.
- Streaming event normalization.
- Tool-calling schemas and authorization.
- Structured outputs across providers.
- Multiple active credentials, scheduling, or load balancing.
- Cost-aware routing and automatic model selection.
- Customer-specified endpoints or compatible APIs.
- Embeddings, reranking, image generation, video, or real-time voice.
- Cross-region secret or workload scheduling.

Each requires a PRD amendment or roadmap approval, threat-model update, adapter contract review, tests, and an ADR when the architecture changes.

## Reverification checklist for provider work

Before implementing or enabling a provider:

1. Use the provider's current official API, authentication, data-usage, retention, regional-processing, security, rate-limit, and error documentation.
2. Confirm approved endpoints, TLS behavior, redirects, DNS resolution, and network ranges.
3. Confirm credential scope, project/account ownership, rotation and revocation controls, and least-privilege options.
4. Confirm enabled models and capabilities in the customer account; do not infer access from marketing pages.
5. Confirm validation calls, their minimum cost, and their content/data-retention implications.
6. Confirm provider request IDs, usage fields, retry guidance, and idempotency behavior.
7. Review provider terms and data-processing obligations with the named legal/security owners.
8. Record the verification date and official sources in the provider-terms review and adapter tests.

## Excluded supplied claims

The supplied source contained a model/pricing comparison dated for a future or ambiguous market state and included model names, prices, currencies, and provider attributions that were not supported by a verified source package. Those values are intentionally not reproduced here. They must not be used for model selection, billing, customer promises, implementation constants, or acceptance criteria.

## Research conclusion

The research supports a centralized server-side credential boundary and provider adapter pattern. The approved implementation narrows that idea to a secure, auditable, OpenAI-first release using AWS Secrets Manager, KMS, explicit workspace policy, approved endpoints, and no silent fallback.
