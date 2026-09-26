import { useCallback, useEffect, useState } from "react";
import { JsonOutput } from "./components/JsonOutput";
import {
  EXAMPLE_PROMPTS,
  checkPelHealth,
  enhancePrompt,
  type Intent,
  type PelResult,
} from "./lib/pel";

interface HealthStatus {
  ready: boolean;
  provider?: string;
  model?: string;
  keyLength?: number;
  error?: string;
}

function IntentBadge({ intent, confidence }: { intent: Intent; confidence: number }) {
  const isIR = intent === "IR";
  return (
    <div className="flex items-center gap-2">
      <span
        className={`rounded-full px-2.5 py-0.5 text-xs font-semibold tracking-wide ${
          isIR
            ? "bg-[var(--color-ir)]/15 text-[var(--color-ir)]"
            : "bg-[var(--color-ae)]/15 text-[var(--color-ae)]"
        }`}
      >
        {intent}
      </span>
      <span className="text-xs text-[var(--color-muted)]">
        {Math.round(confidence * 100)}% confidence
      </span>
    </div>
  );
}

function ProviderStatus({ health }: { health: HealthStatus | null }) {
  if (!health) {
    return (
      <span className="text-xs text-[var(--color-muted)]">Checking provider…</span>
    );
  }

  if (health.ready) {
    return (
      <span className="text-xs text-[var(--color-ir)]">
        Groq · {health.model ?? "default model"}
        {health.keyLength ? ` · key ok (${health.keyLength})` : ""}
      </span>
    );
  }

    return (
      <span className="text-xs text-[var(--color-ae)]" title={health.error}>
        {health.error ?? "API not ready — check GROQ_API_KEY in .env"}
      </span>
    );
}

export default function App() {
  const [prompt, setPrompt] = useState("");
  const [result, setResult] = useState<PelResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    void checkPelHealth().then(setHealth);
  }, []);

  const handleEnhance = useCallback(async () => {
    setError(null);
    setCopied(false);
    if (!prompt.trim()) {
      setError("Please enter a prompt.");
      setResult(null);
      return;
    }
    if (health && !health.ready) {
      setError(
        health.error ??
          "GROQ_API_KEY is not set. Add it to .env, save, then restart npm run dev and use the URL from the terminal."
      );
      setResult(null);
      return;
    }
    setLoading(true);
    try {
      const enhanced = await enhancePrompt(prompt);
      setResult(enhanced);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : "Enhancement failed.");
    } finally {
      setLoading(false);
    }
  }, [prompt, health]);

  const handleCopy = useCallback(async () => {
    if (!result) return;
    await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [result]);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-8 sm:px-6 lg:px-8">
      <header className="mb-8">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-accent)]/20 text-lg font-bold text-[var(--color-accent)]">
              P
            </div>
            <h1 className="text-2xl font-bold tracking-tight">
              Prompt Enhancement Layer
            </h1>
          </div>
          <ProviderStatus health={health} />
        </div>
        <p className="max-w-2xl text-sm leading-relaxed text-[var(--color-muted)]">
          LLM-powered prompt compiler. Classifies intent as{" "}
          <span className="text-[var(--color-ir)]">IR</span> (research) or{" "}
          <span className="text-[var(--color-ae)]">AE</span> (execution), then
          expands your prompt into a structured task — without answering it
          directly.
        </p>
      </header>

      <div className="grid flex-1 gap-6 lg:grid-cols-2">
        <section className="flex flex-col gap-4">
          <label htmlFor="prompt" className="text-sm font-medium text-[#c5cad6]">
            User prompt
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                void handleEnhance();
              }
            }}
            placeholder="Enter a prompt to enhance…"
            rows={10}
            className="w-full resize-y rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3 text-sm leading-relaxed text-[#e8ecf4] placeholder:text-[var(--color-muted)] focus:border-[var(--color-accent)] focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
          />

          <div className="flex flex-wrap gap-2">
            {EXAMPLE_PROMPTS.map((ex) => (
              <button
                key={ex.label}
                type="button"
                onClick={() => {
                  setPrompt(ex.text);
                  setResult(null);
                  setError(null);
                }}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1.5 text-xs text-[var(--color-muted)] transition hover:border-[var(--color-accent-dim)] hover:text-[#e8ecf4]"
              >
                {ex.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => void handleEnhance()}
            disabled={loading || (health !== null && !health.ready)}
            className="rounded-xl bg-[var(--color-accent)] px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-[#6b9af5] disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Enhancing…" : "Enhance prompt"}
          </button>
          <p className="text-xs text-[var(--color-muted)]">
            Ctrl+Enter to submit · Powered by Groq LLM
          </p>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-[#c5cad6]">Output (JSON)</span>
            <div className="flex items-center gap-3">
              {result && (
                <IntentBadge intent={result.intent} confidence={result.confidence} />
              )}
              {result && (
                <button
                  type="button"
                  onClick={() => void handleCopy()}
                  className="rounded-lg border border-[var(--color-border)] px-3 py-1 text-xs text-[var(--color-muted)] transition hover:text-[#e8ecf4]"
                >
                  {copied ? "Copied!" : "Copy JSON"}
                </button>
              )}
            </div>
          </div>
          <JsonOutput result={result} loading={loading} error={error} />
          {result && (
            <p className="text-xs text-[var(--color-muted)]">{result.reasoning}</p>
          )}
        </section>
      </div>

      <footer className="mt-10 border-t border-[var(--color-border)] pt-6 text-center text-xs text-[var(--color-muted)]">
        IR = expand for knowledge · AE = expand for execution
      </footer>
    </div>
  );
}
