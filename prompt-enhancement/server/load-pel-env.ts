import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { loadEnv } from "vite";
import type { PelApiEnv } from "./pel-api";

function parseEnvFile(filePath: string): Record<string, string> {
  if (!existsSync(filePath)) return {};

  const vars: Record<string, string> = {};
  const content = readFileSync(filePath, "utf8");

  for (const line of content.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;

    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();

    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    vars[key] = value;
  }

  return vars;
}

/**
 * Load PEL env vars reliably. Vite's loadEnv is merged, but .env on disk
 * is re-read each call so dev server picks up saves without stale cache.
 */
export function loadPelEnv(root: string, mode: string): PelApiEnv {
  const fromVite = loadEnv(mode, root, "");
  const fromDotEnv = parseEnvFile(resolve(root, ".env"));
  const fromLocal = parseEnvFile(resolve(root, ".env.local"));

  // .env on disk wins over process.env (stale shell exports caused 401s)
  const pick = (key: keyof PelApiEnv) =>
    fromLocal[key] ?? fromDotEnv[key] ?? fromVite[key] ?? process.env[key];

  return {
    GROQ_API_KEY: pick("GROQ_API_KEY"),
    GROQ_MODEL: pick("GROQ_MODEL"),
    GROQ_BASE_URL: pick("GROQ_BASE_URL"),
  };
}
