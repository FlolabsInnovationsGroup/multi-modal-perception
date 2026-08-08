# Product Requirements Document: Bring Your Own AI Provider Key

## Document control

| Field | Value |
|---|---|
| Product | Multi-Modal Perception |
| Feature | Customer-managed AI provider credentials (BYOK) |
| Status | Approved implementation specification |
| Initial provider | OpenAI |
| Future providers | Anthropic, Google Gemini, Azure OpenAI, and additional approved providers |
| Primary repository | multi-modal-perception |
| Production target | AWS, deployed Multi-AZ in the existing primary region |
| Initial scale target | Up to 1,000 workspaces, about 5,000 credentials, and 100 concurrent provider requests |
| Compliance posture | SOC 2-oriented controls and GDPR-compatible deletion; no certification claim |

## 1. Executive summary

Multi-Modal Perception currently uses one process-wide OpenAI API key from the OPENAI_API_KEY environment variable. The service has no authentication, tenant model, authorization, persistent data store, credential lifecycle, or audit trail. Its OpenAI client is a singleton, its response cache is global and keyed only by normalized prompt text, and generation failures are converted into a successful-looking echo response.

Those properties are incompatible with customer-provided credentials. Adding a key field to the existing API would create unacceptable risks of credential disclosure, cross-customer access, unexpected charges, silent routing changes, and response leakage.

This initiative introduces a secure, workspace-scoped provider integration platform:

- Amazon Cognito authenticates users and enforces mandatory MFA.
- The application owns organizations, workspaces, invitations, memberships, and role-based authorization in Amazon RDS for PostgreSQL.
- A separately deployed Credential Broker is the only application component permitted to read provider credentials or send requests to provider endpoints.
- Customer credentials are stored in AWS Secrets Manager using a customer-managed AWS KMS key. PostgreSQL stores metadata and opaque secret references, never credential ciphertext or plaintext.
- Each workspace explicitly chooses customer-managed or platform-managed service. The system never silently changes credentials, models, regions, or providers.
- OpenAI is the first adapter. A common provider interface allows later providers without weakening shared controls.

The feature is successful when authorized workspace users can use an approved OpenAI model with their workspace credential, administrators can safely manage the credential lifecycle, no credential or customer content appears in an unauthorized surface, tenant isolation is proven, and the service meets its reliability and latency objectives.

## 2. Current-state findings

The repository currently contains a small FastAPI service:

- main.py mounts health, process, and OpenAI routers.
- api/process.py and api/openAI.py expose unauthenticated multipart endpoints.
- services/openai_service.py creates an AsyncOpenAI singleton using one environment key.
- The same singleton serves every request.
- A global in-memory dictionary caches responses by lower-cased prompt only.
- Provider generation exceptions return an echo response instead of an error.
- There is no database, migration framework, user identity, workspace context, authorization, credential store, provider policy, audit log, or automated test suite.
- There is no infrastructure-as-code configuration in the repository.

The global cache becomes a direct cross-tenant disclosure path once multiple customers use the service. It must be removed before tenant traffic is accepted. The silent echo behavior violates the no-fallback policy and must be replaced with explicit, normalized error responses.

## 3. Problem statement

Customers need to connect their own AI provider accounts so that they can control provider selection, billing, model access, and compliance. A provider credential is both a secret and a spending authority. Anyone who obtains it may consume the customer’s quota, create charges, or access provider-scoped resources.

The platform must let customers configure provider access without spreading credentials through browsers, application services, databases, logs, analytics, support tools, or operational workflows. It must also prove that one organization or workspace cannot use another workspace’s credential.

## 4. Goals and non-goals

### 4.1 Goals

1. Provide invite-only organization and workspace tenancy with enforceable RBAC.
2. Let an owner or workspace administrator add, validate, rotate, disable, and delete one OpenAI credential per workspace.
3. Keep provider credentials write-only from the customer’s perspective and readable only inside the Credential Broker during an authorized request.
4. Support an explicit choice between customer-managed and platform-managed service without automatic fallback.
5. Enforce a platform model catalog and workspace allowlist.
6. Produce tenant-scoped audit and usage evidence without recording prompts, audio, transcripts, responses, or secrets.
7. Create a provider-adapter contract that supports later provider integrations.
8. Provide a controlled migration from the existing unauthenticated APIs.
9. Meet the v1 availability, latency, isolation, and operational acceptance criteria.

### 4.2 Non-goals

- Implementing Anthropic, Gemini, Azure OpenAI, or other adapters in v1.
- Allowing personal, user-scoped provider credentials.
- Allowing more than one active customer credential for the same workspace and provider.
- Accepting arbitrary provider base URLs or arbitrary model identifiers.
- Automatically creating, rotating, or revoking credentials in a customer’s provider account.
- Automatically failing over to another credential, provider, model, or region.
- Persisting AI interaction content or providing conversation history.
- Building billing-grade metering, invoicing, or cost reconciliation.
- Implementing the companion frontend in this repository.
- Claiming SOC 2, GDPR, HIPAA, or other certification solely because these requirements are implemented.
- Multi-region active-active service or cross-region credential replication in v1.

## 5. Users and authorization

### 5.1 Personas

| Persona | Need |
|---|---|
| Platform operator | Provision an organization and its first owner; operate the service without access to credential values |
| Organization owner | Manage all workspaces, members, provider policies, credentials, audit events, and usage summaries within the organization |
| Workspace administrator | Manage members, provider policies, credentials, audit events, and usage summaries in assigned workspaces |
| Workspace member | Invoke approved models in assigned workspaces; cannot manage or inspect credentials |
| Security operator | Investigate metadata and audit events across tenants through a separate, audited administrative identity; cannot read provider credentials |

### 5.2 Roles

The authoritative application roles are:

- owner: organization-wide access to its workspaces and administrative functions.
- workspace_admin: administrative access only to assigned workspaces.
- member: invocation access only to assigned workspaces.

Cognito groups are not authoritative for workspace membership. The service validates the Cognito access token, resolves its subject to an application user, and evaluates active PostgreSQL memberships for every workspace-scoped request.

### 5.3 Authorization matrix

