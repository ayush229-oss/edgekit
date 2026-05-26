"use client";

/**
 * Custom React Flow node — shown as a colored card on the canvas.
 * The "data" object carries: { spec: NodeSpec, params, onSelect, selected }
 */
import { Handle, Position, NodeProps } from "reactflow";
import { clsx } from "clsx";
import type { NodeSpec } from "@/lib/api";

const CATEGORY_STYLES: Record<string, { bg: string; border: string; chip: string }> = {
  signal: { bg: "bg-sage/15",      border: "border-sage",      chip: "bg-sage/30      text-sage" },
  filter: { bg: "bg-amber/15",     border: "border-amber",     chip: "bg-amber/30     text-amber" },
  entry:  { bg: "bg-cream2",       border: "border-border",    chip: "bg-cream        text-muted" },
  risk:   { bg: "bg-terra/15",     border: "border-terra",     chip: "bg-terra/30     text-terra" },
};

export type NodeCardData = {
  spec:     NodeSpec;
  params:   Record<string, any>;
  selected: boolean;
};

export function NodeCard({ data, selected }: NodeProps<NodeCardData>) {
  const cat   = data.spec.category;
  const style = CATEGORY_STYLES[cat] ?? CATEGORY_STYLES.entry;

  // Build a small "summary line" so the user can read the node at a glance.
  const summary = Object.entries(data.params)
    .filter(([, v]) => v !== "" && v !== null && v !== undefined)
    .slice(0, 3)
    .map(([k, v]) => `${k}=${typeof v === "number" ? v : String(v)}`)
    .join(" · ");

  return (
    <div className={clsx(
      "rounded-xl border-2 p-3 w-56 shadow-sm transition-shadow",
      style.bg, style.border,
      selected && "ring-2 ring-sage ring-offset-2 ring-offset-cream",
    )}>
      <Handle type="target" position={Position.Left}  className="!w-2 !h-2 !bg-muted" />
      <Handle type="source" position={Position.Right} className="!w-2 !h-2 !bg-muted" />

      <div className="flex items-center gap-2 mb-1">
        <span className={clsx("text-[10px] uppercase tracking-wider px-2 py-0.5 rounded", style.chip)}>
          {cat}
        </span>
      </div>
      <div className="font-medium text-sm leading-tight">{data.spec.label}</div>
      {summary && (
        <div className="font-mono text-[10px] text-muted mt-1.5 leading-snug">{summary}</div>
      )}
    </div>
  );
}
