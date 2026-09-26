export type { Intent, PelEnhancer, PelEnhancerOptions, PelResult } from "./types";
export { PEL_SYSTEM_PROMPT } from "./system-prompt";
export { createLlmPelEnhancer } from "./enhancers/llm-enhancer";
export { createApiPelEnhancer } from "./enhancers/api-enhancer";
export { createPelService, type PelService } from "./service";
export { EXAMPLE_PROMPTS } from "./examples";

import { createPelService } from "./service";

const defaultService = createPelService();

export function enhancePrompt(
  prompt: string,
  options?: import("./types").PelEnhancerOptions
) {
  return defaultService.enhance(prompt, options);
}

export async function checkPelHealth(
  healthUrl = "/api/health"
): Promise<{
    ready: boolean;
    provider?: string;
    model?: string;
    keyLength?: number;
    error?: string;
  }> {
  try {
    const res = await fetch(healthUrl);
    return (await res.json()) as {
      ready: boolean;
      provider?: string;
      model?: string;
      error?: string;
    };
  } catch {
    return { ready: false, error: "Cannot reach API server." };
  }
}