| Action | Owner | Workspace admin | Member | Platform operator | Security operator |
|---|---:|---:|---:|---:|---:|
| Create workspace | Yes | No | No | No | No |
| Invite workspace member | Yes | Yes | No | Initial owner only | No |
| Change workspace role | Yes | Yes, except owner roles | No | No | No |
| Configure provider source and models | Yes | Yes | No | No | No |
| Add, rotate, disable, or delete credential | Yes | Yes | No | No | No |
| View masked credential metadata | Yes | Yes | No | No | No |
| Invoke an approved model | Yes | Yes | Yes | No | No |
| View workspace audit and usage | Yes | Yes | No | No | Cross-tenant metadata only |
| Read credential plaintext | No | No | No | No | No |

No human role receives Secrets Manager GetSecretValue or KMS Decrypt permission. Emergency AWS access is governed by a separate break-glass procedure, produces CloudTrail evidence, and triggers an alert.

## 6. Product requirements

### 6.1 Organization and workspace onboarding

AUTH-01. Public self-registration is disabled. A platform operator provisions an organization and its first owner through an audited administrative workflow.

AUTH-02. Owners invite users by verified email. An invitation has a single organization, optional initial workspace assignments, role, issuer, creation time, expiration time, and one-time acceptance token.

AUTH-03. All users authenticate through Amazon Cognito and must enroll in MFA before accessing workspace data.

AUTH-04. The API validates token signature, issuer, audience, token use, expiration, and revocation-relevant state. An ID token is never accepted in place of the required access token.

AUTH-05. Disabled users, expired invitations, removed memberships, and disabled workspaces lose access immediately after the authoritative database transaction commits. Existing Cognito tokens do not override database state.

AUTH-06. Every workspace-scoped route obtains workspace_id from the path, not from untrusted token custom attributes. The service verifies that the authenticated subject has an active membership in that exact workspace.

### 6.2 Credential onboarding

CRED-01. A workspace can have at most one active customer-managed credential per provider.

CRED-02. Only an owner or workspace administrator can submit a credential.

CRED-03. The companion UI uses a password-style input. It must not prefill, retain, copy into application state longer than submission, write to localStorage, sessionStorage, IndexedDB, service-worker caches, URL parameters, analytics, error reporting, session replay, or support tooling.

CRED-04. The browser necessarily holds the value while the authorized administrator types it. The enforceable boundary is that it is submitted once over TLS directly to the credential-management surface and is never persisted or displayed again.

CRED-05. Credential request and response headers include Cache-Control: no-store. Credential values are never returned in an API response.

CRED-06. API Gateway, load balancer, WAF, FastAPI, tracing, and error-reporting configurations must exclude request bodies on credential routes. Generic middleware must not serialize request objects.

CRED-07. On submission, the broker stores the value in a new opaque Secrets Manager secret, records only metadata in PostgreSQL, and queues validation using credential and secret-version identifiers. Queue messages never contain credential values.

CRED-08. The create response is HTTP 202 with status pending_validation. The UI polls metadata or receives an approved event until validation succeeds, fails, or remains indeterminate.

CRED-09. Metadata returned to authorized administrators is limited to credential ID, provider, masked suffix, enabled capabilities, allowed models, source, lifecycle status, validation status, creator, and lifecycle timestamps.

### 6.3 Validation

VAL-01. The OpenAI adapter validates every enabled capability with a documented synthetic request using no customer content.

VAL-02. Text validation sends a fixed platform-owned prompt and requests the smallest practical response. Audio validation uses a short platform-owned non-sensitive audio fixture.

VAL-03. The UI clearly states that validation contacts OpenAI and may create a very small charge on the customer account.

VAL-04. Validation has bounded timeouts and retries only transient network or provider-service failures with exponential backoff and jitter. Authentication, authorization, model-access, or quota failures are not blindly retried.

VAL-05. Successful validation records provider, capability, model, safe result category, provider request ID, and timestamp. It does not record the synthetic response body.

VAL-06. If the provider is unavailable, status becomes validation_pending with a safe reason and retry schedule. The credential cannot serve production requests until every required capability is verified.

VAL-07. If the credential or model permission is invalid, the pending secret version is marked invalid and never becomes active.

### 6.4 Rotation

ROT-01. Rotation is a write-only operation that submits a new value for an existing credential record.

ROT-02. Secrets Manager stores the new value as a pending version. The current version remains active while the new version is validated.

ROT-03. Successful validation atomically moves the application’s active version and Secrets Manager staging label to the new version.

ROT-04. Failed validation leaves the current version active and records a safe failure category for the administrator.

ROT-05. Requests that started before activation may complete on the former version. Requests authorized after activation use the new version.

ROT-06. Previous versions are retained only for the approved recovery window and are never selected automatically as runtime fallback.

### 6.5 Disablement and deletion

DEL-01. Disablement is immediate at the application authorization layer. No request authorized after the disable transaction commits may retrieve or use the credential.

DEL-02. An already-started provider call may finish. The UI and customer policy must describe this narrow in-flight limitation.

DEL-03. Deletion first disables the credential, removes it from workspace policy, records an audit event, and schedules Secrets Manager deletion with a seven-day recovery window.

DEL-04. No normal customer or support interface restores a scheduled secret. Recovery within seven days requires a verified customer request, a security-operator procedure, revalidation, and a complete audit trail.

DEL-05. After the recovery window, the metadata state becomes deleted. Audit evidence remains for its retention period and contains no secret.

DEL-06. RDS backups may retain credential metadata for up to 35 days. They never contain the provider credential value. The privacy policy must distinguish immediate use disablement from backup expiration.

### 6.6 Provider and model policy

POL-01. The platform maintains a provider catalog, capability catalog, and supported model catalog.

POL-02. A workspace administrator selects a provider, service source, enabled capabilities, and allowed models from the platform catalog.

POL-03. Request-supplied provider, model, capability, and region must match active workspace policy. The broker rejects mismatches before credential retrieval.

POL-04. Provider base URLs and authentication modes are operator-controlled adapter configuration. Customer-controlled URLs are prohibited to prevent SSRF and credential exfiltration.

POL-05. The v1 catalog is seeded with the current supported OpenAI text-generation and transcription models already used by the repository. Changing the catalog is a controlled configuration release with capability tests.

POL-06. Azure OpenAI is deferred until a dedicated design covers tenant endpoints, deployments, regions, Entra identity, API keys, and network controls.

### 6.7 Service-source selection and fallback

SRC-01. Each workspace-provider policy explicitly selects customer_managed or platform_managed.

SRC-02. A customer-managed request may use only the active credential owned by the request’s workspace and provider.

SRC-03. A platform-managed request may use only the approved platform credential and commercial policy for that workspace.

