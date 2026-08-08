# Security Policy

## Scope

This repository handles a design for customer-supplied AI-provider credentials. Treat source code, architecture, operational metadata, credentials, customer content, and security findings as confidential unless explicitly classified otherwise.

## Reporting a vulnerability

Do not place vulnerability details, credentials, customer data, exploit steps, or sensitive logs in a public issue, pull request, chat, or support message.

Report privately to the designated security owner through the organization's approved confidential channel.

- Security owner: `SECURITY_OWNER_TBD`
- Private reporting channel: `SECURITY_CHANNEL_TBD`
- Incident escalation contact: `INCIDENT_CONTACT_TBD`

These placeholders must be replaced by authorized organizational contacts before production rollout. Until then, notify the project owner privately and do not disclose the finding more broadly than necessary.

Include only sanitized information:

- A concise description and affected component.
- Reproduction steps using synthetic data.
- Expected and actual behavior.
- Potential tenant, credential, confidentiality, integrity, availability, or cost impact.
- Suggested mitigation if known.

## Secret-handling rules

- Never commit, paste, print, screenshot, record, or transmit real provider keys, AWS credentials, tokens, passwords, connection strings, KMS material, customer data, or production configuration through source control, AI prompts, issues, logs, test output, command history, analytics, or support tools.
- Use synthetic placeholders in documentation and tests. Do not use examples that resemble real provider credentials.
- Never store plaintext provider credentials in PostgreSQL, environment files, fixtures, CI variables, browser storage, caches, message queues, traces, or application logs.
- Credential values are write-only at the product boundary and must never be returned by a GET API or support interface.
- Approved staging credentials must be created and stored through AWS Secrets Manager and used only after the real-credential approval gate.
- If a secret is suspected to have been exposed, stop using it, preserve sanitized evidence, privately notify the security owner, revoke or rotate it through the approved process, and search for secondary exposure.

## Security design requirements

The authoritative requirements are in `docs/byok-credential-broker-prd.md`. The core controls are:

- Mandatory MFA and verified authentication through Amazon Cognito.
- PostgreSQL-authoritative organization/workspace membership and RBAC.
- Application authorization plus foreign keys, uniqueness constraints, and row-level security.
- A private Credential Broker as the only workload permitted to retrieve provider secret values.
- AWS Secrets Manager with a customer-managed KMS key and least-privilege IAM.
- Approved provider endpoints only, provider-specific adapters, and no silent fallback.
- No persistence of prompts, audio, transcripts, or model responses.
- Safe operational metadata, immutable audit export, and documented retention.

## Vulnerability classes requiring immediate escalation

- Plaintext credential disclosure or a credential read-back path.
- Cross-workspace or cross-organization access.
- IDOR or authorization bypass.
- Application API access to `secretsmanager:GetSecretValue` or `kms:Decrypt`.
- Credential Broker access not bound to an authorized workspace request.
- Secrets in logs, traces, exceptions, analytics, database backups, or test artifacts.
- Silent platform-key or alternate-provider fallback.
- SSRF or arbitrary endpoint access.
- Authentication/MFA bypass, token-validation errors, or privilege escalation.
- Destructive migration, data-loss, audit-tampering, or deletion-recovery failure.

## Incident handling outline

1. Contain: disable affected credentials or feature access without deleting evidence.
2. Notify: contact the security and incident owners privately.
3. Assess: identify affected tenants, versions, time range, and data paths.
4. Revoke: rotate or revoke credentials using provider-side controls and the platform lifecycle.
5. Eradicate: correct the root cause and scan all likely secondary locations.
6. Recover: restore service gradually and monitor for repeated use.
7. Learn: complete a blameless review and update tests, runbooks, threat model, and controls.

Detailed executable runbooks are Phase 6 deliverables and must be tested before production.

## Supported state

The BYOK architecture is currently in design and is not production-ready. Existing unauthenticated routes and the process-global OpenAI key are legacy behavior. They must not be represented as secure multi-tenant credential handling.
