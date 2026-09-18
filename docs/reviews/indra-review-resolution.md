# Indra Review Resolution and PRD Comparison

Prepared 2026-09-18. Status: **Revision prepared; reviewer acceptance pending**.
Source: [Indra's Notion review](https://app.notion.com/p/flolabsrd/Requirements-for-Providers-Integration-Feature-3a7a1576955180b9b848e94c2e5f9d30).
Reviewed page text and its All discussions panel; substantive comments and edit entries were dated August 15 and September 6, 2026. No Notion content/comments were edited or resolved by this local revision.

Repository comparison baseline: `211c1092551143b5b34412c1ec1604899450469d`.
Original PRD and plan are preserved in [archive](../archive/README.md). Untracked research copy is untouched.

## Main comparison

The original PRD combined feature requirements, a full AWS platform design, authentication/tenancy, credential administration, UI, API/data schemas, tests, operations, and rollout. The Notion page still retained substantial old text, but review comments explicitly rejected much of that as either implementation detail or another team's responsibility. Therefore merely copying the edited body would leave contradictions.

Revision 2 begins with the problem and behavior requirements. It assigns multimodal the provider module, scoped key reading, access validation, and model interaction; separates backend/UI/platform ownership; and moves necessary technical detail into focused supporting documents. It does not assume that removing a paragraph removes the underlying security risk.

## Comment and edit resolution

Quoted anchors below identify the review location; feedback is otherwise paraphrased. Related mechanical edits are grouped, not treated as new requirements.

| # | Review anchor / feedback | Revision response |
| --- | --- | --- |
| R01 | Product/title and document-control table: this is a feature, independent of provider/implementation | Feature Requirements title; no production topology, provider order, scale, or compliance claim in PRD |
| R02 | Executive-summary Cognito and architecture bullets do not belong | Remove technology prescriptions; backend contract records missing mechanisms |
| R03 | Problem statement: multimodal only reads/validates backend-stored keys and interacts with models | PRD purpose and ownership table; scoped reader contract |
| R04 | Invite-only org/workspace goal belongs to FloBrain | Remove auth/tenancy build from plan and AGENTS |
| R05 | Modular provider goal and "later" wording mix requirements with planning | PI-01 provider-independent goal; provider sequence only in plan |
| R06 | Non-goal listing Anthropic/Gemini/Azure implementation timing belongs in plan | Provider rollout moved to plan; no automatic universal-provider claim |
| R07 | Users/authorization: no user differentiator in multimodal | Remove application role matrix; replace with team responsibility matrix; retain service caller/binding verification |
| R08 | Start with requirements after the problem; preceding material unnecessary | Short PRD opens with purpose, boundaries, and behavior; baseline moved to plan |
| R09 | Section 6.1 onboarding not our responsibility | FloBrain owns user onboarding/auth/authorization; no Cognito or invitation tasks |
| R10 | VAL-01 deleted; VAL-02 unclear; deleted-content comment rejects provider architecture as requirement | PI-03 describes validation outcome, not a fixed provider call; module contract explains illustrative checks |
| R11 | VAL-03 UI/validation-cost statement removed from requirements | No UI task; provider check cost reviewed in B5 and enablement checklist, not dismissed as cost-free |
| R12 | VAL-05: capability, safe result category, provider request ID unclear | Plain-language glossary and safe output contract define each |
| R13 | VAL-06 "schedule": are scheduler requirements available? | No scheduler is assumed; explicit validation returns indeterminate on transient failure; backend may request another attempt |
| R14 | Rotation wording changed to register a new API-key value; remove Secrets Manager-specific wording | PI-05 describes behavior; backend stores/activates, multimodal validates exact candidate version; B4 confirms consistency contract |
| R15 | DEL-04/05 deleted: no recovery work | Recovery excluded from multimodal scope and plan; no recovery service/job |
| R16 | DEL-06 deleted: RDS backup statement is not a feature requirement | Remove fixed backup/retention prescriptions; owners define actual policy |
| R17 | POL-02 deleted: workspace configuration is FloBrain work | Backend selects permitted provider/model/source; multimodal checks supported binding |
| R18 | POL-03 unclear | PI-02/04: selected model/operation must match authorized backend configuration, not arbitrary caller choice |
| R19 | POL-05 deleted; POL-06 deleted as implementation solution | Model seed and Azure sequencing not PRD requirements; provider details belong in task plans/configuration |
| R20 | Customer-managed vs platform-managed requests unclear | Glossary: customer's provider account versus platform's; backend explicitly chooses; no fallback |
| R21 | SRC-05 future fallback paragraph deleted | No future fallback roadmap requirement; retained explicit no-fallback outcome PI-06 |
| R22 | INV-01 deleted: exact endpoint is implementation, not requirement | No mandated workspace v1 URL; B6 agrees existing-caller compatibility before route changes |
| R23 | INV-02 authentication and INV-03 deletion: FloBrain authenticates users | Backend owns end-user auth/policy; multimodal still verifies service caller and credential binding, not a duplicate role system |
| R24 | "Write-only credential routes": which routes? | Originally add/replace key submission APIs, not readback. These are backend-owned; no such public route is assigned to multimodal |
| R25 | "shape": what shape? | Replace with explicit request fields, data types, required values, and size/format limits; logical fields in backend contract |
| R26 | "public application": what application? | Replace ambiguous term with FloBrain backend, multimodal service, or user interface according to responsibility |
| R27 | Section 7 UX: not our responsibility | Remove screen specifications; backend/frontend receive integration outcomes, not implementation assignments here |
| R28 | Sections 8 target architecture and 9 data model do not belong in requirements | Small data-flow/contract docs outside PRD; no invented production schema; old AWS design superseded |
| R29 | Sections 10 public API and 11 adapter contract do not belong in requirements | Separate backend and module contracts; exact public route/schema remains B6 |
| R30 | Sections 15 operations plan and 16 approval gates do not belong | Delivery plan outside PRD; approval gates in AGENTS; operations checklist separate |
| R31 | Section 17 test/acceptance plan does not belong | Separate test plan and traceability; PRD retains only required behavior |
| R32 | Section 19 rollout metrics and 21 deferred roadmap do not belong | Remove from PRD; no inherited numeric SLO commitment; plan/release checklist define later decisions |
| R33 | Mechanical edits: Product -> Feature; API key wording; validation/rotation headings | Consistent feature/API-key terminology; define credential and rotation once |

## Answers in everyday language

- Validation asks whether the selected key can perform the requested operation, not merely whether it looks like a key. A provider outage means "could not check", not "bad key".
- A capability is an operation such as text generation or audio transcription. Passing one operation's check does not prove access to all models.
- A tiny fixed prompt or non-sensitive audio fixture is an example of a possible access check. It is not customer content, and it is not mandatory for every provider; the provider engineer proposes the actual check.
- Safe categories make errors actionable without exposing the provider's raw error or key. Provider request IDs are optional support references, not credentials.
- Backend-authenticated configuration answers "which account, key, model, and operation are allowed?" Multimodal must still reject a swapped credential reference rather than blindly trusting IDs.

## Material conflicts and remaining decisions

The old PRD mandated Secrets Manager-only values and a separate private broker. The review describes backend-stored keys and a modular service. The user approved removing the old architecture as this team's prerequisite; this does **not** select plaintext database storage or an unrestricted read API. B1-B3 remain unresolved.

The page retains rotation/disablement wording alongside the broader "read and validate only" responsibility comment. Revision 2 makes a proposed division explicit: backend persists and activates, multimodal validates and respects current state. B4 and T1 must confirm it with the backend/lead.

The original retained operational/retention/SLO language is not assumed approved merely because it remained on the page. The shortened PRD removes those platform commitments; technical limits and release criteria require explicit team agreement.

## Acceptance of the revision

- Requesting user approved preparation of this package on 2026-09-18.
- Indra's acceptance of the rewritten PRD: pending.
- Backend approval of B1-B7: pending.
- No feature code, deployment, Notion publishing, or Discord posting is part of this revision.