SRC-04. Missing, invalid, disabled, deleted, expired, rate-limited, or quota-exhausted credentials produce explicit failures. The system never silently changes source, credential, provider, model, endpoint, deployment, or region.

SRC-05. Future fallback is a separate product feature requiring explicit customer configuration, data-routing review, cost disclosure, and acceptance criteria.

### 6.8 AI invocation and content handling

INV-01. All production invocation uses POST /v1/workspaces/{workspace_id}/process.

INV-02. For AI invocation, the public application authenticates the user, checks workspace membership and request shape, and forwards a request identity to the broker over an authenticated private service channel. Write-only credential routes are different: the public gateway authenticates and routes them directly to the broker management listener through a private integration, so ordinary application tasks never parse or forward the credential value.

INV-03. The broker independently verifies service identity, end-user identity, workspace membership, active policy, capability, model, credential source, and credential state before retrieving a secret.

INV-04. A credential is retrieved once for an authorized in-flight request. It may be reused for transcription and generation within that request, then all references and provider client instances are released. It is never cached across requests.

INV-05. Python cannot guarantee physical zeroization of immutable strings. The implementation minimizes copies, lifetime, debug visibility, crash dumps, and heap retention and must not claim guaranteed zeroization.

INV-06. Prompts, audio, transcripts, provider responses, and synthetic validation output are processed transiently and are not persisted, cached, logged, traced, or placed in analytics.

INV-07. The existing global response cache is removed. A future cache requires a separate privacy design, tenant-scoped keys, content-retention consent, encryption, expiry, and deletion behavior.

INV-08. Provider failures return normalized error responses. The existing echo-on-error behavior is removed.

## 7. User journeys and UX requirements

### 7.1 Add an OpenAI credential

1. An owner or workspace administrator opens Workspace Settings > AI Providers.
2. The page shows OpenAI status, selected source, enabled capabilities, allowed models, masked credential metadata, validation state, and last validation time.
3. The administrator selects customer-managed service and chooses capabilities and models from the platform catalog.
4. The UI explains secret handling, the synthetic validation call, potential small provider charge, and that the value cannot be revealed later.
5. The administrator enters the key and confirms submission.
6. The UI clears the input immediately after a successful TLS submission.
7. The screen shows pending validation, then active or a safe corrective error.
8. The audit view records who performed the action and its outcome without the value.

### 7.2 Rotate a credential

1. An authorized administrator selects Replace credential.
2. The UI explains that the existing version stays active until the replacement validates.
3. The administrator submits the new value.
4. Pending validation is shown without disrupting current traffic.
5. Success changes the masked suffix and activation timestamp. Failure preserves the existing active version.

### 7.3 Disable or disconnect

1. An authorized administrator selects Disable or Disconnect.
2. The UI explains the effect on new requests and the possibility that an already-started provider call may complete.
3. Disable requires confirmation and takes effect immediately.
4. Disconnect additionally schedules permanent provider-secret deletion after seven days and explains metadata and backup retention.

### 7.4 Use an approved model

1. A workspace member submits text and/or audio with an allowed provider and model.
2. The service authenticates and authorizes the request.
3. The broker applies policy, uses the selected credential source, and calls OpenAI.
4. The response includes output plus safe request metadata. It never includes credential identifiers intended only for administrators.
5. Failures identify the actionable category without revealing provider secrets or raw exception text.

### 7.5 UX security controls

- Credential pages disable session replay and analytics collection.
- Credential values never appear in toast messages, validation errors, browser URLs, DOM attributes after submission, screenshots generated by support tooling, or clipboard automation.
- The UI displays only a masked suffix and never implies that the original value can be recovered.
- Copy and reveal controls are prohibited after submission.
- All destructive actions require clear confirmation and state their effect.
- Accessibility, keyboard navigation, loading, empty, permission-denied, invalid, unavailable, and retry states are specified for the companion frontend.

## 8. Target architecture

### 8.1 Component view

~~~mermaid
flowchart LR
    U["Customer browser"] -->|"TLS + Cognito access token"| G["API Gateway / WAF"]
    G -->|"Normal product routes"| A["FastAPI application service"]
    G -->|"Write-only credential routes via private integration"| B["Credential Broker management listener on private ECS"]
    A -->|"mTLS, request identity"| B
    B -->|"Tenant/RBAC/policy queries"| D[("RDS PostgreSQL Multi-AZ")]
    B -->|"Get approved secret version"| S["AWS Secrets Manager"]
    S --> K["Customer-managed KMS key"]
    B -->|"Allowlisted TLS egress"| O["OpenAI API"]
    A --> D
    A --> Q["Audit outbox"]
    B --> Q
    Q --> L["Tenant audit query store"]
    Q --> W["Immutable S3 audit archive"]
    C["Cognito User Pool"] --> U
    T["CloudTrail / CloudWatch"] --> W
~~~

### 8.2 Trust boundaries

1. Browser boundary: the browser is untrusted for persistence. It may submit a credential once but cannot store or retrieve it.
2. Public ingress boundary: API Gateway/WAF authenticates and routes credential-management writes through a private integration directly to the broker. Request-body logging, caching, and tracing are disabled for these routes.
3. Public application boundary: the application owns ordinary product APIs but never receives credential-write bodies, has no Secrets Manager read or KMS decrypt permission, and has no direct provider egress.
4. Broker boundary: the broker is private, separately deployed, authenticated, and least-privileged. It is the only application workload that handles plaintext provider credentials.
5. Data boundary: PostgreSQL contains tenant metadata; Secrets Manager contains provider values; KMS key material never leaves KMS.
6. Provider boundary: provider requests leave AWS through controlled egress to operator-approved domains.
7. Audit boundary: operational evidence contains identifiers and outcomes, never secrets or AI content.

### 8.3 AWS deployment requirements

- Terraform defines VPC, private subnets across at least two Availability Zones, security groups, private service discovery, ECS services, load balancing, RDS PostgreSQL Multi-AZ, Cognito, KMS, Secrets Manager policies, validation queue, VPC endpoints, egress controls, CloudWatch, CloudTrail, immutable S3 audit storage, alarms, and environment separation.
- The public API and broker use different ECS task roles and security groups.
- Broker management/validation and invocation tasks use distinct IAM policies where practical. Only the permissions required by their route class are granted.
- Secrets Manager, KMS, CloudWatch, and supported AWS control-plane traffic use VPC endpoints where available.
- Provider traffic uses a controlled NAT/egress path with DNS and destination policies. Adapters cannot override their approved host.
- Service-to-service traffic uses TLS and workload authentication. Network reachability alone is not authorization.
- Production, staging, and development use separate Cognito pools, databases, KMS keys, secret namespaces, IAM roles, and audit destinations.
- Production secrets are never copied into lower environments.

