"use client";

/**
 * AI-driven custom node builder — supports all lanes.
 *
 * User describes what they want (any lane, any logic).
 * AI generates a UserNodeDef: lane, ports, params, formula(s).
 * User reviews, optionally renames, and saves to palette.
 *
 * Supported lanes: indicator, alpha, filter, sizing, risk, exit.
 */
import { useState } from "react";
import { v2NodeFromText } from "@/lib/api";
import {
  saveUserNode, type UserNodeDef, type UserLane,
  LANE_COLORS, LANE_DESCRIPTIONS,
} from "@/lib/userNodes";

type Phase = "describe" | "generating" | "preview" | "saving";

const LANE_HINTS: Record<UserLane, string> = {
  indicator: '"Hull Moving Average with period param"',
  alpha:     '"Go long when EMA(8) crosses above EMA(21)"',
  filter:    '"Only pass signals during London/NY overlap (8am–12pm)"',
  sizing:    '"Risk 1% of equity, scaled by ATR volatility"',
  risk:      '"Stop 1.5× ATR below entry"',
  exit:      '"Target 3R, reduce to 2R during high volatility"',
};

export function UserNodeBuilder({
  open,
  onClose,
  onCreated,
}: {
  open:       boolean;
  onClose:    () => void;
  onCreated?: (def: UserNodeDef) => void;
}) {
  const [phase,       setPhase]       = useState<Phase>("describe");
  const [description, setDescription] = useState("");
  const [draft,       setDraft]       = useState<UserNodeDef | null>(null);
  const [label,       setLabel]       = useState("");
  const [err,         setErr]         = useState<string | null>(null);

  function reset() {
    setPhase("describe"); setDescription(""); setDraft(null);
    setLabel(""); setErr(null);
  }
  function close() { reset(); onClose(); }

  async function generate() {
    if (!description.trim()) return;
    setErr(null);
    setPhase("generating");
    try {
      const def = await v2NodeFromText(description.trim());
      setDraft(def as UserNodeDef);
      setLabel((def as any).label || "Custom node");
      setPhase("preview");
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setPhase("describe");
    }
  }

  function save() {
    if (!draft) return;
    setPhase("saving");
    const saved = saveUserNode({ ...draft, label: label.trim() || draft.label });
    onCreated?.(saved);
    reset();
    onClose();
  }

  if (!open) return null;

  const laneColor = draft ? LANE_COLORS[draft.lane as UserLane] ?? "#6B7280" : "#6B7280";

  return (
    <div className="fixed inset-0 z-50 bg-paper/95 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl shadow-float w-full max-w-xl max-h-[90vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-6 py-4 border-b border-border flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-widest text-muted font-semibold">AI Generated</span>
              {draft && (
                <span className="text-[10px] px-1.5 py-0.5 rounded font-medium text-white"
                  style={{ background: laneColor }}>
                  {draft.lane}
                </span>
              )}
            </div>
            <h2 className="text-[18px] font-semibold text-ink">Create a custom node</h2>
            <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
              Describe any node — indicator, signal, filter, sizing, risk, or exit logic.
              The AI picks the right lane and writes the formula.
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
                  rows={5}
                  placeholder={
                    Object.values(LANE_HINTS).map((h) => `• ${h}`).join("\n")
                  }
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2.5 text-[13.5px]
                             focus:outline-none focus:ring-1 focus:ring-money leading-relaxed"
                />
              </label>

              {/* Lane cheat-sheet */}
              <div className="grid grid-cols-2 gap-2">
                {(Object.entries(LANE_DESCRIPTIONS) as [UserLane, string][]).map(([lane, desc]) => (
                  <button
                    key={lane}
                    onClick={() => setDescription((d) => d + (d ? " " : "") + `(${lane}) `)}
                    className="text-left p-2.5 rounded-lg border border-border hover:border-money/40 transition-colors"
                  >
                    <div className="flex items-center gap-1.5 mb-0.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: LANE_COLORS[lane] }} />
                      <span className="text-[11px] font-semibold uppercase tracking-wide text-ink">{lane}</span>
                    </div>
                    <p className="text-[10.5px] text-muted leading-snug">{desc}</p>
                  </button>
                ))}
              </div>

              {err && (
                <div className="rounded-lg border border-down/40 bg-down/5 p-3 text-[12.5px] text-down">
                  {err}
                </div>
              )}
            </>
          )}

          {phase === "generating" && (
            <div className="flex flex-col items-center justify-center py-14 gap-3">
              <div className="text-4xl animate-pulse">⚙</div>
              <p className="text-[14px] font-medium text-ink">Generating your node…</p>
              <p className="text-[12px] text-muted">AI is choosing the lane and writing the formula.</p>
            </div>
          )}

          {phase === "preview" && draft && (
            <>
              {/* Lane badge */}
              <div className="flex items-center gap-2 p-3 rounded-lg border"
                style={{ borderColor: laneColor + "40", background: laneColor + "08" }}>
                <span className="w-3 h-3 rounded-full" style={{ background: laneColor }} />
                <span className="text-[12.5px] font-semibold text-ink uppercase tracking-wide">{draft.lane}</span>
                <span className="text-[11.5px] text-muted">· {LANE_DESCRIPTIONS[draft.lane as UserLane]}</span>
              </div>

              {/* Name */}
              <label className="block">
                <span className="text-[12px] text-muted font-medium">Node name</span>
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2 text-[13.5px]
                             focus:outline-none focus:ring-1 focus:ring-money"
                />
              </label>

              {/* Outputs (indicator only) */}
              {draft.lane === "indicator" && draft.outputs.length > 0 && (
                <div className="rounded-lg bg-surface2 border border-border divide-y divide-border">
                  <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-muted font-semibold">Outputs</div>
                  {draft.outputs.map((o) => (
                    <div key={o.name} className="px-3 py-2 flex items-center justify-between">
                      <span className="font-mono text-[12.5px] text-ink">{o.name}</span>
                      <span className="text-[11px] text-muted px-1.5 py-0.5 rounded bg-paper border border-border">{o.type}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Extra inputs */}
              {draft.extra_inputs && draft.extra_inputs.length > 0 && (
                <div className="rounded-lg bg-surface2 border border-border divide-y divide-border">
                  <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-muted font-semibold">Extra Inputs</div>
                  {draft.extra_inputs.map((p) => (
                    <div key={p.name} className="px-3 py-2 flex items-center justify-between">
                      <span className="font-mono text-[12.5px] text-ink">{p.name}</span>
                      <span className="text-[11px] text-muted">{p.type}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Params */}
              {draft.params_spec.length > 0 && (
                <div className="rounded-lg bg-surface2 border border-border divide-y divide-border">
                  <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-muted font-semibold">Parameters</div>
                  {draft.params_spec.map((p) => (
                    <div key={p.key} className="px-3 py-2 flex items-center justify-between">
                      <span className="text-[12.5px] text-ink">{p.label}</span>
                      <span className="font-mono text-[11px] text-muted">
                        {p.type} · default {p.default}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Formulas */}
              <div className="rounded-lg bg-surface2 border border-border divide-y divide-border">
                <div className="px-3 py-2 text-[10px] uppercase tracking-widest text-muted font-semibold">Formula</div>
                {Object.entries(draft.formulas).map(([port, expr]) => (
                  <div key={port} className="px-3 py-2">
                    {Object.keys(draft.formulas).length > 1 && (
                      <div className="text-[10.5px] text-muted mb-1 font-mono">{port}</div>
                    )}
                    <code className="text-[11px] text-ink break-all leading-relaxed block font-mono">
                      {expr}
                    </code>
                  </div>
                ))}
              </div>

              <p className="text-[11px] text-muted italic">
                Saved under <strong>My Custom Nodes</strong> in the palette. Lives in your browser only.
              </p>
            </>
          )}

          {phase === "saving" && (
            <div className="flex flex-col items-center justify-center py-14 gap-2">
              <p className="text-[13px] text-muted">Saving…</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-border flex items-center justify-between bg-surface2/40">
          {phase === "describe" && (
            <>
              <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5">Cancel</button>
              <button
                onClick={generate}
                disabled={!description.trim()}
                className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark
                           transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Generate →
              </button>
            </>
          )}
          {phase === "preview" && draft && (
            <>
              <button onClick={() => { setDraft(null); setPhase("describe"); }}
                className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5">← Rewrite</button>
              <div className="flex items-center gap-2">
                <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5">Discard</button>
                <button onClick={save} disabled={!label.trim()}
                  className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark
                             transition-colors disabled:opacity-50">
                  Save to palette
                </button>
              </div>
            </>
          )}
          {(phase === "generating" || phase === "saving") && (
            <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-3 py-1.5 ml-auto">Cancel</button>
          )}
        </div>
      </div>
    </div>
  );
}
