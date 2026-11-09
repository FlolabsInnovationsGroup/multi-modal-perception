import type { Intent, PelResult } from "../pel/types";

function stripCodeFences(text: string): string {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)```$/i);
  return fenced ? fenced[1].trim() : trimmed;
}

function isIntent(value: unknown): value is Intent {
  return value === "IR" || value === "AE";
}

export function parsePelResponse(raw: string): PelResult {
  const cleaned = stripCodeFences(raw);
  let parsed: unknown;

  try {
    parsed = JSON.parse(cleaned);
  } catch {
    throw new Error("LLM response was not valid JSON.");
  }

  if (!parsed || typeof parsed !== "object") {
    throw new Error("LLM response must be a JSON object.");
  }

  const obj = parsed as Record<string, unknown>;

  const intentRaw = obj.intent;
  let intent: Intent | null = isIntent(intentRaw) ? intentRaw : null;
  if (!intent && typeof intentRaw === "string") {
    const upper = intentRaw.toUpperCase();
    if (upper.includes("IR") || /information|research|retriev/i.test(intentRaw)) {
      intent = "IR";
    } else if (
      upper.includes("AE") ||
      /action|execution|implement|build/i.test(intentRaw)
    ) {
      intent = "AE";
    }
  }
  if (!intent) {
    throw new Error('LLM response missing valid "intent" (IR or AE).');
  }

  const confidence = Number(obj.confidence);
  if (!Number.isFinite(confidence) || confidence < 0 || confidence > 1) {
    throw new Error('LLM response missing valid "confidence" (0.0–1.0).');
  }

  const enhancedRaw =
    obj.enhanced_prompt ?? obj.enhancedPrompt ?? obj.enhanced ?? obj.prompt;
  if (typeof enhancedRaw !== "string" || !enhancedRaw.trim()) {
    throw new Error('LLM response missing non-empty "enhanced_prompt".');
  }

  const reasoningRaw = obj.reasoning ?? obj.rationale ?? obj.explanation;
  if (typeof reasoningRaw !== "string" || !reasoningRaw.trim()) {
    throw new Error('LLM response missing non-empty "reasoning".');
  }

  return {
    intent,
    confidence: Math.round(confidence * 100) / 100,
    enhanced_prompt: enhancedRaw.trim(),
    reasoning: reasoningRaw.trim(),
  };
}