### 8.4 IAM capability matrix

| Capability | Public API | Broker invocation | Broker management/validation | Human operator |
|---|---:|---:|---:|---:|
| Read tenant metadata | Scoped | Scoped | Scoped | Through audited admin API |
| Write tenant metadata | Scoped business actions | Usage/outbox only | Credential state/outbox only | Through audited admin API |
| Create/update/delete provider secret | No | No | Scoped secret namespace only | No |
| Get provider secret value | No | Active version only | Pending version for validation | No |
| KMS decrypt through Secrets Manager | No | Scoped via service and context | Scoped via service and context | No |
| Provider network egress | No | Approved adapter hosts | Validation hosts only | No |
| Read prompt/response content from storage | Not applicable | Not applicable | Not applicable | Not applicable |

## 9. Data model

All primary identifiers are UUIDs. External URLs and audit messages use opaque IDs rather than customer names. Every tenant-owned table includes organization_id and, where applicable, workspace_id. Foreign keys prevent cross-organization relationships. PostgreSQL row-level security provides defense in depth in addition to application authorization.

### 9.1 Core entities

| Entity | Required fields and rules |
|---|---|
| users | id, cognito_sub unique, verified_email, status, created_at, disabled_at |
| organizations | id, display_name, status, created_at, created_by |
| workspaces | id, organization_id, display_name, status, feature_flags, created_at |
| memberships | user_id, organization_id, workspace_id nullable for owner, role, status, created_at; unique active scope |
| invitations | id, organization_id, workspace_id, email, role, token_digest, expires_at, accepted_at, revoked_at |
| providers | id, code unique, display_name, adapter_version, status |
| model_catalog | id, provider_id, provider_model_id, capability, status, configuration constraints |
| workspace_provider_policies | workspace_id, provider_id, source, enabled, allowed_model_ids, capabilities, version, updated_by |
| provider_credentials | id, organization_id, workspace_id, provider_id, secret_arn, masked_suffix, status, active_secret_version_id, created_by, timestamps |
| credential_versions | id, credential_id, secret_version_id, status, validation_summary, created_by, timestamps |
| audit_events | id, occurred_at, organization_id, workspace_id, actor_type, actor_id, action, resource_type, resource_id, outcome, reason_code, request_id, safe metadata |
| usage_events | id, occurred_at, organization_id, workspace_id, provider_id, model_id, capability, credential_source, request_id, provider_request_id, outcome, latency, token counts |
| outbox_events | id, aggregate, event_type, safe payload, created_at, published_at, attempt_count |

### 9.2 Credential states

~~~mermaid
stateDiagram-v2
    [*] --> pending_validation
    pending_validation --> active: all capability tests pass
    pending_validation --> invalid: definitive validation failure
    pending_validation --> pending_validation: transient provider failure
    active --> rotating: replacement submitted
    rotating --> active: replacement fails; old remains
    rotating --> active: replacement passes; new version activates
    active --> disabled: administrator or security action
    invalid --> disabled: administrator action
    disabled --> pending_validation: authorized reconnect with new value
    disabled --> deletion_scheduled: disconnect
    deletion_scheduled --> disabled: approved recovery before deadline
    deletion_scheduled --> deleted: recovery window expires
    deleted --> [*]
~~~

Database constraints and transactions, not UI assumptions, enforce valid state transitions and one active credential per workspace/provider.

## 10. Public API contract

All v1 endpoints require a Cognito access token except health and readiness endpoints. Workspace routes authorize the workspace path parameter. Mutating routes accept an Idempotency-Key header and return a request_id. Credential routes return Cache-Control: no-store.

### 10.1 Tenancy endpoints

| Method and path | Minimum role | Purpose |
|---|---|---|
| POST /v1/organizations | Platform operator | Provision an invite-only organization and first owner |
| GET /v1/organizations/{organization_id} | Owner | Read organization metadata |
| POST /v1/organizations/{organization_id}/workspaces | Owner | Create a workspace |
| GET /v1/workspaces/{workspace_id} | Member | Read authorized workspace metadata |
| POST /v1/workspaces/{workspace_id}/invitations | Owner or workspace_admin | Invite a member |
| GET /v1/workspaces/{workspace_id}/members | Owner or workspace_admin | List active memberships |
| PATCH /v1/workspaces/{workspace_id}/members/{user_id} | Owner or workspace_admin | Change permitted role or status |

### 10.2 Policy and credential endpoints

| Method and path | Minimum role | Purpose |
|---|---|---|
| GET /v1/providers | Member | List supported providers and models allowed for selection |
| GET /v1/workspaces/{workspace_id}/provider-policy | Member | Read effective non-secret provider policy |
| PUT /v1/workspaces/{workspace_id}/provider-policy | Owner or workspace_admin | Select source, capabilities, and allowed models |
| POST /v1/workspaces/{workspace_id}/provider-credentials | Owner or workspace_admin | Submit a new write-only credential |
| GET /v1/workspaces/{workspace_id}/provider-credentials | Owner or workspace_admin | List masked metadata only |
| GET /v1/workspaces/{workspace_id}/provider-credentials/{credential_id} | Owner or workspace_admin | Read masked status and validation metadata |
| POST /v1/workspaces/{workspace_id}/provider-credentials/{credential_id}/rotations | Owner or workspace_admin | Submit and validate a replacement |
| POST /v1/workspaces/{workspace_id}/provider-credentials/{credential_id}/disable | Owner or workspace_admin | Disable immediately |
| DELETE /v1/workspaces/{workspace_id}/provider-credentials/{credential_id} | Owner or workspace_admin | Disable and schedule deletion |

Example credential submission:

~~~json
{
  "provider": "openai",
  "api_key": "<write-only value>",
  "enabled_capabilities": ["text_generation", "audio_transcription"],
  "allowed_model_ids": ["<catalog text model id>", "<catalog transcription model id>"]
}
~~~

Example accepted response:

~~~json
{
  "credential_id": "2c0f0000-0000-4000-8000-000000000001",
  "provider": "openai",
  "masked_value": "••••1234",
  "status": "pending_validation",
  "request_id": "req_opaque",
  "created_at": "2026-07-22T12:00:00Z"
}
~~~

