# Multi-Modal Perception

Python microservice that will serve as the foundation for a **multimodal perception system** (vision, language, dialogue). The service is built as a single, loosely coupled application suitable for later deployment as part of a larger suite of services.

The service routes text and image requests to MiniCPM-V-4.6 and audio through a self-hosted Whisper transcription endpoint before response generation. The `/openAI` compatibility endpoint remains available for OpenAI text responses.

### Project Architecture

        .
        ├── api/
        │   ├── __init__.py      # Marks the directory as a Python package
        │   ├── health.py        # Contains system health check routes
        │   ├── openAI.py        # Contains POST /openAI (OpenAI-backed responses)
        │   ├── process.py       # Contains the main perception trigger routes
        │   └── speech.py        # Contains POST /transcribe
        ├── main.py              # The central application orchestrator
        ├── schemas.py           # The single source of truth for data structures
        ├── services/            # OpenAI, MiniCPM, and Whisper clients
        │   ├── openai_service.py
        │   ├── minicpm_service.py
        │   └── whisper_service.py
        └── requirements.txt     # Project dependencies

### How the Code Works
The system is broken down into specific functional areas:

* **The Orchestrator (``main.py``)**: The entry point of the application. It initializes the FastAPI framework and "mounts" the individual routers from the ``api/`` folder. It does not handle business logic directly.

* **Data Models (``schemas.py``)**: Uses Pydantic to define typed response data (e.g. ``PerceptionOutput``) and maintain reusable schema definitions as the API evolves.

* **The Routers (``api/`` folder)**:

    * ``health.py``: Handles the ``GET /health`` route used by deployment managers (like Docker or Kubernetes) to check if the server is alive.

    * ``process.py``: Handles ``POST /process`` for text, image, and audio inputs. Audio is transcribed by the self-hosted Whisper service; MiniCPM-V-4.6 generates the response.

    * ``openAI.py``: Handles ``POST /openAI`` with optional ``text_input`` and ``audio_file`` fields; it uses Whisper for audio transcription and OpenAI for response generation.

    * ``speech.py``: Handles ``POST /transcribe`` and returns the transcript from the self-hosted Whisper service.

---

### OpenAI Integration

The `/openAI` compatibility endpoint integrates with the OpenAI Chat Completions API using an async, cached client.

- **Async client**: Uses `AsyncOpenAI` for non-blocking calls under FastAPI.
- **Ultra-fast cache**: In-memory cache keyed by normalized user input to avoid redundant calls.
- **Safe defaults**: Conservative `max_tokens`, temperature, and model selection to keep responses fast and predictable.

#### Required Environment Variables

Set these variables for the corresponding routes:

- **`MINICPM_API_URL`**: Base URL of the MiniCPM/Whisper GPU service. It must expose `POST /v1/generate` and `POST /v1/transcribe`.
- **`OPENAI_API_KEY`**: Required only for the `/openAI` endpoint.

Optional tuning (all have sensible defaults):

- **`OPENAI_MODEL`**: Defaults to `gpt-4o-mini`.
- **`MINICPM_MODEL`**: Defaults to `openbmb/MiniCPM-V-4.6`.
- **`OPENAI_MAX_TOKENS`**: Defaults to `256`.
- **`OPENAI_TEMPERATURE`**: Defaults to `0.4`.
- **`OPENAI_SYSTEM_PROMPT`**: Custom system prompt for the multimodal perception assistant.

Example (PowerShell):

```powershell
$env:MINICPM_API_URL = "http://localhost:6007"
$env:OPENAI_API_KEY = "<set-through-a-secret-manager>"
```

### Selected models

- **TL-approved: MiniCPM-V-4.6** handles text and image understanding. It matches the team's tested turn-based vision baseline and is released under Apache-2.0.
- **Self-hosted Whisper (`small` by default)** transcribes uploaded audio on the GPU service. This reuses the team's existing audio pipeline and avoids depending on a hosted transcription model scheduled for shutdown. OpenAI's API model `whisper-1` is also deprecated, so the service does not use it.
- This is a turn-based image/text/audio pipeline, not a full-duplex speech system.

