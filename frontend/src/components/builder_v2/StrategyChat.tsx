"use client";

/**
 * Conversational AI strategy builder.
 *
 * Non-technical users describe their idea in plain English. The AI asks
 * clarifying questions (one at a time) until it understands the strategy,
 * then builds the graph and lets the user load it onto the canvas.
 */
import { useEffect, useRef, useState } from "react";
import {
  v2Chat, hasUserAIKey, getAIProvider, getAIModel, setAIModel, AI_MODEL_OPTIONS,
  type ChatMessage, type V2Graph,
} from "@/lib/api";
import Link from "next/link";


export function StrategyChat({
  open,
  onClose,
  onLoadGraph,
  symbol = "XAUUSD",
  timeframe = "M15",
  currentGraph = null,
  resultSummary = null,
}: {
  open:        boolean;
  onClose:     () => void;
  onLoadGraph: (g: V2Graph, name: string) => void;
  symbol?:     string;
  timeframe?:  string;
  /** When set, the chat edits this existing strategy instead of starting fresh. */
  currentGraph?:  V2Graph | null;
  /** Short summary of the strategy's last backtest, e.g. "0 trades". */
  resultSummary?: string | null;
}) {
  const editing = !!(currentGraph && currentGraph.nodes && currentGraph.nodes.length > 0);
  const [messages,  setMessages]  = useState<ChatMessage[]>([]);
  const [input,     setInput]     = useState("");
  const [busy,      setBusy]      = useState(false);
  const [graph,     setGraph]     = useState<V2Graph | null>(null);
  const [err,       setErr]       = useState<string | null>(null);
  const [hasKey,    setHasKey]    = useState(false);
  const [provider,  setProvider]  = useState("gemini");
  const [model,     setModel]     = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setHasKey(hasUserAIKey());
      setProvider(getAIProvider());
      setModel(getAIModel());
      // Start the conversation with a greeting from the AI if empty
      if (messages.length === 0) {
        setMessages([{
          role:    "assistant",
          content: editing
            ? `I can see your current strategy${resultSummary ? ` (last backtest: ${resultSummary})` : ""}. Tell me what to change — e.g. "loosen it so it actually trades", "remove the AND condition", or "add a trend filter" — and I'll update it.`
            : "Hey! Tell me about your trading idea in plain English — no jargon needed. For example: \"I want to buy gold when it breaks above a recent high and sell when it drops back below.\" What's your idea?",
        }]);
      }
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function reset() {
    setMessages([]);
    setInput("");
    setGraph(null);
    setErr(null);
  }

  function close() {
    reset();
    onClose();
  }

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setErr(null);
    setInput("");

    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setBusy(true);

    try {
      const res = await v2Chat({
        messages: next, symbol, timeframe,
        current_graph:  editing ? currentGraph : null,
        result_summary: editing ? resultSummary : null,
      });
      if (res.type === "graph") {
        setGraph(res.graph);
        setMessages((m) => [
          ...m,
          {
            role:    "assistant",
            content: `I've built your strategy: **${res.graph.name || "Custom strategy"}** (${res.graph.nodes.length} nodes). Review it below and click "Load onto canvas" when you're happy.`,
          },
        ]);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.content }]);
      }
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function loadGraph() {
    if (!graph) return;
    onLoadGraph(graph, graph.name || "AI Strategy");
    close();
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-paper/95 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl shadow-float w-full max-w-2xl flex flex-col"
           style={{ height: "min(700px, 90vh)" }}>

        {/* Header */}
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3 shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-0.5">
              <span className="text-[10px] uppercase tracking-widest text-money font-semibold">AI Strategy Builder</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-highlight text-highlightInk font-medium">Beta</span>
            </div>
            <h2 className="text-[17px] font-semibold text-ink">{editing ? "Edit your strategy" : "Describe your strategy"}</h2>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <label className="flex items-center gap-1.5" title="Choose which AI model answers">
              <span className="text-[10px] uppercase tracking-wide text-muted">Model</span>
              <select
                value={model}
                onChange={(e) => { setModel(e.target.value); setAIModel(e.target.value); }}
                className="rounded-lg bg-paper border border-border px-2 py-1 text-[12px] text-ink
                           focus:outline-none focus:ring-1 focus:ring-money max-w-[150px]"
              >
                {(AI_MODEL_OPTIONS[provider] ?? AI_MODEL_OPTIONS.gemini).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
            <button onClick={close} className="text-muted hover:text-ink text-2xl leading-none px-2">×</button>
          </div>
        </div>

        {/* Using the free built-in Claude (no user key set) */}
        {!hasKey && (
          <div className="mx-5 mt-3 shrink-0 rounded-lg border border-sage/30 bg-sage/10 px-3 py-2 text-[12px] text-ink/80">
            Using Edgekit's built-in <strong>Claude</strong> assistant — free, with a daily limit.{" "}
            <Link href="/resources" className="underline font-medium" onClick={close}>
              Add your own AI key
            </Link>{" "}
            for unlimited use.
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              {m.role === "assistant" && (
                <div className="w-7 h-7 rounded-full bg-money/15 flex items-center justify-center text-money text-[13px] shrink-0 mt-0.5 mr-2">
                  E
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed ${
                  m.role === "user"
                    ? "bg-money text-white rounded-br-sm"
                    : "bg-surface2 text-ink rounded-bl-sm border border-border"
                }`}
              >
                {/* Simple markdown bold support */}
                {m.content.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
                  part.startsWith("**") && part.endsWith("**")
                    ? <strong key={j}>{part.slice(2, -2)}</strong>
                    : <span key={j}>{part}</span>
                )}
              </div>
            </div>
          ))}

          {busy && (
            <div className="flex justify-start">
              <div className="w-7 h-7 rounded-full bg-money/15 flex items-center justify-center text-money text-[13px] shrink-0 mt-0.5 mr-2">E</div>
              <div className="bg-surface2 border border-border rounded-2xl rounded-bl-sm px-4 py-3 text-[13.5px] text-muted">
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
              </div>
            </div>
          )}

          {err && (
            <div className="rounded-lg border border-down/40 bg-down/5 px-3 py-2.5 text-[12.5px] text-down">
              {err}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Graph preview bar (when AI has built a graph) */}
        {graph && (
          <div className="mx-5 mb-3 shrink-0 rounded-xl border border-up/30 bg-up/5 px-4 py-3 flex items-center gap-3">
            <div className="flex-1">
              <div className="text-[12px] font-semibold text-ink">{graph.name || "Strategy"}</div>
              <div className="text-[11px] text-muted">{graph.nodes.length} nodes · {graph.edges.length} wires</div>
            </div>
            <button
              onClick={loadGraph}
              className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors shrink-0"
            >
              Load onto canvas →
            </button>
            <button
              onClick={() => setGraph(null)}
              className="text-muted hover:text-ink text-sm px-1"
              title="Discard and keep refining"
            >
              ✕
            </button>
          </div>
        )}

        {/* Input */}
        <div className="px-5 pb-4 shrink-0 border-t border-border pt-3">
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              rows={2}
              placeholder="Type your answer… (Enter to send)"
              disabled={busy}
              className="flex-1 rounded-xl bg-paper border border-border px-3 py-2.5 text-[13.5px] resize-none
                         focus:outline-none focus:ring-1 focus:ring-money disabled:opacity-50 leading-relaxed"
            />
            <button
              onClick={send}
              disabled={!input.trim() || busy}
              className="px-4 py-2.5 rounded-xl bg-money text-white text-[13px] font-medium
                         hover:bg-moneyDark transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              Send
            </button>
          </div>
          <p className="text-[10.5px] text-muted mt-1.5">
            Shift+Enter for new line · Enter to send · The AI will ask questions until it understands your strategy
          </p>
        </div>
      </div>
    </div>
  );
}
