# M2 Interface Proposal for the FloBrain Backend (P-1)

Status: **proposal for review by Ofon (backend owner), 2026-11-13. Not agreed.** Prepared by Mani from the backend answers to B1-B7 and the lead decisions D-1 to D-6 (see the [review record](review-record.md)). Nothing here is built on the backend side, and the multimodal side will not connect to a live backend until this is agreed, dated and tested.

Names in `code` style marked *(proposed)* are suggestions the backend may rename. Field names without that mark already exist in the multimodal module.

## 1. What this proposal covers

How a request travels between FloBrain and the multimodal service when the AI provider is called with a backend-managed key:

1. FloBrain authorizes the user, chooses the key and model, and calls multimodal with a short-lived **signed request token** (section 3).
2. Multimodal verifies the token, checks the model against its approved list (D-5), and asks FloBrain's **credential endpoint** for exactly that key version (section 4).
3. Multimodal calls the provider once, discards the key, and returns the result with usage (sections 5-6).

```
FloBrain backend                       Multimodal service                      Provider
      | POST /invoke + signed token  ->        |                                    |
      |                                        | verify token, check model          |
      |  <- POST credential endpoint           |                                    |
      |     (same token, multimodal identity)  |                                    |
      |  key for exact version, no-store   ->  |                                    |
      |                                        | one call with that key         ->  |
      |                                        |                                <-  |
      |  <- result, usage, request IDs         | key discarded                      |
```

Keys are never sent in the request from FloBrain to multimodal, never cached across requests and never returned by multimodal.

## 2. Who builds what

| FloBrain backend | Multimodal |
| --- | --- |
| User sign-in, permissions, choosing the key and model per request | Verifying the signed token and rejecting mismatches |
| Storing keys encrypted; customer key submission (D-1) and platform keys | Reading only the key version named in the token |
| Key states and versions, activation, rotation, disabling (B4) | Calling the provider with limits, safe errors and no fallback |
| Signing request tokens and publishing the verification keys | Returning results, usage and validation outcomes |
| The credential endpoint, with single-use checks | The `/invoke`, `/transcribe` and `/validate` routes |
| Storing validation results and usage (B5.20, B6.23) | Never storing prompts, audio, transcripts or keys |
| HTTPS and private networking with the infrastructure owner (B3.10) | Refusing to run without the agreed configuration |

## 3. Signed request token (FloBrain to multimodal)

Sent as `Authorization: Bearer <token>` on every call. Recommended format: a JWT signed with an **asymmetric** key (EdDSA or ES256), so multimodal holds only the public key and cannot create tokens itself.

| Claim | Meaning | Rule on the multimodal side |
| --- | --- | --- |
| `iss` | Issuer, for example `flobrain-backend` *(proposed)* | Must match configuration exactly |
| `aud` | Audience, for example `multimodal-perception` *(proposed)* | Must match exactly |
| `iat`, `nbf`, `exp` | Issue, not-before and expiry times | Lifetime at most 90 seconds *(proposed)*; clock skew allowance 30 seconds *(proposed)* |
| `jti` | Unique request ID, also used as `request_id` | Allowed characters `A-Z a-z 0-9 . _ : -`, at most 128 |
| `kind` | `invoke` or `validate` | A validate token cannot be used to invoke, and the reverse |
| `binding.scope_id` | Opaque owner scope (customer or workspace) | Same identifier rule; compared exactly |
| `binding.credential_ref` | Opaque key record reference | Same rule |
| `binding.credential_version` | Exact key version | Same rule; old versions are refused after rotation (B4.13) |
| `binding.credential_source` | `customer` or `platform` (D-1) | Never substituted for the other |
| `binding.provider` | For example `openai` | Must be a configured provider |
| `targets` | List of `{operation, model}` the backend allows for this request, from `model_registry` (B2.7). Operations: `generate_text`, `transcribe_audio` | Each requested model must be in this list **and** in multimodal's approved list (D-5). For `validate`, exactly one target |

The token never contains the key, prompts, audio or personal data. Any verification failure returns the single generic denial (B3.11).

**Signing keys.** The backend publishes its public keys with a key ID (`kid`), either as a protected JWKS URL or as deployment configuration. Rotation means adding the new key before signing with it and removing the old key after the longest token lifetime.

**Replay.** Tokens are short-lived, and the credential endpoint accepts each `jti` once for each purpose (section 4). That stops a copied token from being used to read a key again, even across several multimodal instances.

**Dependency note.** Verifying JWTs in Python needs a library such as PyJWT with the `cryptography` package. Adding it is a separate approval on the multimodal side.

## 4. Credential endpoint (FloBrain, called by multimodal)

