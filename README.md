# Multi-Modal Perception

Python microservice that serves as the prototype foundation for a **multimodal perception system** (vision, language, dialogue).

The current implementation accepts text and/or audio and can return an OpenAI-generated response. It is a legacy single-tenant prototype, not a production-ready Bring Your Own Key (BYOK) service.

## BYOK security modernization

This branch contains the approved product requirements and the governed delivery package for adding workspace-scoped customer and platform AI-provider credentials. Start with:

1. [`AGENTS.md`](AGENTS.md) — repository workflow, security rules, and approval gates.
2. [`docs/README.md`](docs/README.md) — document index and source-of-truth hierarchy.
3. [`docs/byok-credential-broker-prd.md`](docs/byok-credential-broker-prd.md) — authoritative product and security requirements.
4. [`docs/PLAN.md`](docs/PLAN.md) — active phase, task IDs, entry/exit criteria, and status.
5. [`docs/ai/implementation-start-prompt.md`](docs/ai/implementation-start-prompt.md) — reusable Codex/Claude kickoff prompt.

The target architecture has **not** been implemented yet. Phase 0 security and architecture documents are ready for human review, and feature coding must not begin until the Phase 0 exit gate is explicitly approved.

### Known legacy limitations

- `/process` and `/openAI` are unauthenticated and have no organization/workspace authorization.
- One process-global OpenAI credential/client is used for all requests.
- A cross-request in-memory response cache has no tenant boundary.
- Provider failures can be converted into a silent input-echo response.
- There is no PostgreSQL tenancy model, audit persistence, migration framework, Terraform, automated test suite, or deployment foundation in this repository.

Do not extend these patterns. The approved replacement uses Cognito, PostgreSQL with row-level security, a private ECS Credential Broker, AWS Secrets Manager/KMS, explicit provider/model/credential-source policy, safe auditing, and no silent fallback.

### Project Architecture

        .
        ├── api/
        │   ├── __init__.py      # Marks the directory as a Python package
        │   ├── health.py        # Contains system health check routes
        │   ├── openAI.py        # Contains POST /openAI (OpenAI-backed responses)
        │   └── process.py       # Contains the main perception trigger routes
        ├── main.py              # The central application orchestrator
        ├── schemas.py           # The single source of truth for data structures
        ├── services/            # Service layer (e.g., OpenAI integration)
        │   └── openai_service.py
        └── requirements.txt     # Project dependencies

### How the Code Works
The system is broken down into specific functional areas:

* **The Orchestrator (``main.py``)**: The entry point of the application. It initializes the FastAPI framework and "mounts" the individual routers from the ``api/`` folder. It does not handle business logic directly.

* **Data Models (``schemas.py``)**: Uses Pydantic to define typed response data (e.g. ``PerceptionOutput``) and maintain reusable schema definitions as the API evolves.

* **The Routers (``api/`` folder)**:

    * ``health.py``: Handles the ``GET /health`` route used by deployment managers (like Docker or Kubernetes) to check if the server is alive.

    * ``process.py``: Handles the ``POST /process`` route. This is the main trigger that accepts a multipart payload (text + audio file), transcribes the audio with OpenAI, and returns a concise perception response.

    * ``openAI.py``: Handles the ``POST /openAI`` route. Same multipart contract as ``/process`` (optional ``text_input`` and ``audio_file``; at least one required): uses OpenAI to generate a text response and returns ``PerceptionOutput``.

---

### OpenAI Integration

The legacy prototype integrates directly with the OpenAI Chat Completions API using an async process-global client. This section documents current behavior for local diagnosis and migration; it is not the approved BYOK architecture.

- **Async client**: Uses `AsyncOpenAI` for non-blocking calls under FastAPI.
- **Legacy response cache**: An in-memory cache is keyed by normalized input. It is cross-tenant unsafe and must be removed from provider execution during Phase 4.
- **Legacy error fallback**: Broad provider failures can echo user input. It must be replaced with normalized safe errors and must never trigger credential/provider fallback.
- **Configuration defaults**: Token, temperature, and model defaults affect behavior and cost but are not security or tenant-isolation controls.

#### Required Environment Variables

For local legacy-prototype use only, the process expects:

- **`OPENAI_API_KEY`**: A local development key. Never commit it, paste it into AI/chat, put it in command history, or use a production/customer key. The target BYOK flow will not use this global application pattern.

Optional tuning (all have sensible defaults):

- **`OPENAI_MODEL`**: Defaults to `gpt-4o-mini`.
- **`OPENAI_TRANSCRIBE_MODEL`**: Defaults to `gpt-4o-mini-transcribe`.
- **`OPENAI_MAX_TOKENS`**: Defaults to `256`.
- **`OPENAI_TEMPERATURE`**: Defaults to `0.4`.
- **`OPENAI_SYSTEM_PROMPT`**: Custom system prompt for the multimodal perception assistant.

Example (Unix/macOS):

```bash
export OPENAI_API_KEY="test-provider-key-redacted"
export OPENAI_MODEL="gpt-4o-mini"
```

Use this synthetic placeholder only to understand the variable shape. Do not place a real key directly in a shell command; follow the approved local secret-input method once the development environment policy is defined.

