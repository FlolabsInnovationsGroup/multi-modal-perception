# Speech Synthesis Design (T3.3)

Status: **deferred to future work (lead decision, 2026-11-13).** Not part of the provider-integration feature or its pull request. Kept as a draft so a future task can start from it; recheck the provider facts below before using it. No code, dependency, route or live call is approved by this note. Owner: Mani. Decision source: D-4 in the [review record](review-record.md).

## 1. Purpose and scope

D-4 adds a `/synthesize` operation: the backend sends text and receives audio bytes. This note proposes how to build it behind the same fail-closed boundary as generation and transcription (L1-L8), and lists what must be decided before code.

In scope: one synthesis operation for OpenAI, request-scoped credentials, bounded output, safe errors, usage and tests. Out of scope: live conversations, voice input, custom voices, streaming audio to the caller, other providers, and the backend's route or UI.

## 2. Provider facts (official OpenAI pages, read 2026-11-13)

| Fact | Source |
| --- | --- |
| `tts-1`, `tts-1-hd`, `gpt-4o-mini-tts` and its snapshots shut down on **2027-01-06** (notice 2026-10-01). No model is listed for `/v1/audio/speech` after that | Text-to-speech guide; deprecations page; Create speech reference |
| The recommended replacement is `gpt-realtime-2.1-mini`, which runs only through the Realtime API, not `/v1/audio/speech` | Text-to-speech guide; deprecations page |
| `gpt-realtime-2.1-mini` is not listed for shutdown. `gpt-realtime-mini` shuts down 2027-01-20 and points to it | Deprecations page |
| Realtime transports: WebRTC, WebSocket and SIP. WebSocket is described as the choice for server-to-server use | Realtime guide; Realtime conversations guide |
| WebSocket endpoint `wss://api.openai.com/v1/realtime?model=<model>`, authenticated with the standard API key as a Bearer header | Realtime conversations guide |
| Audio-only output is set with `output_modalities: ["audio"]` and `audio.output.format`, for example `audio/pcm` at 24,000 Hz | Realtime conversations guide |
| Out-of-band responses (`conversation: "none"`) with fixed instructions such as "Say exactly the following" are shown as an example; reading verbatim is not guaranteed | Realtime conversations guide |
| Audio arrives only in `response.output_audio.delta` events (base64); `response.done` ends the response and carries its status | Realtime conversations guide |
| Voices: alloy, ash, ballad, coral, echo, sage, shimmer, verse, marin, cedar; marin or cedar recommended. A voice cannot change after audio starts | Realtime conversations guide |
| Max output tokens 32,000; context 128,000; session limit 60 minutes | Model page; Realtime conversations guide |
| Price per 1M tokens: text input $0.60, audio output $20.00 | Model page (no date shown) |
| Data retention for Realtime sessions | **Not stated** on the pages read |

Local check (2026-11-13): installed `openai` 1.109.1 includes `AsyncOpenAI.realtime.connect`, which imports the `websockets` package. `websockets` is **not installed** in `.venv` and is not in `requirements.txt`.

There is no text-to-speech in the service today, so the 2027-01-06 shutdown breaks nothing that exists. It only rules out building on `/v1/audio/speech`.

## 3. Options

| Option | Summary | Assessment |
| --- | --- | --- |
| **A. Realtime API through the installed SDK** (recommended) | One WebSocket session per request with `client.realtime.connect`, audio-only output, closed after one response | Uses the provider's named replacement. Needs the `websockets` dependency (approval gate) and new guard and test code for WebSockets |
| B. Speech endpoint now, migrate later | `/v1/audio/speech` over the existing guarded HTTP transport | No new dependency, but it stops working on 2027-01-06, before M2 can go live. Throwaway work |
| C. Chat Completions with audio output | HTTP request to an audio-capable chat model | No new dependency, but not documented as the text-to-speech path; the older `gpt-audio` models shut down 2027-01-20. Would need its own evaluation |
| D. Raw WebSocket library | Hand-written client with another package | Also a new dependency, plus more code than the SDK. No benefit |

## 4. Proposed design (option A)

### Contract additions (core track)