### 10.3 Invocation endpoint

POST /v1/workspaces/{workspace_id}/process accepts multipart/form-data:

- text_input: optional string.
- audio_file: optional supported audio upload.
- provider: required provider code.
- model: required platform catalog ID for generation.
- transcription_model: required when audio is present.

At least one of text_input or audio_file is required. Upload size, media type, duration, decompression behavior, read timeout, and memory limits are enforced before provider execution.

Example successful response:

~~~json
{
  "result": "<model response>",
  "request_id": "req_opaque",
  "provider": "openai",
  "model": "<catalog model id>",
  "credential_source": "customer_managed",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 42
  }
}
~~~

Usage fields are nullable when the provider does not return them. They are operational estimates, not billing records.

### 10.4 Audit and usage endpoints

| Method and path | Minimum role | Purpose |
|---|---|---|
| GET /v1/workspaces/{workspace_id}/audit-events | Owner or workspace_admin | Paginated workspace audit metadata |
| GET /v1/workspaces/{workspace_id}/usage-summary | Owner or workspace_admin | Counts, errors, latency, capabilities, models, and provider-reported tokens |

Neither endpoint returns AI content, credential values, secret ARNs, raw provider errors, or internal IAM details.

### 10.5 Error contract

~~~json
{
  "error": {
    "code": "PROVIDER_CREDENTIAL_INVALID",
    "message": "The configured OpenAI credential is not authorized for this request.",
    "request_id": "req_opaque",
    "retryable": false
  }
}
~~~

Required normalized categories include:

- AUTHENTICATION_REQUIRED
- TOKEN_INVALID
- WORKSPACE_ACCESS_DENIED
- ROLE_INSUFFICIENT
- MODEL_NOT_ALLOWED
- CAPABILITY_NOT_ALLOWED
- PROVIDER_NOT_CONFIGURED
- PROVIDER_CREDENTIAL_PENDING
- PROVIDER_CREDENTIAL_INVALID
- PROVIDER_CREDENTIAL_DISABLED
- PROVIDER_RATE_LIMITED
- PROVIDER_QUOTA_EXCEEDED
- PROVIDER_UNAVAILABLE
- PROVIDER_TIMEOUT
- REQUEST_TOO_LARGE
- UNSUPPORTED_MEDIA_TYPE
- INTERNAL_CONFIGURATION_ERROR

Raw exceptions, headers, credential fragments beyond the approved mask, request bodies, and provider response bodies are excluded. Provider 401/403 errors mark the credential for revalidation but do not automatically disable a working previous rotation version or switch service source.

## 11. Provider adapter contract

Each adapter implements the same security-preserving operations:

| Operation | Contract |
|---|---|
| validate_credentials | Run capability-specific synthetic checks and return normalized status without returning credential data |
| generate_text | Accept validated model configuration and transient content; return output, safe usage, provider request ID, and normalized errors |
| transcribe_audio | Accept validated transcription model and transient bytes; return transcript for the current request only |
| supported_capabilities | Report adapter capabilities to the operator-controlled catalog process |
| normalize_error | Map provider errors to safe platform categories and retry guidance |
| extract_usage | Return provider-reported usage without claiming billing accuracy |

Adapters must not:

- accept a user-controlled endpoint;
- log authorization headers, SDK client configuration, request content, or provider bodies;
- choose a different model or provider when a request fails;
- retain SDK clients containing customer credentials beyond one request;
- expose provider-specific exception text to public APIs;
- bypass workspace model and capability policy.

The initial OpenAI adapter preserves the current text-generation and audio-transcription behavior where compatible. API modernization or model replacement is a separate, tested change rather than an implicit part of BYOK.

## 12. Logging, auditing, privacy, and retention

### 12.1 Events that must be audited

- Organization, workspace, membership, invitation, and role changes.
- Credential create, validation, activation, rotation, disable, recovery, and deletion actions.
- Provider policy and model allowlist changes.
- Credential selection decisions by credential ID and version ID, never value.
- Authorization denials and cross-tenant attempts.
- Provider authentication, rate-limit, quota, timeout, and availability categories.
- Secrets Manager and KMS administrative actions through CloudTrail.
- Break-glass access, infrastructure changes, backup restores, and retention jobs.

### 12.2 Safe audit event shape

Every event includes a UTC timestamp, organization/workspace scope, actor type and opaque ID, action, target type and opaque ID, outcome, safe reason code, request ID, service version, and approved metadata. Correct clock synchronization is monitored.

### 12.3 Prohibited telemetry

The following must never enter application logs, audit events, metrics labels, traces, analytics, support exports, or alert payloads:

- provider credentials or authorization headers;
- Secrets Manager returned values;
- prompts, audio, transcripts, model responses, or validation responses;
- multipart bodies or credential-route JSON bodies;
- raw SDK clients, exception objects, HTTP request objects, or environment dumps.

### 12.4 Retention

| Data | Retention |
|---|---|
| Tenant-visible security and credential audit events | 12 months |
| Operational application logs and traces | 30 days |
| Usage metadata | 12 months unless product policy shortens it |
| Automated RDS backups | Up to 35 days |
| Deleted Secrets Manager credential recovery | 7 days |
| AI interaction content | Not persisted |

An append-only transactional outbox prevents successful security-sensitive changes from occurring without a corresponding audit event. Events are exported to an immutable S3 Object Lock archive. Customer queries use a tenant-filtered query store; security operators use a separate audited administrative path.

## 13. Reliability, performance, and observability

### 13.1 Service objectives

- Credential Broker availability: 99.9% per calendar month.
- Platform overhead: p95 no more than 250 ms, excluding provider processing, provider throttling, and client upload time.
- Tenant isolation: zero known cross-tenant credential or content disclosures.
- Credential leakage: zero credential values in databases, logs, traces, responses, analytics, or support systems.
- Disablement: no request authorized after the disable transaction commits may fetch the disabled credential.
- Audit completeness: 100% of successful credential lifecycle state changes create durable audit events.

### 13.2 Metrics

- Request counts and latency by safe route template, provider, model catalog ID, capability, source, and normalized outcome.
- Authentication and authorization denial counts.
- Credential validation success, failure, pending, and retry counts.
- Secrets Manager and KMS latency/error counts without secret identifiers in high-cardinality labels.
- Provider rate-limit, quota, authentication, timeout, and availability counts.
- ECS task health, queue depth/age, RDS connections/replication/backup status, audit outbox lag, and immutable archive delivery lag.
- Legacy endpoint request counts during the migration window.