---

## How It's Built

### Architecture

- **Framework:** FastAPI for HTTP API, request/response validation, and async handling.
- **Validation:** Pydantic models for typed input and output so the API contract stays clear as the system grows (e.g. adding images or multimodal payloads).
- **Server:** Uvicorn runs the app; it can be started from the command line or by another process (e.g. Docker/Kubernetes).

### Main components

| File / concept        | Role |
|-----------------------|------|
| `main.py`             | Application entry: FastAPI app, router registration, logging, and `uvicorn.run` when executed directly. |
| `api/`                | API module: `health.py` (GET /health), `process.py` (POST /process), `openAI.py` (POST /openAI). Keeps routes modular and testable. |
| `schemas.py`          | Pydantic models for typed API structures (currently used for response validation via `PerceptionOutput`). |
| `requirements.txt`    | Pinned dependencies (FastAPI, Uvicorn, Pydantic) for reproducible installs. |
| `POST /process`       | Main trigger: accepts `multipart/form-data` with `text_input` and `audio_file`, returns JSON with `result` (OpenAI response or stub). |
| `POST /openAI`        | OpenAI route: same multipart fields as `/process`; returns `{"result": "<OpenAI response>"}`. |
| `GET /health`         | Health check for load balancers and orchestrators (e.g. Docker/Kubernetes). |

### API behavior (current)

1. **Health:** `GET /health` → `{"status": "healthy"}`.
2. **Process:** `POST /process` with `multipart/form-data` fields `text_input` and `audio_file` → audio is transcribed first, then `{"result": "<OpenAI response>"}`.  
   Any unhandled exception in the handler returns HTTP 500 with a generic error message; logs contain the real error for debugging.
3. **OpenAI:** `POST /openAI` with the same `multipart/form-data` shape (`text_input` and/or `audio_file`; at least one required) → `{"result": "<OpenAI response>"}`. Missing both fields returns HTTP 422.

### Logging

- Standard library `logging` is configured at INFO in `main.py`.

## How to Run

### 1. Install dependencies

The project uses **one `requirements.txt`** and **one `.venv`** at the **repository root** (where `main.py` is).

```bash
# From repo root
pip install -r requirements.txt
```

Using a virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Start the service

**Option A — Run `main.py` directly (development, with auto-reload):**

```bash
python main.py
```

This runs Uvicorn with `reload=True` on `http://0.0.0.0:8000`.

**Option B — Run Uvicorn from the command line:**

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Call the API

- **Health check:**
  ```bash
  curl http://localhost:8000/health
  ```
  Expected: `{"status":"healthy"}`

- **Process (main trigger):**
  ```bash
  curl -X POST http://localhost:8000/process \
    -F "text_input=from curl" \
    -F "audio_file=@/absolute/path/to/sample.wav"
  ```
  Expected: `{"result":"Hello world from curl"}` (stub) or with OpenAI: `{"result":"<model response>"}`.

  Example with a question:
  ```bash
  curl -X POST http://localhost:8000/process \
       -F "text_input=What is OpenAI?" \
       -F "audio_file=@/absolute/path/to/sample.wav"
  ```
  Expected output: OpenAI chat response.

- **OpenAI (`POST /openAI`):**  
  Text only:
  ```bash
  curl -X POST http://localhost:8000/openAI \
    -F "text_input=what is the best destination to travel to in the winter?"
  ```
  With audio (same pattern as `/process`):
  ```bash
  curl -X POST http://localhost:8000/openAI \
    -F "text_input=from curl" \
    -F "audio_file=@/absolute/path/to/sample.wav"
  ```
  Expected: `{"result":"<model response>"}` (same `PerceptionOutput` shape as `/process`).

- **Interactive API docs:**  
  Open in a browser: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI).

---

## Repository layout (relevant to the microservice)

```
multi-modal-perception/
├── README.md                 # This file — project overview and run instructions
├── main.py                   # FastAPI app entry, router registration
├── schemas.py                # Pydantic models (PerceptionInput, PerceptionOutput)
├── requirements.txt          # fastapi, uvicorn, pydantic (pinned versions)
├── api/                      # API routes (health, process, openAI)
│   ├── __init__.py
│   ├── health.py             # GET /health
│   ├── openAI.py             # POST /openAI
│   └── process.py            # POST /process
└── services/                 # Service layer (e.g., OpenAI)
    └── openai_service.py
```

---

## Future work (placeholders in code)

- **vLLM / model integration:** The main processing logic can be extended in `api/process.py` (e.g. swap or complement the OpenAI client with vLLM).
- **Multimodal input/output:** When adding images or other modalities, extend the Pydantic models in `schemas.py` (e.g. optional `image_url` or `image_b64`) and the `/process` handler in `api/process.py` accordingly; the same endpoint can be extended or new endpoints can be added.

---

## Dependencies (from requirements.txt)

- **fastapi** — Web framework and API definitions.
- **uvicorn** — ASGI server that runs the FastAPI app.
- **pydantic** — Data validation and serialization for request/response bodies.
- **openai** — OpenAI API client for chat completions.
- **python-dotenv** — Load environment variables from `.env`.

All versions are pinned in `requirements.txt` for reproducible builds.
