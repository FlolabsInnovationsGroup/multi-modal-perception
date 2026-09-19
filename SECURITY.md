# Security Policy

## Reporting

Report suspected key exposure, cross-customer use, or service-authentication bypass privately to the designated project/security owner. Do not post credentials, customer content, raw logs, or exploitable details publicly.

Security owner, confidential reporting channel, and incident contact are **not yet supplied**. The lead must identify them before live integration/release. Until then use the project owner's approved private channel and sanitized reproductions only.

## Feature controls

Follow the current [PRD](docs/provider-integration/requirements.md), [backend contract](docs/provider-integration/technical-design.md), and [threat checklist](docs/provider-integration/security-and-operations.md).

- Real keys never belong in source, AI prompts, chat, URLs, screenshots, command history, test fixtures, CI variables/output, logs, traces, or support messages.
- Use synthetic values such as `test-provider-key-redacted` for local development/tests.
- Backend owns protected credential storage/lifecycle. Actual retrieval/decryption is unresolved; do not create an unapproved plaintext database, local secret file, or environment-key substitute.
- Multimodal accepts only authenticated backend operations bound to the authorized scope/provider/credential/version. Private reachability alone is insufficient.
- Use secrets only inside request-local execution; no key read-back, cross-request credential client/cache, or arbitrary provider destination.
- No silent credential/source/model/provider fallback and no echo-on-error.
- Do not persist or log prompts, audio, transcripts, or model responses. Check upload temporary files and failure cleanup.
- Validation of pending credentials is not activation or permission for ordinary invocation.

The old Cognito/RLS/ECS/Secrets Manager mandates are superseded for this repository. This does not authorize weakening backend controls or claim that a database compromise is safe. The agreed integration must demonstrate protection and scoped access.

## Incident handoff

Stop affected use through the approved control, preserve sanitized evidence, notify the security/backend owner, and coordinate provider-side revocation/replacement with the account owner. Do not independently rotate/delete real credentials or change production permissions without explicit authorization.

See [operations checklist](docs/provider-integration/security-and-operations.md) for safe outcomes, staging gates, and rollback. Provider-specific data handling/retention must be verified separately; this service cannot guarantee the provider's retention behavior.
