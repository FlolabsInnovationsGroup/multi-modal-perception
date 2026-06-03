import type {
  ChatCompletionOptions,
  ChatCompletionResult,
  ChatMessage,
  GroqProviderConfig,
  LLMProvider,
} from "../types";

const DEFAULT_BASE_URL = "https://api.groq.com/openai/v1";
const DEFAULT_MODEL = "llama-3.3-70b-versatile";

export function createGroqProvider(config: GroqProviderConfig): LLMProvider {
  const baseUrl = config.baseUrl ?? DEFAULT_BASE_URL;
  const defaultModel = config.defaultModel ?? DEFAULT_MODEL;

  return {
    id: "groq",
    label: "Groq",

    async complete(
      messages: ChatMessage[],
      options?: ChatCompletionOptions
    ): Promise<ChatCompletionResult> {
      const model = options?.model ?? defaultModel;

      const response = await fetch(`${baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${config.apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          messages,
          temperature: options?.temperature ?? 0.2,
          max_tokens: options?.maxTokens ?? 2048,
          response_format: options?.jsonMode ? { type: "json_object" } : undefined,
        }),
        signal: options?.signal,
      });

      if (!response.ok) {
        const body = await response.text().catch(() => "");
        throw new Error(
          `Groq API error (${response.status}): ${body || response.statusText}`
        );
      }

      const data = (await response.json()) as {
        choices?: { message?: { content?: string } }[];
        model?: string;
      };

      const content = data.choices?.[0]?.message?.content;
      if (!content?.trim()) {
        throw new Error("Groq returned an empty completion.");
      }

      return { content: content.trim(), model: data.model ?? model };
    },
  };
}
