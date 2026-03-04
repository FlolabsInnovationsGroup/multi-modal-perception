# Multimodal Perception Microservice
This repository contains the foundational Python microservice for a multimodal perception system. It is built using FastAPI, providing a fast, asynchronous, and robust REST API.

Currently, it acts as a lightweight event-driven service that receives text input and returns an OpenAI-generated text response, using a highly optimized, lightweight client.

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

* **Data Models (``schemas.py``)**: Uses Pydantic to strictly define the expected input and output data (e.g., ``PerceptionInput``, ``PerceptionOutput``). If a system sends malformed data, the API automatically rejects it.

* **The Routers (``api/`` folder)**:

    * ``health.py``: Handles the ``GET /health`` route used by deployment managers (like Docker or Kubernetes) to check if the server is alive.

    * ``process.py``: Handles the ``POST /process`` route. This is the main trigger that accepts the payload, logs the input, and calls the ultra-lightweight OpenAI client to transform the text into a concise perception response.

---

### OpenAI Integration

This microservice now integrates directly with the OpenAI Chat Completions API using an async, cached client optimized for low latency.

- **Async client**: Uses `AsyncOpenAI` for non-blocking calls under FastAPI.
- **Ultra-fast cache**: In-memory cache keyed by normalized user input to avoid redundant calls.
- **Safe defaults**: Conservative `max_tokens`, temperature, and model selection to keep responses fast and predictable.

#### Required Environment Variables

Before starting the server, set at least:

- **`OPENAI_API_KEY`**: Your OpenAI API key.

Optional tuning (all have sensible defaults):

- **`OPENAI_MODEL`**: Defaults to `gpt-4o-mini`.
- **`OPENAI_MAX_TOKENS`**: Defaults to `256`.
- **`OPENAI_TEMPERATURE`**: Defaults to `0.4`.
- **`OPENAI_SYSTEM_PROMPT`**: Custom system prompt for the multimodal perception assistant.

Example (Unix/macOS):

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4o-mini"
```

---

### How to Run the System Locally
1. **Prerequisites**

Ensure you have Python 3.8+ installed. You will also need to install the dependencies. If you haven't already, install them via your terminal:

`pip install fastapi uvicorn pydantic`

2. **Starting the Server**

Since the code includes a Uvicorn execution block at the bottom, you can start the server simply by running the Python file directly:

`python main.py`

(Alternatively, you can start it via the Uvicorn CLI: ``uvicorn main:app --host 0.0.0.0 --port 8000 --reload``)

You should see logs indicating the server has started on http://0.0.0.0:8000.

----

### How to Test the API
Once the server is running, you can interact with it using several methods.

**Method A: Interactive API Docs (Recommended)**

FastAPI automatically generates a beautiful, interactive user interface for testing.

1. Open your web browser.

2. Navigate to: http://localhost:8000/docs

3. Expand the POST /process route, click "Try it out", modify the text, and hit Execute.

**Method B: Terminal (cURL)**

You can trigger the system directly from a new terminal window to simulate how your Django backend will communicate with it.

**Test the Health Check:**

``curl -X GET http://localhost:8000/health``

Expected Output: ``{"status":"healthy"}``

**Test the Main Trigger:**

    curl -X POST http://localhost:8000/process \
         -H "Content-Type: application/json" \
         -d '{"text_input": "What is OpenAI?"}'

Expected Output: OpenAI chat response. 