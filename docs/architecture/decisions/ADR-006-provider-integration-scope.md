# ADR-006: Provider Integration Scope and Backend Ownership

Date: 2026-09-18.
Status: **Scope revision approved by the requesting user; detailed contracts proposed.**

## Evidence

Indra Araujo's Notion review (August 15 / September 6, 2026) assigns user authentication and backend storage responsibilities to FloBrain, limits multimodal to reading/validating API keys and model interaction, and asks for provider-independent feature requirements.

On 2026-09-18 the requesting user approved the proposed documentation-only revision and explicitly requested CODEX instead of CLAUDE. This records that approval, not a new approval from Indra or the backend team.

## Decision

- This repository delivers a modular provider-integration feature, not a full identity/tenancy/credential-management/cloud platform.
- FloBrain owns user authorization and protected credential lifecycle persistence; multimodal consumes an agreed scoped credential-access contract.
- Multimodal owns validation and provider interaction, safe errors/usage, request isolation, no secret leakage, and no silent fallback.
- Requirements stay in the short PRD. Contracts, tests, operations, and provider sequence live in separate documents.
- Retain AGENTS and use CODEX as the explicit coding handoff guide.
- Supersede ADR-001 through ADR-005 and the prior all-platform plan/design as authorities for this feature. Their useful security outcomes are restated in the current PRD rather than inherited implicitly.

## Not decided

Actual storage, direct database versus mediated access, decryption, service authentication, exact wire schemas, lifecycle admission consistency, limits, and route migration. B1-B7 require joint approval. No plaintext database design is approved.

## Consequences

The team can review a small local module and then build/test with synthetic fakes without first building Cognito/RDS/ECS. Live integration remains blocked until its trust boundary is defined and verified.

Supersession does not remove a deployed security control: the prior target architecture was not implemented in this repository. It must not be used as permission to weaken real backend/platform controls.