### 13.3 Alerts

Alerts are required for:

- any detected secret pattern in logs or build artifacts;
- repeated cross-tenant authorization denials;
- elevated provider authentication failures for an active credential;
- unauthorized or unusual Secrets Manager/KMS access;
- audit outbox backlog or archive failure;
- broker availability or latency budget burn;
- validation queue age beyond its objective;
- failed backups, restore tests, retention jobs, or deletion jobs;
- unexpected public reachability or egress destinations.

## 14. Security threat model

| Threat | Example | Required controls |
|---|---|---|
| Credential disclosure in client | Browser analytics records form state | Dedicated no-analytics route, no browser persistence, no reveal API, TLS, no-store headers |
| Log leakage | Middleware logs request body or SDK exception | Body logging disabled, structured allowlisted fields, redaction tests, secret scanning |
| Database compromise | Attacker steals RDS snapshot | No credential value/ciphertext in RDS; opaque Secrets Manager reference only |
| Cross-tenant IDOR | User changes workspace ID in URL | Path-scoped membership lookup, RLS, ownership foreign keys, adversarial tests |
| Compromised application service | Public API tries GetSecretValue | Separate IAM roles, explicit deny/absence, private broker, no provider egress |
| Compromised broker | Process accesses many secrets | Scoped resource policies, KMS conditions, no ListSecrets, anomaly alerts, short plaintext lifetime |
| SSRF or endpoint substitution | Admin enters attacker URL | Operator-controlled endpoints and egress allowlist; no user base URL |
| Silent data routing | Invalid key triggers another provider | Explicit source and model; normalized error; no fallback code path |
| Rotation race | Invalid new key replaces valid key | Pending version, validate first, transactional activation |
| Disable race | New request uses just-disabled key | Authorize against current status immediately before retrieval; define in-flight limitation |
| Stale response cache | Workspace receives another tenant’s cached answer | Remove global cache; no content caching in v1 |
| Insider misuse | Support staff retrieves a key | No human read permission, separate security identity, break-glass controls and alerts |
| Backup retention mismatch | Customer expects immediate physical erasure | Immediate logical disable, transparent seven-day/35-day retention policy |
| Provider error leakage | Raw response exposes account information | Provider adapter normalization and safe public error schema |
| Credential replay | Captured submission is resent | TLS, authenticated route, idempotency keys, short request lifetime, no body storage |

Security review must also cover denial of service, oversized audio, malformed multipart data, decompression bombs, dependency compromise, container escape, credential presence in crash dumps, and Terraform/IAM policy drift.

## 15. Operational delivery plan

Each phase is completed and verified before the next production-impacting phase begins. Routine work can proceed within an approved phase, but the approval gates in Section 16 remain mandatory.

### Phase 0: Security and architecture gate

Objective: establish approved boundaries and evidence before implementation.

Deliverables:

- Final data-flow and trust-boundary diagram.
- STRIDE-style threat model and abuse-case review.
- Role/permission matrix and IAM policy design.
- Data classification, retention, deletion, and privacy review.
- OpenAI terms and customer-disclosure review.
- Terraform module design and environment topology.
- Dependency proposal for database access, migrations, Cognito JWT verification, AWS SDK, testing, and Terraform tooling.
- Cost model for Secrets Manager per credential, KMS operations, Private CA/service authentication, RDS, ECS, egress, logging, and immutable audit storage.

Verification and exit gate:

- Security, platform, backend, product, and privacy owners approve the design.
- No unresolved critical threat or undefined secret-handling path remains.
- Required dependency, migration, infrastructure, and environment approvals are recorded.

### Phase 1: Authentication and tenancy foundation

Objective: ensure every protected request has an authenticated user and authoritative workspace scope.

Deliverables:

- Cognito user pool, invitation-only configuration, mandatory MFA, and environment isolation.
- JWT verification middleware.
- PostgreSQL schema and migrations for users, organizations, workspaces, memberships, and invitations.
- Owner, workspace_admin, and member authorization policies.
- RLS policies and tenant-scoped repository/service patterns.
- Organization provisioning and invitation APIs.
- Audit outbox foundation.

Verification and exit gate:

- Unit and integration tests cover token validation, invitations, role changes, disabled users, and membership revocation.
- Adversarial tests cannot cross organization or workspace boundaries.
- No legacy unauthenticated endpoint can access the new tenant or credential features.

### Phase 2: AWS broker and secret foundation

Objective: create the isolated workload that alone can manage and use credentials.

Deliverables:

- Terraform VPC, ECS, private routing, workload TLS/authentication, IAM task roles, KMS key, Secrets Manager namespaces/policies, validation queue, RDS connectivity, CloudTrail, CloudWatch, and alarms.
- Separate public API and broker deployment units.
- Credential metadata schema and lifecycle transaction rules.
- Write-only secret ingestion and masked metadata.
- Immediate disable and scheduled deletion workflows.
- Immutable audit export.

Verification and exit gate:

- Public API and human roles are demonstrably denied GetSecretValue and KMS Decrypt.
- Database snapshots contain no provider credential values.
- Network tests prove the broker is not publicly reachable and the public API cannot reach provider endpoints directly.
- CloudTrail and application audits capture safe lifecycle evidence.

### Phase 3: OpenAI credential lifecycle

Objective: safely activate and maintain a workspace OpenAI credential.

Deliverables:

- OpenAI credential validation adapter for text and transcription.
- Asynchronous validation state and retry policy.
- Atomic activation and rotation.
- Disable, disconnect, recovery, and deletion jobs.
- Provider/model catalog and workspace policy APIs.
- Credential status and safe error contracts.

Verification and exit gate:

- Invalid replacement leaves the previous version active.
- Successful replacement changes active version atomically.
- Disabled/deleted credentials cannot be selected.
- Tests confirm no secret appears in API output, logs, traces, queue messages, database fields, or exceptions.
- Approved staging credentials reside only in staging Secrets Manager.

### Phase 4: Brokered OpenAI invocation

Objective: move production provider calls behind workspace policy and the broker.

Deliverables:

- Request-scoped OpenAI client/adaptor behavior.
- Generic authenticated v1 process endpoint.
- Text generation and transcription using the explicit workspace policy.
- Removal of global response cache.
- Removal of silent echo fallback.
- Safe provider errors, usage metadata, provider request IDs, limits, and timeouts.
- Platform-managed source path with no automatic fallback.

