# Prompt Enhancement Layer (PEL)

A modular, **LLM-powered** prompt-to-program compiler. Classifies prompts as **IR** (Information Retrieval) or **AE** (Action Execution) and returns structured enhanced prompts as JSON.

## Quick start

1. Copy the env template and add your Groq API key:

```bash
cp .env.example .env
# Edit .env — set GROQ_API_KEY=gsk_...
```

2. Install and run:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`. The header shows provider status (Groq + model when configured).

## Architecture

```
src/lib/pel/           # PEL domain
  types.ts             # PelResult, PelEnhancer interfaces
  system-prompt.ts     # PEL instructions (not hardcoded signals)
  service.ts           # PelService factory
  enhancers/
    api-enhancer.ts    # Browser → POST /api/enhance
    llm-enhancer.ts    # Server-side LLM enhancement

src/lib/llm/           # LLM abstraction
  types.ts             # LLMProvider interface
  providers/groq.ts    # Groq OpenAI-compatible client
  parse-pel-response.ts

server/                # Dev/preview API (keeps API key server-side)
  pel-api.ts           # /api/enhance, /api/health
  vite-pel-plugin.ts   # Vite middleware plugin
```

### Modular extension

Swap providers or enhancers without touching the UI:

```ts
import { createGroqProvider } from "./lib/llm/providers/groq";
import { createLlmPelEnhancer } from "./lib/pel/enhancers/llm-enhancer";
import { createPelService } from "./lib/pel/service";

const service = createPelService({
  enhancer: createLlmPelEnhancer({
    provider: createGroqProvider({ apiKey: "..." }),
  }),
});
```

Add a new LLM by implementing `LLMProvider` in `src/lib/llm/types.ts`.

## Environment variables

| Variable        | Required | Description                          |
|-----------------|----------|--------------------------------------|
| `GROQ_API_KEY`  | Yes      | Groq API key from [console.groq.com](https://console.groq.com/) |
| `GROQ_MODEL`    | No       | Default: `llama-3.3-70b-versatile`   |
| `GROQ_BASE_URL` | No       | Default: Groq OpenAI-compatible URL  |

The API key is **never** sent to the browser — only the Vite dev/preview server calls Groq.

### Troubleshooting 401 Invalid API Key

1. Verify the key file: `npm run check:env` (should show `groq_status: 200` and `key_length: 50+`).
2. **Clear a stale shell variable** (overrides `.env` on Windows):
   ```powershell
   Remove-Item Env:GROQ_API_KEY -ErrorAction SilentlyContinue
   ```
3. Stop **all** running dev servers (Ctrl+C in every terminal), then `npm run dev` once.
4. Open the **exact URL** printed in the terminal (e.g. `http://localhost:5174/`), not an old tab on another port.
5. Header should show `key ok (56)` when the server loaded your key correctly.

## API endpoints (dev server)

| Method | Path           | Description                    |
|--------|----------------|--------------------------------|
| GET    | `/api/health`  | Provider readiness + model   |
| POST   | `/api/enhance` | Body: `{ "prompt": "..." }`    |

## Scripts

| Command           | Description              |
|-------------------|--------------------------|
| `npm run dev`     | Dev server + API         |
| `npm run build`   | Production static build  |
| `npm run preview` | Preview build + API      |

## Output format

```json
{
  "intent": "IR",
  "confidence": 0.85,
  "enhanced_prompt": "...",
  "reasoning": "..."
}
```
