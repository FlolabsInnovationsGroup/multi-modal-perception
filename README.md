# Multi-Modal Perception

Python microservice that will serve as the foundation for a **multimodal perception system** (vision, language, dialogue). The service is built as a single, loosely coupled application suitable for later deployment as part of a larger suite of services.

Currently, it also acts as a lightweight event-driven service that receives text plus an audio file and returns an OpenAI-generated text response, using a highly optimized, lightweight client.

### Project Architecture

        .
        ├── api/
        │   ├── __init__.py      # Marks the directory as a Python package
        │   ├── health.py        # Contains system health check routes
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

---

### OpenAI Integration

This microservice integrates directly with the OpenAI Chat Completions API using an async, cached client optimized for low latency.

- **Async client**: Uses `AsyncOpenAI` for non-blocking calls under FastAPI.
- **Ultra-fast cache**: In-memory cache keyed by normalized user input to avoid redundant calls.
- **Safe defaults**: Conservative `max_tokens`, temperature, and model selection to keep responses fast and predictable.

#### Required Environment Variables

Before starting the server, set at least:

- **`OPENAI_API_KEY`**: Your OpenAI API key.

Optional tuning (all have sensible defaults):

- **`OPENAI_MODEL`**: Defaults to `gpt-4o-mini`.
- **`OPENAI_TRANSCRIBE_MODEL`**: Defaults to `gpt-4o-mini-transcribe`.
- **`OPENAI_MAX_TOKENS`**: Defaults to `256`.
- **`OPENAI_TEMPERATURE`**: Defaults to `0.4`.
- **`OPENAI_SYSTEM_PROMPT`**: Custom system prompt for the multimodal perception assistant.

Example (Unix/macOS):

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

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
| `api/`                | API module: `health.py` (GET /health), `process.py` (POST /process). Keeps routes modular and testable. |
| `schemas.py`          | Pydantic models for typed API structures (currently used for response validation via `PerceptionOutput`). |
| `requirements.txt`    | Pinned dependencies (FastAPI, Uvicorn, Pydantic) for reproducible installs. |
| `POST /process`       | Main trigger: accepts `multipart/form-data` with `text_input` and `audio_file`, returns JSON with `result` (OpenAI response or stub). |
| `GET /health`         | Health check for load balancers and orchestrators (e.g. Docker/Kubernetes). |

### API behavior (current)

1. **Health:** `GET /health` → `{"status": "healthy"}`.
2. **Process:** `POST /process` with `multipart/form-data` fields `text_input` and `audio_file` → audio is transcribed first, then `{"result": "<OpenAI response>"}`.  
   Any unhandled exception in the handler returns HTTP 500 with a generic error message; logs contain the real error for debugging.

### Logging

- Standard library `logging` is configured at INFO in `main.py`.

### Dataset (separate)

- The **Caipo Multimodal Dataset** lives under `caipo_multimodal_dataset/` and is used for training/evaluation of future models (e.g. vLLM).  
- See [`caipo_multimodal_dataset/README.md`](caipo_multimodal_dataset/README.md) for structure, tasks, and usage.  
- The microservice does not depend on the dataset at runtime; the dataset is for offline training and evaluation.

---

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
├── api/                      # API routes (health, process)
│   ├── __init__.py
│   ├── health.py             # GET /health
│   └── process.py            # POST /process
├── services/                 # Service layer (e.g., OpenAI)
│   └── openai_service.py
└── caipo_multimodal_dataset/ # Training/eval dataset (see its README)
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