Verification and exit gate:

- Functional parity tests cover existing valid text/audio behavior.
- Failure tests prove no source/model/provider switching.
- Cross-workspace requests cannot select another workspace’s credential.
- No AI content is persisted or logged.
- Focused and broad test suites pass.

### Phase 5: Companion UI contract and customer operations

Objective: provide a complete, safe customer-management experience.

Deliverables:

- Final frontend screen specifications and API examples.
- Add, validate, rotate, disable, disconnect, provider-source, model-policy, audit, and usage flows.
- Accessibility and responsive-state requirements.
- Analytics/session-replay exclusions and verification checklist.
- Customer documentation for key creation, least privilege, validation cost, rotation, compromise, deletion, and provider support.
- Support procedure that explicitly prohibits receiving keys.

Verification and exit gate:

- Browser tests find no credential in storage, URLs, analytics, error reporting, DOM after submission, or cached responses.
- Permission tests hide or deny administrative functions for members.
- Customer-facing lifecycle language matches actual retention behavior.

### Phase 6: Hardening and operational readiness

Objective: prove security, recovery, scale, and support readiness.

Deliverables:

- Full unit, integration, contract, infrastructure, security, and load test suites.
- Secret-scanning and dependency/security checks in CI.
- Dashboards, SLO alerts, on-call playbooks, incident severity criteria, and escalation paths.
- Credential compromise, provider outage, KMS/Secrets Manager outage, audit failure, backup restore, and break-glass runbooks.
- RDS restore, Secrets Manager recovery, Terraform plan/rollback, and ECS rollback exercises.
- Production readiness review and evidence package.

Verification and exit gate:

- 100 concurrent request test meets the 250 ms p95 platform-overhead objective.
- Restore and deletion-recovery drills pass.
- No open critical/high security defect or silent data-loss risk remains.
- On-call, support, security, and customer-success teams approve runbooks.

### Phase 7: Controlled rollout and legacy migration

Objective: release safely and retire insecure entry points.

Steps:

1. Deploy dark with the workspace feature flag disabled.
2. Enable internal test workspaces with platform-managed credentials.
3. Enable selected design partners with customer-managed credentials.
4. Review validation, authorization, provider-error, latency, and support metrics daily.
5. Expand only when phase gates and error budgets remain healthy.
6. Announce deprecation of /process and /openAI when authenticated v1 is production-ready.
7. Track legacy use by safe client identity and route metrics for 30 days.
8. Remove legacy routes from production after the migration window.
9. Retain local development stubs only when they cannot be enabled in production.

Rollback:

- Disable BYOK per workspace using the feature flag.
- Stop new credential submissions while leaving encrypted secrets and metadata intact.
- Roll back broker/API ECS task versions through Terraform/deployment automation.
- Do not silently move customer-managed workspaces to platform-managed service.
- Preserve lifecycle/audit evidence throughout rollback.

## 16. Mandatory implementation approval gates

The PRD itself does not authorize any of the following. Explicit approval is required immediately before:

- adding, changing, or removing Python, Terraform, test, security, or runtime dependencies;
- creating or changing development environments that install software;
- creating database schemas or applying migrations;
- creating or changing AWS resources, IAM policies, KMS keys, Secrets Manager entries, Cognito pools, networking, billing resources, or production configuration;
- using real credentials or customer data;
- deploying to staging or production;
- deleting files/data, forcing operations, or performing hard-to-reverse actions;
- creating branches, commits, pushes, pull requests, tags, or releases.

Each approval request must identify the exact action, reason, expected effect, main risks, rollback, and safer alternatives.

## 17. Test and acceptance plan

### 17.1 Functional tests

- Organization provisioning and invitation acceptance.
- Mandatory MFA and invalid/expired/wrong-audience token rejection.
- Workspace creation, membership, role changes, and revocation.
- Provider catalog and workspace allowlist enforcement.
- Credential add, pending validation, success, definitive failure, and transient retry.
- Rotation success and failure with old-version continuity.
- Immediate disable, scheduled deletion, approved recovery, and final deletion.
- Customer-managed and platform-managed explicit selection.
- Text-only, audio-only, and combined OpenAI requests.
- Safe audit and usage summaries.
- Idempotent create/rotation requests.

### 17.2 Tenant-isolation and adversarial tests

- Change organization_id, workspace_id, membership ID, credential ID, version ID, policy ID, and audit cursor to another tenant.
- Attempt horizontal and vertical privilege escalation.
- Use revoked membership with a still-valid Cognito token.
- Race disablement, rotation, deletion, and invocation.
- Submit malformed, oversized, unsupported, and adversarial multipart payloads.
- Attempt SSRF through provider/model fields and metadata.
- Attempt to inject credentials into logs, validation errors, model input, filenames, headers, and tracing baggage.
- Confirm RLS and application checks independently deny cross-tenant data.

### 17.3 Secret-leakage tests

- Scan source, Git history, build output, containers, Terraform plans/state handling, CI logs, test reports, CloudWatch, CloudTrail, traces, database snapshots, queue messages, browser storage, and support exports.
- Force OpenAI SDK, Secrets Manager, KMS, database, network, and serialization errors.
- Confirm no raw exception or request body reaches public responses or telemetry.
- Confirm public API and human IAM roles cannot retrieve or decrypt provider secrets.

### 17.4 Provider and fallback tests

- Invalid key, restricted key, wrong model permission, revoked key, quota exhaustion, rate limiting, timeout, malformed response, and provider outage.
- Verify every failure maps to the expected normalized category.
- Verify no failure invokes a platform key, previous key version, alternate provider, alternate model, or alternate region.
- Verify provider request IDs and usage are recorded only when safely available.

### 17.5 Infrastructure and recovery tests

- Terraform validation, policy checks, plan review, environment isolation, and rollback.
- Private broker reachability and public API egress denial.
- Secrets Manager/KMS access-policy denial and CloudTrail evidence.
- RDS Multi-AZ failover, backup restore, outbox recovery, audit archive immutability, and retention expiration.
- Seven-day secret recovery and final deletion workflow.
- ECS deployment rollback and validation-queue replay/idempotency.

### 17.6 Performance and reliability tests

