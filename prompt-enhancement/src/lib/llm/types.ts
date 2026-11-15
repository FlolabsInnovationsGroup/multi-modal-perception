export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ChatCompletionOptions {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  jsonMode?: boolean;
  signal?: AbortSignal;
}

export interface ChatCompletionResult {
  content: string;
  model: string;
}

export interface LLMProvider {
  readonly id: string;
  readonly label: string;
  complete(
    messages: ChatMessage[],
    options?: ChatCompletionOptions
  ): Promise<ChatCompletionResult>;
}

export interface GroqProviderConfig {
  apiKey: string;
  baseUrl?: string;
  defaultModel?: string;
}
