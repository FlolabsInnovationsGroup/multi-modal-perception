import { createApiPelEnhancer } from "./enhancers/api-enhancer";
import type { PelEnhancer, PelEnhancerOptions, PelResult } from "./types";

export interface PelServiceConfig {
  enhancer?: PelEnhancer;
}

export interface PelService {
  readonly enhancer: PelEnhancer;
  enhance(prompt: string, options?: PelEnhancerOptions): Promise<PelResult>;
}

export function createPelService(config: PelServiceConfig = {}): PelService {
  const enhancer = config.enhancer ?? createApiPelEnhancer();

  return {
    enhancer,
    enhance(prompt, options) {
      return enhancer.enhance(prompt, options);
    },
  };
}
