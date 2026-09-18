# Team Responsibility Matrix

Status: proposed handoff assignments, 2026-09-18.
This replaces the old owner/admin/member RBAC matrix. Multimodal does not implement user roles.

| Work | Accountable team | Multimodal contribution | Handoff |
| --- | --- | --- | --- |
| User sign-in, MFA, memberships, authorization | FloBrain backend | Require trusted authorized operation context | B2/B3 |
| Credential submission and protected storage | FloBrain backend | Read only through agreed secure interface; no key-management UI/API | B1 |
| Credential ownership and provider/model/source selection | FloBrain backend | Verify scoped bindings and supported configuration | B2 |
| Credential validation | Multimodal | Provider-specific access check and version-bound safe result | B5 |
| Save replacement / atomic activation / disable / delete | FloBrain backend | Validate candidate, respect selected active state/version | B4 |
| Recovery / provider-account revocation | Backend/platform and account owner | Stop using denied credentials; provide sanitized incident evidence | Operations checklist |
| Provider adapters and inference | Multimodal | Implement, test, normalize errors/usage, prevent fallback | T2-T4 |
| Frontend and customer notices | Frontend/product | Explain validation outcomes and cost/data implications for their contract | B5/B6 |
| Service authentication and route exposure | Backend/platform with multimodal integration | Enforce the agreed service guard; test denial | B3 |
| Cloud resources, secret-store operation, observability platform | Platform/backend owners | Document runtime needs and safe telemetry fields | B1/B7 |
| Staging/release/rollback | Lead + platform/backend | Provide tested artifact and failure/rollback evidence | T6/T7 |

Named teammate assignments are not provided. The lead assigns humans to the suggested roles in the plan; AI must not invent names or commitments. Responsibility transfer does not remove security acceptance checks.
