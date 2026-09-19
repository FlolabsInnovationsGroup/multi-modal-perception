> **SUPERSEDED IN FULL — HISTORICAL DESIGN (2026-09-18).** All decisions, status labels, requirements, and phase gates below are inactive for the revised feature. Do not use them as implementation instructions or evidence of deployed controls. [ADR-006](../../provider-integration/review-record.md) records the scope change; the current PRD and backend contract govern new work. Preserved below for comparison only.

# ADR-005: Approved Provider Endpoints Only in the Initial Release

## Status

Accepted by PRD; custom deployments are deferred.

## Context

Allowing a user to supply an endpoint can turn the server into an SSRF primitive capable of reaching loopback, private networks, cloud metadata services, internal control planes, or attacker-controlled redirect/DNS targets. Compatible APIs also differ in authentication, TLS, data handling, and behavior despite similar request shapes.

## Decision

- Initial release supports only pre-registered official provider endpoints through reviewed adapters.
- Users choose from the platform model catalog; they cannot submit arbitrary endpoints, ports, headers, or provider model identifiers.
- Broker egress is restricted to approved HTTPS provider destinations with reviewed DNS, redirect, TLS, timeout, and response-size behavior.
- Azure OpenAI receives a dedicated later design for endpoint, deployment, region, API version, private networking, and Entra/API-key identity.
- Custom or compatible endpoints require a future PRD amendment, threat-model update, provider/terms review, egress design, ADR, and adversarial tests.

## Consequences

Positive:

- Strongly reduces SSRF, data exfiltration, compatibility, and support risk.
- Makes network policy and provider assurance tractable for the first release.

Costs/risks:

- Enterprise private/custom deployments are unavailable initially.
- Approved endpoint/DNS behavior must be monitored as providers change infrastructure.
- A future custom endpoint feature will need substantially more design than adding a text field.

## Rejected alternatives

- URL format validation alone: cannot prevent DNS rebinding, redirects, private resolution, or malicious compatible services.
- Block private IP strings only: misses IPv6, alternative encodings, DNS changes, redirect chains, and proxy behavior.
- User-defined authentication headers: could expose secrets to arbitrary destinations.

## Verification

- Reject user-provided endpoints, hosts, ports, and sensitive headers.
- Egress tests prove loopback, link-local, metadata, private IPv4/IPv6, unapproved domains, unsafe redirects, and DNS-rebinding scenarios cannot be reached.
- Provider endpoint changes trigger configuration and security review.
