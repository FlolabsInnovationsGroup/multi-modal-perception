import type { IncomingMessage, ServerResponse } from "node:http";
import { createGroqProvider } from "../src/lib/llm/providers/groq";
import { createLlmPelEnhancer } from "../src/lib/pel/enhancers/llm-enhancer";
import type { PelResult } from "../src/lib/pel/types";

export interface PelApiEnv {
  GROQ_API_KEY?: string;
  GROQ_MODEL?: string;
  GROQ_BASE_URL?: string;
}

function readBody(req: IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function sendJson(res: ServerResponse, status: number, body: unknown) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

function normalizeApiKey(raw: string | undefined): string {
  return (raw ?? "").trim().replace(/^["']|["']$/g, "");
}

function validateGroqKey(apiKey: string): string | undefined {
  if (!apiKey) return "GROQ_API_KEY is not set. Add it to .env";
  if (!apiKey.startsWith("gsk_")) {
    return "GROQ_API_KEY should start with gsk_. Copy a fresh key from console.groq.com";
  }
  if (apiKey.length < 40) {
    return `GROQ_API_KEY looks truncated (${apiKey.length} chars). Paste the full key, save .env, and restart the dev server.`;
  }
  return undefined;
}

export function getPelApiStatus(env: PelApiEnv) {
  const apiKey = normalizeApiKey(env.GROQ_API_KEY);
  const keyError = validateGroqKey(apiKey);
  return {
    ready: Boolean(apiKey) && !keyError,
    provider: apiKey && !keyError ? "groq" : undefined,
    model: env.GROQ_MODEL ?? "llama-3.3-70b-versatile",
    keyLength: apiKey.length,
    error: keyError,
  };
}

function createServerEnhancer(env: PelApiEnv) {
  const apiKey = normalizeApiKey(env.GROQ_API_KEY);
  const keyError = validateGroqKey(apiKey);
  if (keyError) {
    throw new Error(keyError);
  }

  const provider = createGroqProvider({
    apiKey,
    baseUrl: env.GROQ_BASE_URL,
    defaultModel: env.GROQ_MODEL,
  });

  return createLlmPelEnhancer({
    provider,
    model: env.GROQ_MODEL,
  });
}

export async function handlePelApiRequest(
  req: IncomingMessage,
  res: ServerResponse,
  env: PelApiEnv
): Promise<boolean> {
  const url = req.url?.split("?")[0];

  if (url === "/api/health" && req.method === "GET") {
    sendJson(res, 200, getPelApiStatus(env));
    return true;
  }

  if (url === "/api/enhance" && req.method === "POST") {
    try {
      const raw = await readBody(req);
      const { prompt } = JSON.parse(raw || "{}") as { prompt?: string };

      if (!prompt?.trim()) {
        sendJson(res, 400, { error: "Missing or empty prompt." });
        return true;
      }

      const enhancer = createServerEnhancer(env);
      const result: PelResult = await enhancer.enhance(prompt);
      sendJson(res, 200, { result });
    } catch (e) {
      const message = e instanceof Error ? e.message : "Enhancement failed.";
      sendJson(res, 500, { error: message });
    }
    return true;
  }

  return false;
}
