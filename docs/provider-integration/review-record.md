# Provider Integration Review Record

Prepared 2026-09-18; local implementation-specification revision 2.1 added 2026-09-19. Status: **Ready for review; reviewer acceptance pending**. The previous Notion publication is not yet synchronized with revision 2.1.
Source: [Indra's Notion review](https://app.notion.com/p/flolabsrd/Requirements-for-Providers-Integration-Feature-3a7a1576955180b9b848e94c2e5f9d30).
Reviewed page text and its All discussions panel; substantive comments and edit entries were dated August 15 and September 6, 2026. The original review page and its comments were not edited or resolved. The later approved publication uses the separate V2 review page.

Repository comparison baseline: `211c1092551143b5b34412c1ec1604899450469d`.
Original PRD and plan are preserved in [archive](../archive/provider-integration-v1/README.md). The later approved consolidation removed the confirmed redundant research copy and retained the canonical research in the archive.

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
- The subsequent user approval authorizes documentation consolidation and publication under Notion V2. It does not authorize feature code, deployment, Git writes, or Discord posting.

## ADR-006 — Scope and backend ownership

Date: 2026-09-18.
Status: **Scope revision approved by the requesting user; detailed contracts proposed.**

### Evidence

Indra Araujo's Notion review (August 15 / September 6, 2026) assigns user authentication and backend storage responsibilities to FloBrain, limits multimodal to reading/validating API keys and model interaction, and asks for provider-independent feature requirements.

On 2026-09-18 the requesting user approved the proposed documentation-only revision and explicitly requested CODEX instead of CLAUDE. This records that approval, not a new approval from Indra or the backend team.

### Decision

- This repository delivers a modular provider-integration feature, not a full identity/tenancy/credential-management/cloud platform.
- FloBrain owns user authorization and protected credential lifecycle persistence; multimodal consumes an agreed scoped credential-access contract.
- Multimodal owns validation and provider interaction, safe errors/usage, request isolation, no secret leakage, and no silent fallback.
- Requirements stay in the short PRD. Contracts, tests, operations, and provider sequence live in separate documents.
- Retain AGENTS and use CODEX as the explicit coding handoff guide.
- Supersede ADR-001 through ADR-005 and the prior all-platform plan/design as authorities for this feature. Their useful security outcomes are restated in the current PRD rather than inherited implicitly.

### Not decided at the original scope decision

Actual storage, direct database versus mediated access, decryption, service authentication, exact wire schemas, lifecycle admission consistency, limits, and route migration. B1-B7 require joint approval. No plaintext database design is approved.

Revision 2.1 below now supplies proposed local limits and simulated admission semantics for M1. It does not resolve the corresponding live B decisions or alter this historical scope approval.

### Consequences

The team can review a small local module and then build/test with synthetic fakes without first building Cognito/RDS/ECS. Live integration remains blocked until its trust boundary is defined and verified.

Supersession does not remove a deployed security control: the prior target architecture was not implemented in this repository. It must not be used as permission to weaken real backend/platform controls.

## Consolidation decision and provenance

On 2026-09-18 the requesting user approved combining the current documentation into nine active feature documents, keeping five root guides, moving history into one archive, removing the confirmed redundant research copy, and publishing the current package to Notion V2. Requirements PI-01–PI-12, test cases TC-01–TC-14, and review responses R01–R33 retain their IDs. This is an organization/handoff change, not a new architecture approval.

Source checkpoint: `d73ab6779d5a6a267cd042e1208be9af80b2d932` on `Mani's_First_Multi_Model_Branch`. Consolidation changes are local until separately committed/pushed. The previous verification report at that commit describes the previous layout; its 32-file/68-link counts are historical, not current evidence.

### File migration map

| Previous document(s) | Canonical destination |
| --- | --- |
| docs/README | [Start here](README.md) |
| Legacy-named BYOK PRD | [Requirements](requirements.md) |
| PLAN + team responsibility matrix | [Delivery plan](delivery-plan.md) |
| Module contract + data flow + backend contract | [Technical design](technical-design.md) |
| Threat checklist + provider review + operations | [Security and operations](security-and-operations.md) |
| Test plan + traceability matrix | [Acceptance tests](acceptance-tests.md) |
| Indra resolution + ADR-006 + documentation verification | This review record |
| Implementation start prompt | [Codex start prompt](codex-start-prompt.md) |
| Discord announcement | [Team announcement](team-announcement.md) |
| Original PRD/plan, AWS design, ADR-001–005, research | [Historical archive](../archive/provider-integration-v1/README.md) |

Merged source files are removed rather than left as competing copies. Their previous content is recoverable at the source checkpoint. Historical document bodies are preserved except for relocated navigation links. The duplicate research body was identical after removing the canonical historical banner and normalizing line endings.

### Documentation verification

Local checks completed on 2026-09-18:

| Check | Actual result |
| --- | --- |
| File read-back | 24 of 24 consolidated files match intended content before this evidence entry |
| Package layout | Nine active feature documents, five root guides, ten historical files |
| Local Markdown links | 83 checked; zero broken |
| Fenced blocks | Zero unbalanced files |
| Stable IDs | 12 PI requirements, 14 TC cases, 33 R review responses retained |
| Historical preservation | All nine historical source bodies match after navigation-link/line-ending normalization |
| Stale active path scan | Only the intentional previous-index name in the migration table |
| Discord message bodies | 1,162 / 1,508 / 1,279 characters; each below 2,000 |
| Git whitespace | `git diff --check` exit 0 |
| Application/config/dependency changes | `git diff --name-only -- '*.py' '*.txt' '*.toml' '*.yaml' '*.yml' '*.json'` returned no files |
| Staged changes | `git diff --cached --name-only` returned no files |

Methods: read every output file and compare against the intended text; resolve every relative Markdown link with PowerShell Test-Path; count fenced blocks and stable ID rows; compare historical bodies ignoring relocated Markdown link targets. Git reported the existing global-ignore access warning and LF-to-CRLF notices; settings were not changed.

Feature tests remain not run; feature code is unchanged. The earlier Downloads folder was absent. No dependency installation, real provider call, Git write, deployment, or Discord posting was performed.

### Notion publication — 2026-09-19

The user explicitly approved replacing the ten temporary V2 child pages. All ten were moved to Notion Trash (recoverable); the parent V2 page, V1, original PRD review, Indra's comments, task properties, and sharing permissions were preserved.

The update connector rejected its documented page-ID parameter, and an initial browser paste duplicated text. The replacement uses complete native Notion pages created directly from the local Markdown. Tables are native tables; the full Codex prompt is a code block. This changes presentation/navigation, not requirement wording.

The first 13 published content pages were fetched back: five root guides, one history overview, and seven feature documents. There were no publication placeholders. All 12 PI requirement IDs and all 14 TC test IDs were present. The 5,079-character Codex prompt block matched the local source exactly; Notion changed only its code-language label from text to plain text. Content-line checks found no omissions after accounting for Notion's list/link rendering.

The Start Here page and this review record are published last so they can link the completed package. Notion is a review mirror; the repository remains authoritative. Relative source references not yet available as Notion links are shown as repository paths with navigation back to the V2 index. Historical bodies remain in the repository archive and V1 rather than being duplicated into the active review flow.

No feature code or live security test is implied by publication. T1 review remains pending; local implementation begins only after its task approval.

## Revision 2.1 — Multimodal implementation specification

Date: 2026-09-19. The user requested complete documentation for the multimodal team's independently buildable part and explicitly approved the proposed documentation-only update. Authority granted: edit local documentation, specify the design/tasks/tests, align handoff materials, and verify consistency. Not granted: implementation, installations, live credentials, Git writes or a new Notion publication. This is not Indra's acceptance of the new technical choices.

### What changed and why

The prior package described responsibilities and conceptual interfaces but deferred internal types, a concrete limit profile, probe methods and implementation-sized task cards. Revision 2.1 fills those local gaps in the existing nine documents, while keeping the PRD short. Architecture is prominent in the technical-design title and diagrams. B1-B7 remain genuine external integration decisions rather than fabricated production facts.

Trade-offs: retain existing OpenAI models/API family for the first slice; use standard-library testing and explicit dependency injection; choose a conservative local profile with no retries/redirects; leave existing public routes disconnected from the new module during M1. This reduces scope and permits independent local completion, but does not secure the legacy routes or prove live authorization. The response-size cap and SDK version preflight are explicit work, not assertions that existing tooling already meets them.

### T1 decision sheet — fill during review

All statuses below are **proposed / pending**. Accept or amend each row; record reviewer, date, accepted revision and conditions. Do not tick the whole table just because this documentation task was approved. Team names/contacts remain for the lead to assign.

| ID | Review decision | Status / evidence |
| --- | --- | --- |
| L1 | Component architecture, file map, module ownership; no new deployed broker | Pending |
| L2 | Exact internal types, failure envelopes, operations and secret handling | Pending |
| L3 | Fake verifier/reader, lifecycle state table and atomic admission tests | Pending |
| L4 | Text/audio composition, legacy-success mapping and no-spooling live boundary | Pending |
| L5 | Numerical local limit profile, deadlines, capacity, zero retries and bounded responses | Pending |
| L6 | OpenAI-first models/API calls, probes, usage/error mapping and SDK preflight | Pending |
| L7 | Offline test harness and deny-all default; no M1 public wiring | Pending |
| L8 | M1 evidence/handoff definition and separation from live completion | Pending |

Acceptance entry template: `L ID(s); reviewer; date; revision; accepted/amended/rejected; amendment/conditions; affected PI/TC IDs; evidence; task owner`. T1 exits only after the affected documents are reconciled with accepted amendments. Implementation begins with a separately approved T2.1 plan.

### Publication and sharing

Revision 2.1 is local and uncommitted. The Notion V2 page still shows the previous consolidated package. The revised Discord messages are drafts to send only after this revision is shared and its Notion publication verified. No historical file, original Indra comment, task property or Notion page was changed by this revision. Repository changes from the previous consolidation remain intact.

### Revision 2.1 verification

Checks executed on 2026-09-19 after drafting:

| Check | Result |
| --- | --- |
| Package structure | 24 Markdown documents total: nine active, five root, ten archive; no extra competing file |
| Relative Markdown links | 86 resolved with PowerShell Test-Path; zero broken |
| Markdown fences and trailing whitespace | Checked every document including untracked files; zero issues |
| Stable IDs | 12 PI requirements, 14 TC cases, 33 R feedback responses retained |
| Implementation specificity | Eight L decisions and seven T2.1-T4.2 cards; all proposed/pending, not marked passed |
| PRD length | 1,228 whitespace-delimited words; detailed implementation remains outside PRD |
| Discord draft bodies | 1,209 / 1,480 / 1,348 characters; all below 2,000 |
| Git whitespace | git diff --check reported no whitespace errors; explicit Markdown checks also cover untracked files |
| Application/dependency changes | git diff --name-only over Python, txt, toml, yaml, yml and json files returned none; repository file listing shows no new implementation/test files |
| Git staging | git diff --cached --name-only returned none |
| Provider facts | Opened current official API/SDK/model/error references; recorded SDK-major-version mismatch and preserved existing model/API family; no live calls |
| Consistency review | Corrected ambiguous validation failures, 401 and quota classification, async context-manager signatures, old deferred-probe wording, and publication status |

Only nine active feature documents and root README/CODEX were edited in this task. Existing consolidation deletions/relocations remain pre-existing changes; no additional files were deleted. The initial patch-validation failures made no changes and were corrected before applying the updates. Git continued to report the existing global-ignore permission warning and line-ending notices; no settings were changed.

Feature tests remain not run; there is no implementation in this task. No production security claim follows from these documentation checks. Notion, Discord, Git history, dependencies and credentials were unchanged.
