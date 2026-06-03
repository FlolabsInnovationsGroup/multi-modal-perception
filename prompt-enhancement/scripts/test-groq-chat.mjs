import { readFileSync } from "node:fs";

const line = readFileSync(".env", "utf8")
  .split(/\r?\n/)
  .find((l) => l.startsWith("GROQ_API_KEY="));
const key = line.replace(/^GROQ_API_KEY=/, "").trim();

const res = await fetch("https://api.groq.com/openai/v1/chat/completions", {
  method: "POST",
  headers: {
    Authorization: `Bearer ${key}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "llama-3.3-70b-versatile",
    messages: [{ role: "user", content: "Say hi" }],
    max_tokens: 10,
    response_format: { type: "json_object" },
  }),
});

console.log("status", res.status);
const body = await res.text();
console.log(body.slice(0, 400));
