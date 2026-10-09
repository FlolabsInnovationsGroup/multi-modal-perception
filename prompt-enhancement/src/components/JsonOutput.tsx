import type { ReactNode } from "react";
import type { PelResult } from "../lib/pel";

interface JsonOutputProps {
  result: PelResult | null;
  loading: boolean;
  error: string | null;
}

function highlightJson(json: string): ReactNode[] {
  const parts: ReactNode[] = [];
  const tokenRegex =
    /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
  let last = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(json)) !== null) {
    if (match.index > last) {
      parts.push(
        <span key={`t-${last}`} className="text-[#c5cad6]">
          {json.slice(last, match.index)}
        </span>
      );
    }
    const [full, str, colon] = match;
    let cls = "text-[#c5cad6]";
    if (str) {
      cls = colon ? "text-[#7ec8e3]" : "text-[#a8d4a0]";
    } else if (/true|false/.test(full)) {
      cls = "text-[#d4a0f0]";
    } else if (full === "null") {
      cls = "text-[#8b95a8]";
    } else {
      cls = "text-[#f0c27a]";
    }
    parts.push(
      <span key={`m-${match.index}`} className={cls}>
        {full}
      </span>
    );
    last = match.index + full.length;
  }
  if (last < json.length) {
    parts.push(
      <span key={`end-${last}`} className="text-[#c5cad6]">
        {json.slice(last)}
      </span>
    );
  }
  return parts;
}

export function JsonOutput({ result, loading, error }: JsonOutputProps) {
  if (loading) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)]">
        <div className="flex flex-col items-center gap-3 text-[var(--color-muted)]">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--color-border)] border-t-[var(--color-accent)]" />
          <span className="text-sm">Enhancing prompt…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-300">
        {error}
      </div>
    );
  }

  if (!result) {
    return (
      <div className="flex h-full min-h-[280px] items-center justify-center rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-panel)]/50 p-6 text-center text-sm text-[var(--color-muted)]">
        Submit a prompt to see enhanced JSON output
      </div>
    );
  }

  const json = JSON.stringify(result, null, 2);

  return (
    <pre className="overflow-auto rounded-xl border border-[var(--color-border)] bg-[#0c0e14] p-4 font-mono text-[13px] leading-relaxed">
      <code>{highlightJson(json)}</code>
    </pre>
  );
}
