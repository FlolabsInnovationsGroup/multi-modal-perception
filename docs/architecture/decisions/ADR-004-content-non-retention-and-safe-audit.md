> **SUPERSEDED IN FULL — HISTORICAL DESIGN (2026-09-18).** All decisions, status labels, requirements, and phase gates below are inactive for the revised feature. Do not use them as implementation instructions or evidence of deployed controls. [ADR-006](ADR-006-provider-integration-scope.md) records the scope change; the current PRD and backend contract govern new work. Preserved below for comparison only.

# ADR-004: No Platform Content Retention and Allowlisted Audit Metadata

## Status

Accepted by PRD; provider-side behavior remains subject to the customer's provider controls and terms.

## Context

Prompts, audio, transcripts, and model responses may contain highly sensitive customer information. The current cross-request response cache creates an unsafe persistence and tenant-isolation boundary. Operations still require enough metadata to diagnose failures, attribute usage, detect abuse, and prove credential lifecycle actions.

## Decision

- Do not persist prompts, audio, transcripts, or model responses in platform databases, caches, queues, logs, traces, analytics, or support tools.
- Remove the global prompt/response cache from provider execution.
- Keep content only for the in-flight request and release references afterward.
- Record allowlisted operational metadata: request ID, opaque tenant/principal/credential identifiers, provider/catalog model, source category, provider request ID, usage, latency, safe outcome/error category, and timestamps.
- Record credential and security audit events for 12 months, operational logs for 30 days, and encrypted RDS backups for no more than 35 days.
- Use field-allowlisted telemetry rather than raw request/response or exception dumps.
- Disclose that provider-side processing/retention is governed separately by the customer's provider project and terms.

## Consequences

Positive:

- Reduces breach, privacy, backup, and cross-tenant cache exposure.
- Makes the platform's content-handling promise clear.
- Retains operational and audit evidence without storing customer content.

Costs/risks:

- Support cannot replay customer requests or inspect raw content.
- Usage/provider metadata remains sensitive and needs tenant isolation.
- Provider-side retention may differ from platform non-retention.
- Retention periods require confirmation against organizational/legal policy.

## Rejected alternatives

- Cross-request content cache: unsafe without an approved tenant/content retention design and outside initial scope.
- Debug logging of raw provider exchanges: likely to expose credentials and customer content.
- No audit data at all: prevents accountability, incident response, and usage attribution.

## Verification

- Schema/repository inspection for forbidden content fields/caches.
- Synthetic content and credential canary scans across logs, traces, database, backups, crash output, and test artifacts.
- Retention configuration and expiry tests.
- Support/incident exercises using metadata only.
