"use client";

/**
 * Right-rail property editor for the selected node.
 * Handles every ParamSpec.type: int, float, select, bool, string.
 */
import { useState } from "react";
import type { V2NodeSpec, ParamSpec } from "@/lib/api";
import { LANE_META, laneAccentColor } from "./portColors";
import { effectFor } from "./coachingHints";


export function PropertyPanelV2({
  spec, params, onChange, onDelete,
}: {
  spec:     V2NodeSpec | null;
  params:   Record<string, any>;
  onChange: (k: string, v: any) => void;
  onDelete: () => void;
}) {
  if (!spec) {
    return (
      <div className="p-5 text-sm text-muted">
        <p className="italic">Click a node on the canvas to edit it.</p>
        <p className="text-[11px] mt-2">
          Or click an empty area to deselect. Click a node in the palette to drop a new one.
        </p>
      </div>
    );
  }
  const lane = LANE_META[spec.lane];
  return (
    <div className="p-5 space-y-4">
      <div>
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-3 rounded-sm" style={{ background: laneAccentColor(spec.lane) }} />
          <div className="text-[10px] uppercase tracking-widest text-muted">{lane.label}</div>
        </div>
        <h3 className="text-base font-semibold mt-1">{spec.label}</h3>
        <p className="text-xs text-muted mt-1 leading-snug">{spec.description}</p>
      </div>

      <div className="space-y-3">
        {spec.params.map((p) => (
          <ParamRow
            key={p.key}
            p={p}
            value={params[p.key]}
            onChange={(v) => onChange(p.key, v)}
            nodeType={spec.type}
          />
        ))}
        {spec.params.length === 0 && (
          <p className="text-xs italic text-muted">No parameters — just wire it.</p>
        )}
      </div>

      <button
        onClick={onDelete}
        className="w-full mt-4 py-2 text-xs rounded-md border border-terra text-terra hover:bg-terra/10 transition-colors"
      >
        Delete node
      </button>
    </div>
  );
}


function ParamRow({
  p, value, onChange, nodeType,
}: { p: ParamSpec; value: any; onChange: (v: any) => void; nodeType: string }) {
  const [showEffect, setShowEffect] = useState(false);
  const effect = effectFor(nodeType, p.key);
  const numeric = p.type === "int" || p.type === "float";
  const step    = p.step ?? (p.type === "int" ? 1 : 0.1);
  const min     = p.min ?? -Infinity;
  const max     = p.max ?? Infinity;

  // Clamp + round so float arithmetic doesn't produce 20.00000001 etc.
  const setNum = (raw: number) => {
    if (Number.isNaN(raw)) return;
    let v = Math.max(min, Math.min(max, raw));
    if (p.type === "int") v = Math.round(v);
    else v = Math.round(v / step) * step;            // snap to step
    onChange(p.type === "int" ? Math.trunc(v) : Number(v.toFixed(4)));
  };

  return (
    <label className="block">
      <div className="flex items-center justify-between text-xs gap-2">
        <span className="font-medium flex-1">{p.label}</span>
        {numeric && (
          <div className="flex items-center gap-0.5">
            <button type="button"
              onClick={(e) => { e.preventDefault(); setNum(Number(value ?? p.default) - step); }}
              className="w-5 h-5 rounded bg-cream hover:bg-cream3 border border-border text-muted hover:text-ink text-xs leading-none flex items-center justify-center select-none"
              title={`Decrease by ${step}`}>−</button>
            <input
              type="number"
              value={(value ?? p.default) as number}
              step={step} min={p.min} max={p.max}
              onChange={(e) => setNum(parseFloat(e.target.value))}
              className="w-14 text-center font-mono text-[11px] text-sage bg-cream border border-border rounded px-1 py-0.5
                          focus:outline-none focus:ring-1 focus:ring-sage
                          [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            />
            <button type="button"
              onClick={(e) => { e.preventDefault(); setNum(Number(value ?? p.default) + step); }}
              className="w-5 h-5 rounded bg-cream hover:bg-cream3 border border-border text-muted hover:text-ink text-xs leading-none flex items-center justify-center select-none"
              title={`Increase by ${step}`}>+</button>
          </div>
        )}
      </div>
      {p.description && (
        <p className="text-[10px] italic text-muted leading-snug mb-1 mt-0.5">{p.description}</p>
      )}
      {numeric && (
        <input
          type="range"
          min={p.min ?? 0} max={p.max ?? 100}
          step={step}
          value={(value ?? p.default) as number}
          onChange={(e) => setNum(parseFloat(e.target.value))}
          className="w-full mt-1 accent-sage"
        />
      )}
      {p.type === "select" && (
        <select
          value={(value ?? p.default) as string}
          onChange={(e) => onChange(e.target.value)}
          className="w-full mt-1 rounded-md bg-cream border border-border px-2 py-1.5 text-sm"
        >
          {(p.options ?? []).map((o) => (
            <option key={String(o)} value={String(o)}>{String(o)}</option>
          ))}
        </select>
      )}
      {p.type === "bool" && (
        <label className="flex items-center gap-2 mt-1 text-sm">
          <input
            type="checkbox"
            checked={!!(value ?? p.default)}
            onChange={(e) => onChange(e.target.checked)}
            className="accent-sage"
          />
          <span className="text-muted text-xs">Enabled</span>
        </label>
      )}
      {(p.type as string) === "string" && (
        <input
          type="text"
          value={(value ?? p.default ?? "") as string}
          onChange={(e) => onChange(e.target.value)}
          className="w-full mt-1 rounded-md bg-cream border border-border px-2 py-1.5 text-sm"
        />
      )}

      {/* "Effect" coaching hint — toggleable, single line collapsed */}
      {effect && (
        <div className="mt-1">
          <button
            type="button"
            onClick={(e) => { e.preventDefault(); setShowEffect((v) => !v); }}
            className="text-[10px] text-sage hover:text-sageMid flex items-center gap-1">
            <span>{showEffect ? "▾" : "▸"}</span>
            <span className="italic">What does changing this do?</span>
          </button>
          {showEffect && (
            <div className="mt-1 rounded-md bg-sage/10 border border-sage/20 p-2 text-[10px] leading-snug space-y-1">
              <div><strong className="text-sage">Higher →</strong> <span className="text-ink2">{effect.higher}</span></div>
              <div><strong className="text-terra">Lower →</strong>  <span className="text-ink2">{effect.lower}</span></div>
            </div>
          )}
        </div>
      )}
    </label>
  );
}
