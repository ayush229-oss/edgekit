"use client";

/**
 * AI-generated Custom Node modal.
 *
 * Flow:
 *   1. User describes the logic they want in plain English.
 *   2. We call /graph/v2/from-text — same endpoint as "Describe strategy" —
 *      and get back a V2 graph that does what was asked.
 *   3. User sees a preview (name, node count, lane breakdown).
 *   4. They can name it, tweak the description, and Save.
 *   5. Saved nodes appear in the palette under "My Custom Nodes" and can be
 *      dropped onto any canvas as a pre-wired sub-graph.
 *
 * Why reuse from-text instead of a custom prompt?
 *   - The endpoint already knows the full node catalog and validates output.
 *   - A "custom node" is logically just a strategy fragment — you might want
 *     a complete mini-strategy (entry + exit), or just an alpha-only block.
 *     from-text covers both since the user description shapes the output.
 *   - One LLM call path to maintain.
 */
import { useState } from "react";
import { v2FromText, type V2Graph } from "@/lib/api";
import { saveCustomNode } from "@/lib/customNodes";


type Phase = "describe" | "generating" | "preview" | "saving";

export function CustomNodeBuilder({
  open,
  onClose,
  symbol,
  timeframe,
  onCreated,
}: {
  open:       boolean;
  onClose:    () => void;
  symbol:     string;
  timeframe:  string;
  onCreated?: (id: string) => void;
}) {
  const [phase,       setPhase]       = useState<Phase>("describe");
  const [description, setDescription] = useState("");
  const [err,         setErr]         = useState<string | null>(null);
  const [graph,       setGraph]       = useState<V2Graph | null>(null);
  const [name,        setName]        = useState("");
  const [nodeNote,    setNodeNote]    = useState("");

  function reset() {
    setPhase("describe");
    setDescription("");
    setErr(null);
    setGraph(null);
    setName("");
    setNodeNote("");
  }

  async function generate() {
    if (!description.trim()) return;
    setErr(null);
    setPhase("generating");
    try {
      const g = await v2FromText({ description, symbol, timeframe });
      setGraph(g);
      setName(g.name || "Custom node");
      setNodeNote(description.trim().slice(0, 140));
      setPhase("preview");
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setPhase("describe");
    }
  }

  function save() {
    if (!graph) return;
    setPhase("saving");
    const cn = saveCustomNode({
      name,
      description: nodeNote,
      graph,
      prompt: description,
    });
    onCreated?.(cn.id);
    reset();
    onClose();
  }

  function close() {
    reset();
    onClose();
  }

  if (!open) return null;

  // ── Quick stats about the generated graph ─────────────────────────────
  const stats = graph
    ? {
        nodes: graph.nodes.length,
        edges: graph.edges.length,
        lanes: Array.from(new Set(graph.nodes.map((n) => n.type.split(".")[0]))),
      }
    : null;

  return (
    <div className="fixed inset-0 z-50 bg-paper/95 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl shadow-float w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-widest text-money font-semibold">AI Generated</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-highlight text-highlightInk font-medium">Beta</span>
            </div>
            <h2 className="text-[18px] font-semibold text-ink">Create a custom node</h2>
            <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
              Describe what you want your node to do. The AI will generate a sub-graph from existing nodes —
              you'll see a preview before saving.
            </p>
          </div>
          <button onClick={close} className="text-muted hover:text-ink text-2xl leading-none px-2">×</button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">

          {phase === "describe" && (
            <>
              <label className="block">
                <span className="text-[12px] text-muted font-medium">What should this node do?</span>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={6}
                  placeholder={'e.g. "Detect a liquidity sweep below the prior 20-bar low, then go long when an engulfing candle closes back above"'}
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2.5 text-[13.5px]
                             focus:outline-none focus:ring-1 focus:ring-money leading-relaxed"
                />
              </label>

              <div className="rounded-lg bg-surface2 border border-border p-3 text-[11.5px] text-muted space-y-1.5">
                <p className="font-medium text-ink">Tips for better results:</p>
                <ul className="list-disc list-inside space-y-0.5">
                  <li>Be specific about entry conditions, indicators, and direction</li>
                  <li>Mention indicators by name (EMA, RSI, ATR, Donchian, Bollinger, VWAP, etc.)</li>
                  <li>State the trigger clearly — "when X crosses above Y" beats "when X is high"</li>
                </ul>
              </div>

              {err && (
                <div className="rounded-lg border border-down/40 bg-down/5 p-3 text-[12.5px] text-down">
                  {err}
                </div>
              )}
            </>
          )}

          {phase === "generating" && (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <div className="text-4xl animate-pulse">🤖</div>
              <p className="text-[14px] font-medium text-ink">Generating your custom node…</p>
              <p className="text-[12px] text-muted">Calling the AI and validating the graph. Usually under 10 seconds.</p>
            </div>
          )}

          {phase === "preview" && graph && stats && (
            <>
              <div className="rounded-lg bg-up/5 border border-up/30 p-3 text-[12.5px] text-ink">
                ✓ Generated — {stats.nodes} nodes, {stats.edges} wires, lanes: <span className="font-mono text-[11px]">{stats.lanes.join(" → ")}</span>
              </div>

              <label className="block">
                <span className="text-[12px] text-muted font-medium">Node name</span>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2 text-[13.5px]
                             focus:outline-none focus:ring-1 focus:ring-money"
                />
              </label>

              <label className="block">
                <span className="text-[12px] text-muted font-medium">Short description</span>
                <textarea
                  value={nodeNote}
                  onChange={(e) => setNodeNote(e.target.value)}
                  rows={2}
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2 text-[12.5px]
                             focus:outline-none focus:ring-1 focus:ring-money leading-relaxed"
                />
              </label>

              <div className="rounded-lg bg-surface2 border border-border p-3">
                <div className="text-[11px] uppercase tracking-widest text-muted mb-2 font-semibold">Internal graph</div>
                <ul className="space-y-1 text-[12px]">
                  {graph.nodes.map((n) => (
                    <li key={n.id} className="flex items-center justify-between font-mono">
                      <span className="text-ink">{n.id}</span>
                      <span className="text-muted">{n.type}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <p className="text-[11px] text-muted italic">
                This node will appear in your palette under <strong>My Custom Nodes</strong>. Click it to drop
                the whole sub-graph onto any canvas. It's stored in your browser only.
              </p>
            </>
          )}

          {phase === "saving" && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <div className="text-3xl">💾</div>
              <p className="text-[13px] text-muted">Saving…</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-border flex items-center justify-between bg-surface2/40">
          {phase === "describe" && (
            <>
              <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5">
                Cancel
              </button>
              <button
                onClick={generate}
                disabled={!description.trim()}
                className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark
                           transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Generate with AI →
              </button>
            </>
          )}

          {phase === "preview" && graph && (
            <>
              <button
                onClick={() => { setGraph(null); setPhase("describe"); }}
                className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5"
              >
                ← Rewrite
              </button>
              <div className="flex items-center gap-2">
                <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5">
                  Discard
                </button>
                <button
                  onClick={save}
                  disabled={!name.trim()}
                  className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark
                             transition-colors disabled:opacity-50"
                >
                  Save to palette
                </button>
              </div>
            </>
          )}

          {(phase === "generating" || phase === "saving") && (
            <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5 ml-auto">
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
