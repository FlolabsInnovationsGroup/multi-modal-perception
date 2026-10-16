import { readFileSync } from "node:fs";

const raw = readFileSync(".env", "utf8");
const line = raw.split(/\r?\n/).find((l) => l.startsWith("GROQ_API_KEY="));
const bytes = Buffer.from(line ?? "", "utf8");

console.log("byte_length:", bytes.length);
for (let i = 0; i < Math.min(bytes.length, 80); i++) {
  const b = bytes[i];
  if (b < 32 || b > 126) {
    console.log(`offset ${i}: non-ascii 0x${b.toString(16)}`);
  }
}
