"use client";

/**
 * Modal showing the generated Pine Script with copy-to-clipboard and
 * download-as-file actions.
 *
 * Opens from the "📜 Pine Script" button in the toolbar. Calls the
 * /graph/v2/pinescript endpoint on open. Re-fetches if the graph changes
 * while the modal is open (so the user always sees fresh code).
 */
import { useEffect, useState } from "react";
import { v2ExportPineScript, type V2Graph } from "@/lib/api";
import type { TradeMgmt } from "@/components/TradeManagement";


export function PineExportModal({
  open, onClose, graph, mgmt, strategyName,
}: {
  open:         boolean;
  onClose:      () => void;
  graph:        V2Graph | null;
  mgmt:         TradeMgmt;
  strategyName: string;
}) {
  const [code,    setCode]    = useState("");
  const [lines,   setLines]   = useState(0);
  const [busy,    setBusy]    = useState(false);
  const [err,     setErr]     = useState<string | null>(null);
  const [copied,  setCopied]  = useState(false);

  useEffect(() => {
    if (!open || !graph || graph.nodes.length === 0) return;
    setBusy(true); setErr(null); setCopied(false);
    v2ExportPineScript({
      graph,
      target_r:         mgmt.target_r,
      target_close_pct: mgmt.target_close_pct,
      trail_mode:       mgmt.trail_mode,
      trail_start:      mgmt.trail_start,
      trail_params:     mgmt.trail_params,
    })
      .then((r) => { setCode(r.code); setLines(r.lines); })
      .catch((e) => setErr(e.message ?? String(e)))
      .finally(() => setBusy(false));
  }, [open, graph, mgmt]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      setErr("Clipboard blocked by browser — select the code and copy manually.");
    }
  }

  function download() {
    const safe = (strategyName || "edgekit_strategy").replace(/[^a-z0-9-_]+/gi, "_");
    const blob = new Blob([code], { type: "text/plain;charset=utf-8" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url; a.download = `${safe}.pine`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (!open) return null;

  // Free-tier Pine limit. Premium = 1000, Pro+ = 4000.
  const overFreeLimit = lines > 500;
  const overPremium   = lines > 1000;

  return (
    <div className="fixed inset-0 z-50 bg-cream/95 backdrop-blur-sm flex items-center justify-center p-6">
      <div className="bg-cream2 border border-border rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col">
        <div className="flex items-start justify-between p-5 border-b border-border">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg">📊</span>
              <h2 className="text-xl font-semibold">Deploy to TradingView</h2>
              <span className="text-[10px] uppercase tracking-widest text-muted bg-cream border border-border px-1.5 py-0.5 rounded">Artifact</span>
            </div>
            <p className="text-xs text-muted mt-1 max-w-2xl">
              Copy this Pine Script v6 code into TradingView when you're ready to take the strategy live.
              For iteration and tuning, use <strong>📈 Preview chart</strong> instead — same simulator, same numbers.
            </p>
          </div>
          <button onClick={onClose} className="text-muted hover:text-ink text-2xl leading-none">×</button>
        </div>

        {/* Prominent divergence disclaimer — this is the trust-protection layer */}
        <div className="px-5 py-3 border-b border-border bg-amber/10">
          <div className="flex gap-3">
            <span className="text-amber-900 text-base shrink-0">⚠</span>
            <div className="text-[11px] text-amber-900 leading-relaxed">
              <strong>Backtest numbers in TradingView will differ from Edgekit by 5–15%</strong> — TradingView's fill model,
              ATR formula (RMA vs SMA), and timezone handling don't match the Edgekit simulator exactly. Treat this as a
              <em> deployment artifact</em>, not a re-validation. Trust the Edgekit backtest; use this Pine code to actually
              place the trades on TradingView's live execution.
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 px-5 py-3 border-b border-border bg-cream/40 text-xs">
          <span className={overFreeLimit ? "text-amber-900 font-medium" : "text-muted"}>
            {lines} lines · {code.length} chars
          </span>
          {overFreeLimit && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium
              ${overPremium ? "bg-terra/20 text-terra" : "bg-amber/30 text-amber-900"}`}>
              {overPremium ? "Needs TradingView Pro+ (4000-line limit)" : "Needs TradingView Premium (1000-line limit)"}
            </span>
          )}
          <span className="text-muted">·</span>
          <span className="text-muted italic">
            Trail "{mgmt.trail_mode}" approximated
          </span>
          <div className="flex-1" />
          <button onClick={copy} disabled={!code || busy}
            className={`text-xs px-3 py-1.5 rounded transition-colors disabled:opacity-50
              ${copied ? "bg-sage text-cream2" : "bg-sage/15 text-sage hover:bg-sage/25 border border-sage/30"}`}>
            {copied ? "✓ Copied" : "Copy code"}
          </button>
          <button onClick={download} disabled={!code || busy}
            className="text-xs px-3 py-1.5 rounded border border-border hover:bg-cream transition-colors disabled:opacity-50">
            Download .pine
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4">
          {busy && <div className="text-sm text-muted italic">Generating…</div>}
          {err  && <div className="text-sm text-terra">{err}</div>}
          {!busy && code && (
            <pre className="text-[12px] font-mono leading-relaxed bg-cream rounded-md p-4 border border-border whitespace-pre overflow-x-auto">
{code}
            </pre>
          )}
          {!busy && !code && !err && (
            <div className="text-sm text-muted italic">
              No graph to export — drop some nodes on the canvas first.
            </div>
          )}
        </div>

        <div className="px-5 py-3 border-t border-border bg-cream/40 text-[11px] text-muted">
          <strong className="text-ink">5-step deploy:</strong>
          <span className="mx-2">①</span> Open <a href="https://www.tradingview.com/chart" target="_blank" rel="noreferrer" className="underline hover:text-ink">TradingView chart</a>
          <span className="mx-2">②</span> Click <em>Pine Editor</em> at the bottom
          <span className="mx-2">③</span> Paste the code
          <span className="mx-2">④</span> Click <em>Save</em>, name it
          <span className="mx-2">⑤</span> Click <em>Add to chart</em>
        </div>
      </div>
    </div>
  );
}
