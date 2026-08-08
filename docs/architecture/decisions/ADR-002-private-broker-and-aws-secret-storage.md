# ADR-002: Private Credential Broker with Secrets Manager and KMS

## Status

Accepted by PRD; implementation subject to Phase 0, AWS, IAM, dependency, and credential gates.

## Context

A provider API key can authorize spend and access on a customer's provider account. Keeping it in a general application database, frontend, or broadly privileged service would expand the blast radius of a compromise. The database must be useful for tenant lifecycle and policy without containing decryptable credential values.

## Decision

- Run a separate private Credential Broker service on ECS.
- Only the broker workload role may retrieve BYOK secret values and call approved provider endpoints.
- Store provider credential values in AWS Secrets Manager encrypted under a customer-managed KMS key.
- Store only opaque secret ARNs, masked metadata, version/state, and tenant ownership in PostgreSQL.
- Retrieve plaintext once per in-flight request and never cache it across requests.
- Never return plaintext to the public API or another service.
- Use opaque secret names/tags and record AWS access through CloudTrail.
- Enforce immediate application disablement and a seven-day Secrets Manager deletion-recovery window.

## Consequences

Positive:

- Database compromise alone does not reveal provider keys.
- IAM and network boundaries reduce the number of credential-capable workloads.
- Secrets Manager/KMS provide versioning, encryption, access logs, and recoverable deletion primitives.

Costs/risks:

- The broker becomes a high-value service and requires hardening, monitoring, least privilege, and an incident runbook.
- Every invocation adds a secret retrieval operation and platform overhead.
- Secrets Manager metadata is not encrypted as the secret value and must remain non-sensitive.
- A compromised broker/AWS administrator remains a critical residual risk.

## Rejected alternatives

- Plaintext database or environment storage: unacceptable disclosure and isolation risk.
- Application-managed encrypted blobs in PostgreSQL: increases cryptographic/key-management complexity and still broadens database/application access.
- Passing credentials from browser on every invocation: exposes keys repeatedly and prevents safe centralized lifecycle/audit.
- Letting the public API retrieve secrets: violates least privilege and expands blast radius.

## Verification

- Database and restored-backup inspection cannot recover a credential.
- Public API role is denied `GetSecretValue` and `kms:Decrypt`.
- Broker role is limited to the expected environment/secret namespace.
- Synthetic canary never appears in responses, logs, traces, database, queues, or test output.
- Disable, rotation, delete, restore, and concurrent invocation tests.
