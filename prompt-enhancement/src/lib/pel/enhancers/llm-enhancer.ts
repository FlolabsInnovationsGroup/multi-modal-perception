import type { LLMProvider } from "../../llm/types";
import { parsePelResponse } from "../../llm/parse-pel-response";
import { PEL_SYSTEM_PROMPT } from "../system-prompt";
import type { PelEnhancer, PelResult } from "../types";

export interface LlmPelEnhancerConfig {
  provider: LLMProvider;
  model?: string;
}

export function createLlmPelEnhancer(
  config: LlmPelEnhancerConfig
): PelEnhancer {
  const { provider, model } = config;

  return {
    id: `pel-llm-${provider.id}`,
    label: `PEL (${provider.label})`,

    async enhance(prompt: string): Promise<PelResult> {
      const trimmed = prompt.trim();
      if (!trimmed) {
        throw new Error("Prompt cannot be empty.");
      }

      const completion = await provider.complete(
        [
          { role: "system", content: PEL_SYSTEM_PROMPT },
          {
            role: "user",
            content: `Return valid JSON only (fields: intent, confidence, enhanced_prompt, reasoning). Enhance this user prompt:\n\n${trimmed}`,
          },
        ],
        { model, temperature: 0.2, maxTokens: 2048, jsonMode: true }
      );

      return parsePelResponse(completion.content);
    },
  };
}
