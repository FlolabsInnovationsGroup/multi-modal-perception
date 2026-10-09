import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = process.cwd();
const envPath = resolve(root, ".env");
const raw = readFileSync(envPath, "utf8");
const line = raw.split(/\r?\n/).find((l) => l.startsWith("GROQ_API_KEY="));

if (!line) {
  console.log("GROQ_API_KEY line not found in .env");
  process.exit(1);
}

const key = line.replace(/^GROQ_API_KEY=/, "").trim().replace(/^["']|["']$/g, "");

console.log("key_length:", key.length);
console.log("starts_with_gsk:", /^gsk_/.test(key));
console.log(
  "looks_complete:",
  key.length >= 40,
  "(Groq keys are usually 50+ chars)"
);

const res = await fetch("https://api.groq.com/openai/v1/models", {
  headers: { Authorization: `Bearer ${key}` },
});
const body = await res.json().catch(() => ({}));

console.log("groq_status:", res.status);
console.log("groq_code:", body?.error?.code ?? "ok");

if (res.ok) {
  console.log("\n.env key is valid. Restart dev server: npm run dev");
  console.log("Then open the URL shown in the terminal (not an old tab).");
}
