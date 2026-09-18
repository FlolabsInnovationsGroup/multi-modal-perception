# Provider Integration Operations and Release Checklist

Status: ready for review, 2026-09-18. No deployment authorization.

## Failure handling

| Event | Multimodal behavior | Backend/platform action |
| --- | --- | --- |
| Key rejected / no permission | Safe error or rejected validation; no fallback | Review account permissions; manage replacement |
| Rate limit / quota / provider outage | Explicit category; no hidden provider/source switch | Apply approved retry/customer policy |
| Backend credential source unavailable | Fail closed; never use environment key or fake | Restore backend access |
| Key suspected exposed | Stop affected use through agreed disable/control path; preserve sanitized evidence | Security owner coordinates disable and provider-side revocation |
| Stale candidate validation | Return exact checked version; no activation | Reject stale result |
| Cancelled operation | Close local resources; no promise to undo upstream spend | Track safe partial usage if available |

Do not send keys or customer content to support. Use request ID, provider/model, safe category, timestamp, and approved scoped references. The service returns safe validation/usage metadata; backend owns persistence and platform owns retention. No seven-day recovery, 35-day backup, or 12-month audit commitment is inherited.

## Before live staging

- [ ] T1-T5 and B1-B7 approvals/evidence recorded.
- [ ] Service authentication and scoped reader permissions verified, including negative cases.
- [ ] Runtime destinations, models, timeouts, upload/concurrency limits, retry policy, and content-spooling controls recorded.
- [ ] Only approved staging keys through the agreed protected backend mechanism; separate approval before use.
- [ ] Provider enablement review completed with current official sources.
- [ ] Security owner, backend contact, release owner, and confidential reporting channel assigned.

## Release gate

Run TC-01 through TC-14 at the appropriate layers. Record actual results; mock success alone is insufficient. No unresolved critical/high credential-leakage or scope-isolation defect. Agree expected load and pass limits before measuring.

Enable for a small approved internal cohort first, check actual result/error/usage behavior and latency/resource use, then expand only with the release owner's authorization. Deployment and external changes need separate approvals.

B6 defines caller compatibility. Do not automatically remove `/process` or `/openAI`, publish a new workspace API, or start a fixed 30-day countdown.

## Rollback

Document and test the exact mechanism in the approved deployment environment: disable the new feature path or restore a known-safe release. Deny BYOK operations when disabled; never route them to the legacy shared platform key or echo fallback. Preserve backend credential state and sanitized evidence. Coordinate any existing-caller impact with the backend owner.

No new feature flags, cloud resources, or deployment tooling are created by this checklist. If the environment lacks a safe rollback mechanism, release remains blocked until its owner supplies one.
