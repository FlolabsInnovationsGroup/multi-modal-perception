import type { PelEnhancer, PelEnhancerOptions, PelResult } from "../types";

export interface ApiPelEnhancerConfig {
  endpoint?: string;
}

export function createApiPelEnhancer(
  config: ApiPelEnhancerConfig = {}
): PelEnhancer {
  const endpoint = config.endpoint ?? "/api/enhance";

  return {
    id: "pel-api",
    label: "PEL (API)",

    async enhance(
      prompt: string,
      options?: PelEnhancerOptions
    ): Promise<PelResult> {
      const trimmed = prompt.trim();
      if (!trimmed) {
        throw new Error("Prompt cannot be empty.");
      }

      const url = options?.apiUrl ?? endpoint;
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: trimmed }),
        signal: options?.signal,
      });

      const data = (await response.json().catch(() => ({}))) as {
        error?: string;
        result?: PelResult;
      };

      if (!response.ok) {
        throw new Error(data.error ?? `Enhancement failed (${response.status}).`);
      }

      if (!data.result) {
        throw new Error("API returned no result.");
      }

      return data.result;
    },
  };
}
