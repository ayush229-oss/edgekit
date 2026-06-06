"use client";

/**
 * v2 custom node — each input/output handle is colored by its PortType.
 * Handle id == port name (so the connection validator can look it up).
 *
 * Layout:
 *   ┌──────────────────────────────────┐
 *   │ ▮ INDICATOR  ATR                 │  ← lane chip + label
 *   │ period=14 · multiplier=2.0       │  ← param summary
 *   │                                  │
 *   │ ●in1                  out1●      │  ← typed handles, color-coded
 *   │ ●in2                  out2●      │
 *   └──────────────────────────────────┘
 */
import { Handle, Position, type NodeProps } from "reactflow";
import { clsx } from "clsx";
import type { V2NodeSpec } from "@/lib/api";
import { PORT_COLORS, LANE_META, laneAccentColor } from "./portColors";

export type NodeCardV2Data = {
  spec:      V2NodeSpec;
  params:    Record<string, any>;
  selected:  boolean;
  disabled?: boolean;
};


export function NodeCardV2({ data, selected }: NodeProps<NodeCardV2Data>) {
  const { spec, params, disabled } = data;
  const accent = laneAccentColor(spec.lane);
  const lane   = LANE_META[spec.lane];

  const summary = Object.entries(params)
    .filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${typeof v === "number" ? (Number.isInteger(v) ? v : v.toFixed(2)) : v}`)
    .join(" · ");

  // Stagger handle y-positions so multi-port nodes have visible separation
  const stepY = (count: number, idx: number) => {
    if (count <= 1) return 50;
    const total = 60;        // total % range
    const start = 50 - total / 2;
    return start + (total * idx) / (count - 1);
  };

  return (
    <div
      className={clsx(
        "rounded-xl border-2 bg-cream2 shadow-sm transition-all min-w-[180px] relative",
        selected ? "ring-2 ring-offset-2 ring-offset-cream" : "",
        disabled ? "opacity-40 grayscale" : "",
      )}
      style={{
        borderColor: accent,
        boxShadow:   selected ? `0 0 0 3px ${accent}55` : undefined,
      }}
    >
      {disabled && (
        <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none rounded-xl">
          <span className="text-[9px] uppercase tracking-widest font-bold bg-ink/80 text-cream2 px-2 py-0.5 rounded">OFF</span>
        </div>
      )}
      {/* Lane stripe at the top */}
      <div className="h-1.5 rounded-t-[10px]" style={{ background: accent }} />

      <div className="px-3 py-2">
        <div className={clsx("inline-block text-[9px] uppercase tracking-widest px-1.5 py-0.5 rounded font-semibold", lane.chip)}>
          {lane.label}
        </div>
        <div className="font-medium text-sm mt-1 leading-tight">{spec.label}</div>
        {summary && (
          <div className="font-mono text-[10px] text-muted mt-1.5 leading-snug whitespace-nowrap overflow-hidden text-ellipsis">
            {summary}
          </div>
        )}
      </div>

      {/* Inputs — left side, color-coded */}
      {spec.inputs.map((p, idx) => (
        <Handle
          key={`in-${p.name}`}
          id={p.name}
          type="target"
          position={Position.Left}
          style={{
            top: `${stepY(spec.inputs.length, idx)}%`,
            background: PORT_COLORS[p.type].bg,
            width: 12, height: 12,
            border: `2px solid ${PORT_COLORS[p.type].ring}`,
          }}
          title={`${p.name} : ${p.type}`}
        />
      ))}

      {/* Outputs — right side, color-coded */}
      {spec.outputs.map((p, idx) => (
        <Handle
          key={`out-${p.name}`}
          id={p.name}
          type="source"
          position={Position.Right}
          style={{
            top: `${stepY(spec.outputs.length, idx)}%`,
            background: PORT_COLORS[p.type].bg,
            width: 12, height: 12,
            border: `2px solid ${PORT_COLORS[p.type].ring}`,
          }}
          title={`${p.name} : ${p.type}`}
        />
      ))}

      {/* Port labels — small text next to each handle */}
      <div className="px-3 pb-2 pt-1 flex flex-col gap-0.5">
        {spec.inputs.length > 0 && (
          <div className="text-[9px] text-muted">
            in: {spec.inputs.map((p) => p.name).join(", ")}
          </div>
        )}
        {spec.outputs.length > 0 && (
          <div className="text-[9px] text-muted text-right">
            out: {spec.outputs.map((p) => p.name).join(", ")}
          </div>
        )}
      </div>
    </div>
  );
}
