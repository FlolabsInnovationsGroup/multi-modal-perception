# Multi-Modal Perception

Python/FastAPI multimodal service with text/audio processing and separate MiniCPM evaluation scripts.

## Provider-integration feature

Revision 2 documentation incorporates Indra Araujo's review. The feature will read and validate backend-managed provider credentials and use them for model interaction. FloBrain owns user authentication/authorization, protected storage, and credential lifecycle persistence; this repository does not build that platform.

Start with [AGENTS](AGENTS.md), [CODEX](CODEX.md), the [docs index](docs/README.md), [feature PRD](docs/byok-credential-broker-prd.md), and [plan](docs/PLAN.md). The [Codex kickoff prompt](docs/ai/implementation-start-prompt.md) begins with task discovery and approval.

The revised specification is ready for team review. **Feature code is not implemented.** The actual [backend integration contract](docs/contracts/backend-provider-integration.md) is unresolved. Local mock-based tasks can begin after their review/approval; live credential integration cannot.

## Current implementation — not the target design

| Component | Current behavior |
| --- | --- |
| `main.py` | FastAPI setup; mounts health/process/OpenAI routers |
| `api/health.py` | Health route |
| `api/process.py`, `api/openAI.py` | Multipart text/audio processing, no implemented service authentication |
| `services/openai_service.py` | Process-global AsyncOpenAI client/key, transcription and text generation, prompt-only response cache, echo on generation failure |
| `schemas.py` | Response requires `result`, `model`, and `file_type` |
| `minicpm_test_case/` | Evaluation/test scripts, including image/audio/GPU-related work; not BYOK acceptance coverage |
| `docs/` | Current feature requirements, contracts, plan, tests, review record, and historical references |

Both processing routes accept optional `text_input` and `audio_file`; at least one non-empty input is required. Audio is transcribed before generation. Returned `file_type` is text or audio for these routes; schema enumeration also includes image/video but these routes do not thereby implement those inputs.

Known risks: shared credential-bearing client, cross-request content cache, raw exception logging, unbounded audio read, and successful-looking input echo on provider failure. These must not become the new credential path. No production-ready BYOK or backend-auth integration is claimed.

## Local environment

Use Python 3.11 or 3.12 with the existing requirements. Some dependencies are pinned and others use ranges; do not change them implicitly. Creating environments or installing dependencies requires approval under AGENTS.

After explicit installation approval, normal setup is:

```text
python -m venv .venv
python -m pip install -r requirements.txt
```

Activate the intended environment first; verify the Python executable before installing. The project includes FastAPI, Uvicorn, Pydantic, OpenAI SDK, python-dotenv, python-multipart, and requests. Existing MiniCPM scripts have separate requirements and resource needs; do not install/run them for routine feature tests.

For local inspection in an already approved environment:

```text
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Do not expose the unauthenticated prototype publicly. Processing routes may make external provider calls and incur cost; starting a server or reading this README is not approval to use real credentials.

The legacy service reads `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TRANSCRIBE_MODEL`, `OPENAI_MAX_TOKENS`, `OPENAI_TEMPERATURE`, and `OPENAI_SYSTEM_PROMPT`. Inspect source for current defaults; they are not a current model recommendation. The new feature must not fall back to the legacy environment key.

For new-feature local tests, use synthetic fakes and no real key. Do not paste keys into shell commands, files, CI variables, AI/chat, or fixtures. Staging key delivery awaits the approved backend contract.

## Working with the team

See [CONTRIBUTING](CONTRIBUTING.md), [SECURITY](SECURITY.md), [test plan](docs/testing/provider-integration-test-plan.md), and [Discord announcement](docs/team/discord-announcement.md).

Keep actual code separate from planned behavior. Preserve existing response fields until a compatibility change is agreed. Do not follow the archived full-platform plan or superseded AWS/identity ADRs. No automatic branch merge, commit, push, or deployment is authorized by the documents.