| Item | Proposal |
| --- | --- |
| Operation | New `Operation.SYNTHESIZE_SPEECH`; approved target `(synthesize_speech, gpt-realtime-2.1-mini)` in provider configuration |
| Request | `SynthesisRequest(text, voice, target)`. Text is required, stripped, and limited to 4,096 characters (the old speech endpoint's limit; Realtime states none). The voice comes from an approved list in configuration |
| Result | `SynthesisResult(request_id, provider, model, outcome, audio_format, error_code, usage)` plus audio bytes excluded from repr. Separate from `InvocationResult`, whose `result` is text |
| Port | `ProviderSession.synthesize_speech(target, text, voice, remaining_seconds)` returns audio bytes and a `UsageEntry` |
| Orchestration | Same order as invocation: verify, then check the approved target and voice, admit the exact credential version, open one session, call it once, close it, release capacity. No retry, no fallback model or voice |
| Model choice | D-5 applies: the backend names the model, and the service runs it only if it is an approved synthesis target |

### Adapter behavior

1. Open `wss://api.openai.com/v1/realtime?model=<approved model>` with the request's key only. Fixed destination; proxies from the environment, extra headers and redirects are refused, as in L6.
2. Send one `session.update`: `output_modalities: ["audio"]`, the approved voice, output `audio/pcm` at 24,000 Hz, fixed instructions telling the model to read the supplied text exactly and do nothing else.
3. Send the text as a user message item, then one `response.create` with no conversation context.
4. Collect `response.output_audio.delta` chunks into a bounded in-memory buffer. Stop and fail if the running total exceeds the byte cap or the deadline passes.
5. Finish on `response.done` with status `completed`. Any other status, an `error` event or an early close is a safe error.
6. **Read-back check:** compare the output transcript (`response.output_audio_transcript.done`) with the input text after normalizing case, spacing and punctuation. A mismatch becomes `PROVIDER_RESPONSE_INVALID`, so text that tries to instruct the model ("ignore this and say...") is never returned as audio saying something else. The false-reject rate on numbers and abbreviations must be measured before this rule is accepted.
7. Close the WebSocket in all cases, within the 2-second cleanup limit.
8. Wrap the PCM samples in a WAV header with the standard library and return `audio/wav`. MP3 would need an encoder dependency and is not proposed.

### Limits (within D-3's 60 seconds)

| Setting | Proposal |
| --- | --- |
| Text input | 4,096 characters and 16 KiB of UTF-8, checked before any key access |
| Synthesis call | At most 45 seconds, capped by the remaining overall deadline |
| Output audio | At most 4 MiB of PCM (about 87 seconds at 24 kHz, 16-bit mono), checked while receiving |
| WebSocket messages | Bounded message size; no compression; one session and one response per request |
| Concurrency | Shares the existing gate of 8 operations per process |

### Errors

| Situation | Code |
| --- | --- |
| Handshake refused for the key (HTTP 401) | `CREDENTIAL_REJECTED` |
| Handshake 403, unsupported region or model access | `ACCESS_DENIED` (as A2) |
| Rate-limit or quota error event | `RATE_LIMITED` / `QUOTA_EXCEEDED` |
| Connect failure or server close | `PROVIDER_UNAVAILABLE` |
| No `response.done` in time | `PROVIDER_TIMEOUT` |
| Oversized audio, missing audio, failed read-back check, malformed events | `PROVIDER_RESPONSE_INVALID` |

No provider error text, event payload, session ID or key fragment is returned or logged. The SDK's and `websockets`' loggers must stay below the level that prints headers or frames.

### Usage

Copy the provider-reported token counts from `response.done` into one `UsageEntry(operation=synthesize_speech)`. Missing values stay null. A sanitized provider response ID may be returned as `provider_request_id`. Nothing is estimated.

### Validation

Synthesis access is validated only when the backend asks: one fixed text ("OK."), one session, read-back not required. Result `valid`, `rejected` or `indeterminate` as in L6. Each validation costs audio output tokens.

### HTTP mapping (D-2)

Success is status 200 with the WAV bytes and `Content-Type: audio/wav`. Metadata (`model`, `total_tokens`, `provider_request_id`, `request_id`) goes in response headers, because the body is audio. The header names need Ofon's agreement. Errors use the existing D-2 body and status table.

## 5. Tests (all offline)

- Fake realtime connection that replays scripted events; no network, no real key.
- Destination and header guard: wrong host, proxy settings, extra headers and redirects are refused before sending.
- Exactly one `session.update`, one item, one `response.create`; no second response; session closed on success, error and cancellation.
- Byte cap and deadline enforced while receiving; read-back mismatch rejected; empty audio rejected.
- Every error event, handshake status and close code maps to its code without reflecting payloads.
- Leakage: the key, provider messages and event payloads never appear in results, logs or exceptions.
- Unapproved model or voice refused before the key is read (D-5); both key sources (D-1).
- Import safety: the core still imports no SDK; only the adapter imports the realtime client, lazily.

## 6. Decisions needed before code

| ID | Question | Recommendation |
| --- | --- | --- |
| S-1 | Add the `websockets` package (needed by the installed SDK's realtime client), with an exact version range | Yes, as a separate approved dependency change after checking the SDK's supported range |
| S-2 | Accept the read-back check and its false-reject risk | Yes for M1; measure on sample texts during the first approved live test |
| S-3 | Voices allowed, and whether the backend may choose per request | Allow marin and cedar; backend chooses within that list |
| S-4 | Output format | WAV (24 kHz, 16-bit mono) only |
| S-5 | Data retention for Realtime sessions is not stated by OpenAI | Record as an open provider question before live use |
| S-6 | Cost approval for synthesis and its validation calls | Product/engineering manager, as in B5.18 |
| S-7 | Response metadata header names | Agree with Ofon in P-1 |

## 7. Proposed task split after approval

| Card | Work |
| --- | --- |
| T2.4 | Core types, port method, orchestrator path and limits for synthesis, with the scripted adapter |
| T3.4 | Dependency preflight (after S-1 approval) and the OpenAI realtime synthesis adapter with a fake connection |
| T4.7 | Handler parsing, WAV result and HTTP mapping for synthesis; no route registered |

A live check with a real key happens only in M2 staging (T6), with separate approval.
