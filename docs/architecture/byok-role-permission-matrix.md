# BYOK Role and Service Permission Matrix

## Document control

| Field | Value |
| --- | --- |
| Status | Draft for product and security review |
| PRD basis | Sections 5–7, 10, and 18 |
| Last updated | 2026-08-08 |

## Product roles

- **Owner:** Organization-level authority, including workspace and owner/admin governance.
- **Workspace admin:** Administrative authority limited to assigned workspaces.
- **Member:** Can use approved provider/model capabilities but cannot manage credentials or membership.

All actions require a valid authenticated user, mandatory MFA state, active membership, and server-side workspace authorization. A role does not grant access outside its tenant.

## Product permission matrix

| Capability | Owner | Workspace admin | Member | Required safeguards |
| --- | --- | --- | --- | --- |
| View organization metadata | Allow | Allow if member of an organization workspace as product permits | Limited safe view | Tenant-scoped response |
| Update organization metadata | Allow | Deny | Deny | Audit and validation |
| Create workspace | Allow | Deny unless separately approved | Deny | Organization authorization |
| View workspace metadata | Allow | Allow for assigned workspace | Allow for assigned workspace | RLS and membership |
| Update workspace metadata | Allow | Allow for assigned workspace | Deny | Audit |
| Invite member | Allow | Allow for assigned workspace | Deny | Verified destination, expiry, single use |
| List memberships | Allow | Allow for assigned workspace | Limited self/workspace view per product contract | No cross-tenant enumeration |
| Change member role | Allow | Allow member-level changes within assigned workspace; cannot create/modify owner unless approved | Deny | Prevent self-escalation/last-owner loss |
| Remove member | Allow | Allow non-owner members in assigned workspace | Deny | Last-owner and self-lockout protection |
| View provider credential metadata | Allow | Allow for assigned workspace | Deny | Masked metadata only |
| Add provider credential | Allow | Allow for assigned workspace | Deny | Write-only key and step-up/confirmation policy |
| Validate credential | Allow | Allow for assigned workspace | Deny | Rate limit, disclosed provider call, audit |
| Rotate credential | Allow | Allow for assigned workspace | Deny | Validate-before-switch, atomic activation |
| Disable credential | Allow | Allow for assigned workspace | Deny | Immediate effect, confirmation, audit |
| Delete/restore credential | Allow | Allow for assigned workspace | Deny | Seven-day recovery and audit |
| View workspace provider policy | Allow | Allow | Allow safe effective policy | No secret/source detail beyond contract |
| Change credential-source/provider/model policy | Allow | Allow for assigned workspace | Deny | Explicit no-fallback default, audit |
| Invoke approved model | Allow | Allow | Allow | Membership, model allowlist, quota, active credential source |
| View usage summary | Allow | Allow | Own/workspace view as product approves | Aggregation and tenant scoping |
| View audit events | Allow | Allow for assigned workspace | Deny by default | Safe fields, pagination, immutable evidence |
| Export audit events | Allow if approved | Deny by default | Deny | Separate permission and data handling review |
| Configure platform-wide catalog/provider | Deny unless separate platform-admin role is designed | Deny | Deny | Out of current tenant-role scope |

## Safety rules for role changes

- Never authorize from a client-supplied role or workspace claim alone.
- Resolve identity from the validated token and membership from PostgreSQL.
- An administrator cannot grant a role more privileged than their own.
- Preserve at least one active organization owner.
- Role and membership changes invalidate or recheck authorization promptly; exact session behavior must be approved.
- Credential lifecycle and policy changes generate owner-visible audit events.
- Sensitive operations may require recent MFA/step-up confirmation if supported by the selected Cognito design; this is a Phase 1 product/security decision.

## Service capability matrix

| Capability | Public API | Credential Broker | Migration job | Terraform/deploy role | Operator | Break-glass |
| --- | --- | --- | --- | --- | --- | --- |
| Validate Cognito token | Yes | No, trusts authenticated service context plus internal identity | No | No | No | No |
| Read memberships/policy | Yes | Minimum binding/state recheck | Schema access only | No | Safe diagnostic views only | Time-bound if approved |
| Write membership/policy | Authorized product operations | No | Migration only | No | No | Incident-only if approved |
| Store credential value | Forward without logging | Yes, directly to Secrets Manager | No | No | No | Incident-only if unavoidable |
| Read credential value | Never | Yes, one in-flight request, resource-scoped | Never | Never by default | Never | Exceptional, time-bound, audited |
| Call OpenAI | Never in target architecture | Yes, approved endpoints/models | No | No | No | No |
| Read secret metadata ARN | Authorized safe metadata | Yes | Migration as required | Provisioning metadata | Safe limited view | Time-bound |
| `kms:Decrypt` / `GetSecretValue` | Denied/absent | Indirect/allowed as required through Secrets Manager and scoped policy | Denied | Denied by default | Denied | Exceptional audited role only |
| Write audit event | Yes | Yes | Migration event | Infrastructure event via CloudTrail | No mutation | Append incident action |
| Modify audit history | Never | Never | Never except approved schema maintenance | Never | Never | Never |
| Apply infrastructure | Never | Never | Never | Only after explicit approval | Never | Recovery-only and approved |

## Endpoint authorization requirements

Every `/v1/workspaces/{workspace_id}/...` endpoint must:

1. Validate authentication and required MFA.
2. Parse and validate identifiers without leaking existence.
3. Load active membership from PostgreSQL.
4. Enforce the centralized action permission.
5. Apply tenant context/RLS before querying tenant tables.
6. Enforce workspace provider/model/credential-source policy.
7. Record a safe audit event for security-sensitive changes and outcomes.

Public credential GET responses may include only safe identifier, provider, masked value, state, validation timestamps/outcome category, last-used timestamp, creator/rotator safe identity, and version metadata approved by the API contract. They never include the credential, secret payload, authorization header, KMS data, or raw provider error.

## Review questions

- Can workspace admins promote another workspace admin, or only owners?
- What member-level usage/audit aggregation is visible?
- Which operations require recent/step-up MFA beyond mandatory sign-in MFA?
- Is a separate platform administrator/support role required, and what safe capabilities does it have?
- What happens to active sessions immediately after removal, role downgrade, or user disablement?

These choices affect externally visible authorization and require product/security approval during P0-09/P1-02.
