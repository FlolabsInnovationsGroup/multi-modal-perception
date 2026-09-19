> **SUPERSEDED IN FULL — HISTORICAL DESIGN (2026-09-18).** All decisions, status labels, requirements, and phase gates below are inactive for the revised feature. Do not use them as implementation instructions or evidence of deployed controls. [ADR-006](../../provider-integration/review-record.md) records the scope change; the current PRD and backend contract govern new work. Preserved below for comparison only.

# ADR-001: Cognito Authentication and PostgreSQL-Authoritative Tenancy

## Status

Accepted by PRD; implementation subject to Phase 0 and Phase 1 gates.

## Context

The current service has no authentication or tenancy. BYOK credentials, provider policy, usage, and audit data must be isolated by organization/workspace. Cognito can authenticate identities, but mutable claims or identity-provider configuration alone are not a sufficient source for application workspace authorization.

## Decision

- Use Amazon Cognito for invite-only user authentication with mandatory MFA.
- Validate JWT signature, issuer, audience/client, token use, expiry, and required claims at the API boundary.
- Store authoritative organizations, workspaces, invitations, memberships, and roles in PostgreSQL.
- Resolve every workspace authorization from the validated principal and active database membership.
- Enforce tenant isolation with centralized application authorization, relational constraints, and PostgreSQL row-level security.
- Do not trust client-supplied role/workspace claims or mutable Cognito attributes as the sole authorization source.

## Consequences

Positive:

- Identity lifecycle remains managed by Cognito while application tenancy is explicit and testable.
- Role and workspace policy changes do not require encoding the entire authorization model in tokens.
- RLS provides defense in depth against query mistakes.

Costs/risks:

- Authentication and authorization are separate systems that require synchronization and clear failure behavior.
- Invitation, MFA recovery, token/session invalidation, and last-owner rules require careful product design.
- RLS context must be safe under connection pooling, and the application role cannot own/bypass protected tables.

## Rejected alternatives

- A global shared API key with no user identity: cannot provide tenant isolation or accountability.
- Cognito groups/claims as the only workspace authorization store: difficult to model dynamic multi-workspace membership safely and can create stale/mutable authorization.
- Application checks without relational constraints/RLS: a single missed predicate could expose another tenant.

## Verification

- Token-negative tests and mandatory-MFA tests.
- Full role/endpoint matrix.
- Cross-workspace IDOR tests.
- RLS tests using the real application database role and connection-pool behavior.
- Membership change/session behavior tests after the policy is approved.