The MiniCPM model card is available at [Hugging Face](https://huggingface.co/openbmb/MiniCPM-V-4.6). Whisper's self-hosted implementation is [MIT-licensed](https://github.com/openai/whisper/blob/main/LICENSE). OpenAI's [deprecations page](https://developers.openai.com/api/docs/deprecations) lists `gpt-4o-mini-transcribe` and hosted `whisper-1` for shutdown on February 26, 2027.

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
| `api/`                  | API module: `health.py` (GET /health), `process.py` (POST /process), `speech.py` (POST /transcribe), and `openAI.py` (POST /openAI). Keeps routes modular and testable. |
| `schemas.py`          | Pydantic models for typed API structures (currently used for response validation via `PerceptionOutput`). |
| `requirements.txt`    | Pinned dependencies (FastAPI, Uvicorn, Pydantic) for reproducible installs. |
| `POST /process`       | Main multimodal trigger: accepts optional `text_input`, `audio_file`, and `image_file`; uses Whisper for audio transcription and MiniCPM-V-4.6 for responses. |
| `POST /transcribe`    | Accepts `multipart/form-data` with `audio_file`; returns the Whisper transcript and model name. |
| `POST /openAI`        | OpenAI-compatible route: accepts optional `text_input` and `audio_file`; returns `PerceptionOutput`. |
| `GET /health`         | Health check for load balancers and orchestrators (e.g. Docker/Kubernetes). |

### API behavior (current)

1. **Health:** `GET /health` → `{"status": "healthy"}`.
2. **Process:** `POST /process` accepts any non-empty combination of `text_input`, `audio_file`, and `image_file`. Audio is transcribed by the Whisper service and MiniCPM-V-4.6 generates the response. `MINICPM_API_URL` must be configured.
3. **Transcribe:** `POST /transcribe` accepts `audio_file` and returns `{"transcript": "...", "model": "..."}`.
4. **OpenAI:** `POST /openAI` keeps the existing `text_input` and `audio_file` multipart contract. Audio uses the self-hosted Whisper service; text response generation uses OpenAI.

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

- **Process (text + image + audio):**
  ```powershell
  curl.exe -X POST http://localhost:8000/process `
    -F "text_input=What is happening in this scene?" `
    -F "image_file=@C:\path\to\image.jpg" `
    -F "audio_file=@C:\path\to\question.wav"
  ```

- **Transcribe audio:**
  ```powershell
  curl.exe -X POST http://localhost:8000/transcribe `
    -F "audio_file=@C:\path\to\question.wav"
  ```

- **Process (main trigger):**
  ```bash
  curl -X POST http://localhost:8000/process \
    -F "text_input=What is happening in this scene?" \
    -F "image_file=@/absolute/path/to/image.jpg" \
    -F "audio_file=@/absolute/path/to/question.wav"
  ```
  Expected: `{"result":"<MiniCPM response>","model":"openbmb/MiniCPM-V-4.6","file_type":"image"}`.

- **Transcribe audio:**
  ```bash
  curl -X POST http://localhost:8000/transcribe \
    -F "audio_file=@/absolute/path/to/question.wav"
  ```
  Expected: `{"transcript":"<recognized speech>","model":"small"}`.

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
├── api/                      # API routes (health, process, speech, openAI)
│   ├── __init__.py
│   ├── health.py             # GET /health
│   ├── openAI.py             # POST /openAI
│   └── process.py            # POST /process
│   └── speech.py             # POST /transcribe
├── services/                 # Provider service clients
│   └── openai_service.py
└── caipo_multimodal_dataset/ # Training/eval dataset (see its README)
```

---

## Future work (placeholders in code)

- **Speech synthesis:** Add a TTS provider and `/synthesize` endpoint when a model and service contract are selected.

---

## Dependencies (from requirements.txt)

- **fastapi** — Web framework and API definitions.
- **uvicorn** — ASGI server that runs the FastAPI app.
- **pydantic** — Data validation and serialization for request/response bodies.
- **openai** — OpenAI API client for chat completions.
- **httpx** — asynchronous client for MiniCPM and Whisper GPU service requests.
- **python-dotenv** — Load environment variables from `.env`.

All versions are pinned in `requirements.txt` for reproducible builds.
