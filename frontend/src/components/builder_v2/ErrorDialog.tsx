"use client";

import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Sparkles, X, Loader2, Lightbulb } from "lucide-react";
import { v2ExplainError, hasUserAIKey, type V2Graph } from "@/lib/api";

/**
 * Centered, hard-to-miss dialog for backtest / setup errors.
 *
 * Replaces the old tiny red text tucked into the bottom of the right panel.
 * Shows the raw error prominently, then fetches AI-generated, plain-language
 * suggestions for how to fix it. Suggestions are best-effort: if the AI call
 * fails (e.g. no key, rate limit) the dialog still shows the error.
 */
export function ErrorDialog({
  error,
  graph,
  symbol,
  timeframe,
  onClose,
}: {
  error: string;
  graph?: V2Graph | null;
  symbol?: string;
  timeframe?: string;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [requested, setRequested] = useState(false);
  const [explanation, setExplanation] = useState<string>("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [aiError, setAiError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // Suggestions are on-demand: fetched only when the user clicks the button.
  async function loadSuggestions() {
    setLoading(true);
    setRequested(true);
    setExplanation("");
    setSuggestions([]);
    setAiError(null);
    try {
      const res = await v2ExplainError({ error, graph, symbol, timeframe });
      setExplanation(res.explanation || "");
      setSuggestions(res.suggestions || []);
    } catch (e: any) {
      setAiError(
        hasUserAIKey()
          ? (e?.message ?? "Couldn't load suggestions.")
          : "Add an AI key under Resources → AI Model to get smart fix suggestions."
      );
    } finally {
      setLoading(false);
    }
  }

  // Reset suggestion state whenever the underlying error changes.
  useEffect(() => {
    setLoading(false);
    setRequested(false);
    setExplanation("");
    setSuggestions([]);
    setAiError(null);
  }, [error]);

  // Focus the close button and wire Escape-to-close.
  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Backtest error"
    >
      <div
        className="bg-cream2 border border-border rounded-2xl shadow-2xl w-full max-w-md overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start gap-3 px-6 pt-5 pb-4 border-b border-border">
          <div className="shrink-0 mt-0.5 h-9 w-9 rounded-full bg-terra/10 flex items-center justify-center">
            <AlertTriangle className="h-5 w-5 text-terra" />
          </div>
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-[15px] text-ink">Something needs attention</h3>
            <p className="text-xs text-muted mt-0.5">Here's what went wrong and how to fix it.</p>
          </div>
          <button
            ref={closeRef}
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 -mr-1 -mt-1 p-1.5 rounded-lg text-muted hover:text-ink hover:bg-cream3 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Raw error */}
          <div className="rounded-xl border border-terra/30 bg-terra/5 px-3.5 py-3">
            <p className="text-sm text-ink2 break-words whitespace-pre-wrap leading-relaxed">{error}</p>
          </div>

          {/* AI suggestions — on demand */}
          {!requested ? (
            <button
              onClick={() => void loadSuggestions()}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-sage/40 bg-sage/5 text-sm font-medium text-sage hover:bg-sage/10 transition-colors"
            >
              <Sparkles className="h-4 w-4" />
              Get AI suggestions
            </button>
          ) : (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Sparkles className="h-3.5 w-3.5 text-sage" />
                <span className="text-xs font-semibold text-ink uppercase tracking-wide">AI suggestions</span>
              </div>

              {loading ? (
                <div className="flex items-center gap-2 text-sm text-muted py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analyzing the error…
                </div>
              ) : aiError ? (
                <div className="space-y-2">
                  <p className="text-xs text-muted">{aiError}</p>
                  <button
                    onClick={() => void loadSuggestions()}
                    className="text-xs font-medium text-sage hover:text-sageMid transition-colors"
                  >
                    Try again
                  </button>
                </div>
              ) : (
                <div className="space-y-3">
                  {explanation && (
                    <p className="text-sm text-ink2 leading-relaxed">{explanation}</p>
                  )}
                  {suggestions.length > 0 && (
                    <ul className="space-y-2">
                      {suggestions.map((s, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-ink2">
                          <Lightbulb className="h-4 w-4 text-amber shrink-0 mt-0.5" />
                          <span className="leading-relaxed">{s}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  {!explanation && suggestions.length === 0 && (
                    <p className="text-xs text-muted py-1">No suggestions available for this one.</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border flex justify-end">
          <button
            onClick={onClose}
            className="py-2 px-5 rounded-lg bg-sage text-cream2 text-sm font-medium hover:bg-sageMid transition-colors"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  );
}
