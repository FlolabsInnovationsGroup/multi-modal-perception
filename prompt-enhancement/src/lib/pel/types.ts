export type Intent = "IR" | "AE";

export interface PelResult {
  intent: Intent;
  confidence: number;
  enhanced_prompt: string;
  reasoning: string;
}

export interface PelEnhancer {
  readonly id: string;
  readonly label: string;
  enhance(prompt: string, options?: PelEnhancerOptions): Promise<PelResult>;
}

export interface PelEnhancerOptions {
  apiUrl?: string;
  signal?: AbortSignal;
}