| Item | Proposal |
| --- | --- |
| Call | `POST <backend-internal-url>/internal/credentials/resolve` *(proposed)*, HTTPS, private network only |
| Who may call | Multimodal only: mutual TLS, or a separate multimodal service credential from the deployment secret store. The infrastructure owner decides |
| Request body | `{"context_token": "<the token from section 3>"}`. The backend re-verifies it and reads the binding and kind from it, never from separate fields |
| Success (200) | `{"binding": {...same five fields...}, "state": "active" or "pending", "permitted_targets": [{"operation": "...", "model": "..."}], "key": "<secret>"}` with `Cache-Control: no-store` |
| Atomic read | State, version and key are read together (B4.14). For `invoke`, only the current active version is returned; for `validate`, active or pending |
| Single use | The backend records the token's `jti` per kind and refuses a second fetch |
| Errors | Token invalid or wrong caller: 403. Version not current, disabled, deleted or expired: 409 *(proposed)*. Store unavailable: 503. Bodies use the backend's error shape with no key details |
| Time | Must answer within 5 seconds (multimodal's admission limit) |
| Logging | Never log the key or the response body. Log only `jti`, outcome and timing |

On the multimodal side: 403 maps to `ACCESS_DENIED`; 409 and 503 map to `CREDENTIAL_UNAVAILABLE`. A returned binding that differs from the token is treated as `ACCESS_DENIED`. There is no retry and no fallback key.

## 5. Routes multimodal will expose

No route is registered until sections 3 and 4 are agreed, HTTPS is in place and the joint tests pass. `/process` and `/openAI` stay unchanged until M2 is verified in staging (B6.22).

**`POST /invoke`** (JSON, text generation)

```json
{"text": "Hello", "generation_model": "gpt-4o-mini"}
```

**`POST /transcribe`** (multipart, audio with optional text)

| Field | Meaning |
| --- | --- |
| `audio` | Audio file: wav, mp3, m4a, webm, mp4, mpeg or mpga; at most 10 MiB |
| `audio_format` | One of the formats above |
| `transcription_model` | For example `gpt-4o-mini-transcribe` |
| `generation_model` | For example `gpt-4o-mini` |
| `text` | Optional instruction; default "reply to the audio" |

This matches today's `/process` behavior: transcribe, then generate a reply. The transcript itself is not returned (see open question O-6).

**`POST /validate`** (JSON, token `kind` = `validate`)

```json
{"operation": "generate_text", "model": "gpt-4o-mini"}
```

Returns `status` (`valid`, `rejected` or `indeterminate`), `reason_code`, `checked_at`, `credential_version`, `provider_request_id` and `request_id`, which covers the fields in B5.20. One small fixed provider check, never customer content, and never activates a key. The module already produces these values; their HTTP mapping is built in T5 after agreement.

## 6. Responses

**Success (200)**, as implemented in `http_contract.to_http`:

```json
{"result": "...", "model": "gpt-4o-mini", "file_type": "text", "total_tokens": 15,
 "provider_request_id": "req_...", "request_id": "..."}
```

`total_tokens` and `provider_request_id` come from the generation step and are `null` when the provider did not report them. Null means unknown, not zero.

**Errors**: `{"error_code": "...", "message": "...", "request_id": "..."}`.

| `error_code` | Status |
| --- | --- |
| `INVALID_INPUT`, `UNSUPPORTED_OPERATION` | 400 |
| `ACCESS_DENIED` with a missing or unreadable token | 401 |
| `ACCESS_DENIED` (other), `CREDENTIAL_UNAVAILABLE`, `CREDENTIAL_REJECTED`, `CAPABILITY_DENIED` | 403, all with the message "Access denied." |
| `RATE_LIMITED`, `QUOTA_EXCEEDED`, `CAPACITY_EXCEEDED` | 429 |
| `NOT_CONFIGURED`, `PROVIDER_UNAVAILABLE` | 503 |
| `PROVIDER_RESPONSE_INVALID` | 502 |
| `PROVIDER_TIMEOUT`, `OPERATION_TIMEOUT` | 504 |
| `INTERNAL_ERROR` | 500 |

502 and 504 are additions to the statuses suggested in B6.21.

## 7. Limits

| Limit | Value |
| --- | --- |
| Whole request | 60 seconds (D-3), equal to the backend's `MULTIMODAL_SERVICE_TIMEOUT` |
| Validation | 20 seconds |
| Text | 64 KiB |
| Audio | 10 MiB, which the gateway should also enforce before the body is read (B7.26) |
| Concurrent operations | 8 per multimodal process; the ninth gets 429 `CAPACITY_EXCEEDED` |
| Retries | None, by either side, for the same request ID |

## 8. Rollout and rollback

Joint contract tests run first with synthetic keys only, then staging with an approved test key. The backend's `USE_CREDENTIALED_LLM` flag switches between `/process` and the new path, with no silent fallback (B6.24). Production use and the retirement of `/process` each need separate approval.

## 9. Open questions for Ofon

| ID | Question | Multimodal recommendation |
| --- | --- | --- |
| O-1 | Token format and algorithm (section 3) | JWT with EdDSA or ES256 |
| O-2 | How multimodal gets the public keys and how they rotate | Protected JWKS URL with `kid` |
| O-3 | Token lifetime and clock skew | At most 90 seconds; 30 seconds of skew |
| O-4 | How multimodal proves its identity to the credential endpoint | Mutual TLS if infrastructure supports it |
| O-5 | **Images.** `MultimodalLLMAdapter` sends an optional `image`, but today's `/process` only reads `text_input` and `audio_file`, so images are ignored. The new module supports text and audio only | Confirm whether image input is needed. If yes, it becomes its own task |
| O-6 | Should `/transcribe` return only the transcript, or transcribe and then reply as `/process` does today | Keep today's behavior for M2; add transcript-only later if needed |
| O-7 | Should error bodies include usage for steps that reached the provider before a failure, for billing | Not by default; add a field if billing needs it |
| O-8 | Plan and dates for customer key submission and storage (D-1) | Needed before M2 testing of customer keys |
| O-9 | Who owns HTTPS and private networking, and by when (B3.10) | Infrastructure or deployment manager |
| O-10 | Replacement models in `model_registry` before 2027-01-14 (text) and 2027-02-26 (transcription) | Send the model IDs so they can be added to multimodal's approved list |
| O-11 | Owner and target dates for sections 3-4 | Needed to plan T5 |

Please answer each item with a date. Multimodal will record the answers and turn the agreed parts into contract tests before any live connection.