- 100 concurrent requests across multiple workspaces and credential sources.
- p50/p95/p99 platform overhead separated from provider latency.
- Secrets Manager, database, queue, and broker saturation behavior.
- Broker task failure, provider timeout, retry storm, and partial dependency outage.
- SLO and alert verification using controlled failure injection.

### 17.7 Release acceptance criteria

The feature may enter general availability only when:

1. All approved functional and security requirements are implemented.
2. Authentication, RBAC, RLS, and adversarial tenant-isolation tests pass.
3. No credential appears in any prohibited surface.
4. Database-only compromise cannot recover credential values.
5. Public application and human roles are denied secret read/decrypt access.
6. Rotation, disablement, deletion, backup, and recovery drills pass.
7. No silent fallback path exists.
8. The 99.9% design and 250 ms p95 overhead target pass readiness review.
9. Required dashboards, alerts, on-call procedures, and customer documentation are operational.
10. No known critical/high security defect, data-loss risk, or unapproved production dependency remains.

## 18. Incident and support runbooks

### 18.1 Suspected customer credential compromise

1. Authenticate the reporting administrator; never ask them to send the key.
2. Disable the credential immediately and record the request ID.
3. Advise the customer to revoke the key at OpenAI and review provider usage.
4. Review tenant audit events, broker usage metadata, provider request IDs, CloudTrail, and IAM activity.
5. Search approved telemetry for leak indicators without reproducing any secret.
6. Have the customer create a replacement directly in OpenAI and submit it through the secure flow.
7. Validate and activate the replacement.
8. Complete incident classification, notification, evidence retention, and corrective actions.

### 18.2 Provider outage or rate limiting

1. Confirm normalized provider errors and provider status.
2. Preserve the configured credential source, provider, model, and region.
3. Return explicit retry guidance where safe.
4. Do not use platform credentials or another provider.
5. Communicate impact and recovery through approved channels.

### 18.3 Suspected platform secret exposure

1. Trigger the security incident process and freeze credential changes if needed.
2. Disable affected credentials and restrict broker IAM/network access.
3. Preserve CloudTrail, immutable audits, deployment evidence, and volatile forensic data under approved procedures.
4. Notify affected customers with clear provider-side revocation instructions.
5. Rotate platform KMS/IAM/service credentials according to the approved containment plan.
6. Restore only after root cause, blast radius, and regression controls are verified.

### 18.4 Broker or Secrets Manager outage

1. Fail closed with PROVIDER_UNAVAILABLE or INTERNAL_CONFIGURATION_ERROR.
2. Do not expose cached credentials; cross-request plaintext caching does not exist.
3. Monitor dependency recovery and error-budget impact.
4. Use the approved AWS recovery path. Break-glass access must not bypass tenant policy.

## 19. Rollout metrics and product success

The launch is considered successful when, over the design-partner period:

- at least 95% of valid credential submissions activate without support intervention;
- definitive validation failures provide an actionable safe category;
- zero unauthorized credential reads or cross-tenant access events occur;
- zero secrets or AI content are detected in prohibited telemetry/storage;
- at least 99.9% broker availability is maintained;
- p95 platform overhead remains at or below 250 ms under the target load;
- 100% of credential lifecycle actions produce durable audit events;
- legacy production traffic reaches zero before route removal;
- no workspace experiences an unapproved credential/provider/model fallback.

## 20. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Secrets Manager per-secret and per-request cost | Higher operating cost at scale | Track cost, prohibit cross-request plaintext caching in v1, review architecture before exceeding scale target |
| Per-request secret retrieval latency | SLO pressure | Private endpoint, connection reuse without key reuse, measure independently, scale broker horizontally |
| Customers provide overly broad OpenAI keys | Larger customer blast radius | Document project-scoped/restricted keys, synthetic capability tests, provider-side budget/IP controls |
| Browser extensions can inspect typed values | Client compromise | Honest disclosure, minimize DOM lifetime, offer management API, never claim browser input is fully trusted |
| Cognito token remains valid after role removal | Stale identity token | Authoritative membership check on every workspace request |
| Python memory cannot guarantee zeroization | Residual process-memory risk | Short lifetime, minimal copies, no dumps/logs, hardened containers, no cross-request cache |
| Provider permission models differ | Adapter inconsistency | Shared invariant tests plus provider-specific threat/design review |
| Audit store contains sensitive metadata | Privacy exposure | Data minimization, tenant filtering, encryption, retention, restricted security-operator access |
| Legacy endpoints remain callable | Unauthenticated cost/security path | 30-day measured deprecation and production removal |
| Terraform state exposes sensitive outputs | Secret leakage | Never pass customer values through Terraform; encrypted remote state, least privilege, no sensitive output |

## 21. Deferred roadmap

After OpenAI v1 is stable:

1. Add Anthropic through the same adapter invariants and a provider-specific security review.
2. Add Google Gemini with its supported authentication modes, endpoints, regions, quotas, and model catalog.
3. Design Azure OpenAI separately for resource endpoints, deployments, regions, API keys, Entra workload identity, and private networking.
4. Evaluate customer external-vault references and short-lived identity-based provider authentication where providers support it.
5. Evaluate explicitly configured fallback only as a separate consent, routing, compliance, and billing feature.
6. Reassess Secrets Manager cost and latency before exceeding 1,000 workspaces or 5,000 stored credentials.
7. Evaluate multi-region disaster recovery after RTO, RPO, residency, provider routing, and secret replication requirements are approved.

## 22. Source basis

This PRD uses the following primary security guidance:

- OpenAI API authentication guidance: https://platform.openai.com/docs/api-reference/authentication
- OpenAI API data controls: https://platform.openai.com/docs/models/default-usage-policies-by-endpoint
- OpenAI API authentication reference: https://developers.openai.com/api/reference/overview#authentication
- AWS Secrets Manager best practices: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
- AWS Secrets Manager encryption and KMS envelope encryption: https://docs.aws.amazon.com/secretsmanager/latest/userguide/security-encryption.html
- AWS Secrets Manager GetSecretValue security notes: https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
- Amazon Cognito multi-tenancy security recommendations: https://docs.aws.amazon.com/cognito/latest/developerguide/multi-tenancy-security-recommendations.html
- Amazon Cognito JWT guidance: https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-with-identity-providers.html
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

These sources support the server-side credential boundary, centralized secrets management, least privilege, encryption, lifecycle management, TLS, safe logging, auditing, and incident-response requirements. Provider terms, APIs, and security capabilities must be rechecked immediately before each provider implementation.
