# Multi-Modal Perception

Python microservice that will serve as the foundation for a **multimodal perception system** (vision, language, dialogue). The service is built as a single, loosely coupled application suitable for later deployment as part of a larger suite of services.

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
| `schemas.py`          | Pydantic models: `PerceptionInput` (request body), `PerceptionOutput` (response body). |
| `requirements.txt`    | Pinned dependencies (FastAPI, Uvicorn, Pydantic) for reproducible installs. |
| `POST /process`       | Main trigger: accepts JSON with `text_input`, returns JSON with `result` (e.g. `"Hello world " + text_input`). |
| `GET /health`         | Health check for load balancers and orchestrators (e.g. Docker/Kubernetes). |

### API behavior (current)

1. **Health:** `GET /health` → `{"status": "healthy"}`.
2. **Process:** `POST /process` with body `{"text_input": "your text"}` → `{"result": "Hello world your text"}`.  
   Any unhandled exception in the handler returns HTTP 500 with a generic error message; logs contain the real error for debugging.

### Logging

- Standard library `logging` is configured at INFO in `main.py`.
- Incoming input and processing completion are logged in `api/process.py`; errors are logged before raising the 500 response.

### Dataset (separate)

- The **Caipo Multimodal Dataset** lives under `caipo_multimodal_dataset/` and is used for training/evaluation of future models (e.g. vLLM).  
- See [`caipo_multimodal_dataset/README.md`](caipo_multimodal_dataset/README.md) for structure, tasks, and usage.  
- The microservice does not depend on the dataset at runtime; the dataset is for offline training and evaluation.

---

## How to Run

### 1. Install dependencies

From the **repository root** (where `requirements.txt` and `main.py` are):

```bash
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
    -H "Content-Type: application/json" \
    -d '{"text_input": "from curl"}'
  ```
  Expected: `{"result":"Hello world from curl"}`

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
└── caipo_multimodal_dataset/ # Training/eval dataset (see its README)
```

---

## Future work (placeholders in code)

- **vLLM / model integration:** The main processing logic will go in the `try` block of `process_data` in `api/process.py` (section marked `FUTURE vLLM LOGIC GOES HERE`). The current "Hello world" concatenation is a stub.
- **Multimodal input/output:** When adding images or other modalities, extend the Pydantic models in `schemas.py` (e.g. optional `image_url` or `image_b64`) and the `/process` handler in `api/process.py` accordingly; the same endpoint can be extended or new endpoints can be added.

---

## Dependencies (from requirements.txt)

- **fastapi** — Web framework and API definitions.
- **uvicorn** — ASGI server that runs the FastAPI app.
- **pydantic** — Data validation and serialization for request/response bodies.

All versions are pinned in `requirements.txt` for reproducible builds.
