# BYOK Provider Terms and Data-Control Review

## Document control

| Field | Value |
| --- | --- |
| Status | Draft — requires legal and security approval |
| Initial provider | OpenAI |
| Verification date | 2026-08-08 |
| Scope | Technical product implications, not legal advice |

## Purpose

BYOK changes who contracts with and pays the provider, but the platform still sends customer content to that provider. Before enabling a provider, product, security, privacy, and legal owners must confirm the provider agreement, permitted credential use, data-processing roles, retention, region, security controls, and customer disclosures.

This document records technical review questions and known official-source facts. It does not replace legal review or the customer's provider agreement.

## OpenAI initial review

| Topic | Current technical finding | Product/implementation requirement | Owner/status |
| --- | --- | --- | --- |
| API-key handling | OpenAI recommends server-side storage and secure secret management; keys must not be exposed in client code | Key submitted over TLS, stored only in Secrets Manager, never returned, logged, or placed in browser persistence | Security review pending |
| Account and cost | Calls made with a customer key use that customer's provider project/account permissions and billing | UI/policy must clearly identify customer-managed versus platform-managed source; usage is not represented as the final provider bill | Product/legal review pending |
| Training | Official OpenAI API data-control documentation states API data is not used to train models by default unless the customer opts in | Do not make broader promises; disclose that the customer's OpenAI project settings and agreement govern provider behavior | Legal review pending |
| Abuse monitoring | Default API abuse-monitoring logs may retain customer content for up to 30 days; approved Modified Abuse Monitoring or Zero Data Retention controls can change handling and eligibility | Platform non-persistence does not equal provider zero retention; surface this distinction and verify each customer project's controls when required | Privacy/legal review pending |
| Application state | Some API features can persist application state; retention depends on endpoint and feature | Initial adapter must use approved endpoints/options that do not request platform persistence; set storage flags safely where supported and test | Adapter review pending |
| Data residency | Availability and behavior depend on approved OpenAI project/region and eligible features | Workspace policy may expose only regions/endpoints actually approved and supported; do not infer region from the key | Enterprise/legal review pending |
| Model access | Model availability depends on provider project permissions and changes over time | Use a platform catalog plus validation; reverify before catalog changes; no arbitrary identifiers | Product/adapter review pending |
| Validation call | A validation call may consume quota and send synthetic content | Disclose it, use the minimum synthetic capability call, rate-limit it, and never send customer content merely to validate a key | Product/security review pending |
| Error/request IDs | Provider errors and IDs aid support but raw payloads can contain sensitive data | Normalize errors, store only approved provider request ID/safe fields, never return raw exception/body/header dumps | Security review pending |
| Revocation | Customer controls provider-side key revocation; platform disablement only prevents use through this platform | UI/runbook must distinguish platform disable/delete from provider-side revoke and instruct compromise response | Operations review pending |

## Required customer disclosures

Before credential creation or provider use, the product contract/UI should accurately disclose:

- The credential is used server-side to call the selected provider for the workspace.
- Provider usage may create charges on the customer's provider account.
- The customer is responsible for provider-account permissions, quotas, billing, and provider-side revocation.
- The platform does not reveal or allow read-back of the key after submission.
- Validation uses disclosed minimal synthetic provider calls and may consume small quota/cost.
- The platform does not persist prompt/audio/transcript/response content, but the provider may process or retain content under the customer's provider settings and agreement.
- Disablement stops new platform use; deletion has a seven-day platform secret-recovery window and encrypted backups may retain historical metadata for their documented retention.
- No automatic credential/provider fallback occurs unless an explicit future policy is designed and approved.

The final text requires legal/product approval and must not be invented by implementation AI.

## Provider enablement checklist

Complete one reviewed copy of this checklist for every provider and materially different offering, including Azure OpenAI:

- [ ] Named legal, privacy, security, product, and operations reviewers.
- [ ] Provider agreement permits the platform's intended BYOK/agency use.
- [ ] Authentication method and credential scope documented.
- [ ] Official endpoint/region/deployment rules documented and egress reviewed.
- [ ] Data training, abuse monitoring, application-state retention, and residency documented.
- [ ] Subprocessor and data-processing obligations reviewed.
- [ ] Supported capabilities/models verified against the customer account, not marketing assumptions.
- [ ] Minimum validation operation and cost/content impact approved.
- [ ] Rate limits, spend limits, error taxonomy, request IDs, retry/idempotency, and cancellation documented.
- [ ] Provider-side rotation/revocation and compromise instructions documented.
- [ ] Customer disclosures, privacy notice, support limits, and billing language approved.
- [ ] Adapter contract/security tests pass with approved staging credentials.
- [ ] Review date and official sources recorded; re-review trigger assigned.

## Additional-provider status

| Provider | Initial-release status | Required special review |
| --- | --- | --- |
| OpenAI | In scope after Phase 0–3 approvals | API data controls, project/model access, endpoints, validation, billing disclosure |
| Anthropic | Deferred | Authentication, messages/streaming, data controls, regional options, error/usage behavior |
| Google Gemini | Deferred | API key/project controls, data-use terms, regional/product variants, safety settings |
| Azure OpenAI | Deferred with dedicated design | Tenant/subscription/resource/deployment, endpoint and region, API key versus Entra identity, private networking |
| Other/custom endpoint | Out of initial scope | Full provider review plus SSRF/egress, compatibility, contractual, and support model |

## Re-review triggers

- New provider, API family, endpoint, region, model capability, authentication mode, or custom deployment.
- Provider terms, data controls, retention, privacy, security, or pricing change.
- New content modality, streaming, tools, stored state, batch processing, or fine-tuning.
- Customer contractual/regulatory requirement or incident.
- At least annually before continued production support, or more frequently under organizational policy.

## Official sources

- [OpenAI API authentication and key-handling guidance](https://platform.openai.com/docs/api-reference/authentication)
- [OpenAI API data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)

Official technical sources were checked on 2026-08-08. Legal reviewers must confirm the specific agreement and policies applicable to the platform and each customer's account at the time of enablement.
