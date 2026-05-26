"use client";

/**
 * Lane-grouped palette. Each section is collapsible.
 * Click any row to drop the node onto the canvas at a random spot.
 *
 * Bottom of the palette has a legend explaining the port-type colors,
 * so users learn the wiring rules at a glance.
 */
import { useEffect, useState } from "react";
import type { V2NodeSpec, V2Lane } from "@/lib/api";
import { LANE_META, PORT_COLORS, laneAccentColor } from "./portColors";
import {
  listCustomNodes, deleteCustomNode, onCustomNodesChange,
  type CustomNode,
} from "@/lib/customNodes";


export function PaletteV2({
  library, onAdd, onAddCustomNode, onOpenCustomNodeBuilder, minimized, onToggleMinimized,
}: {
  library:                  V2NodeSpec[];
  onAdd:                    (spec: V2NodeSpec) => void;
  onAddCustomNode:          (cn: CustomNode) => void;
  onOpenCustomNodeBuilder:  () => void;
  minimized:                boolean;
  onToggleMinimized:        () => void;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // Reactive list of saved custom nodes (re-renders when localStorage changes).
  const [customNodes, setCustomNodes] = useState<CustomNode[]>([]);
  useEffect(() => {
    setCustomNodes(listCustomNodes());
    return onCustomNodesChange(() => setCustomNodes(listCustomNodes()));
  }, []);

  const lanes = (Object.keys(LANE_META) as V2Lane[])
    .sort((a, b) => LANE_META[a].order - LANE_META[b].order);

  // ── Minimized: thin strip with one colored dot per lane ───────────────
  if (minimized) {
    return (
      <div className="w-10 shrink-0 bg-cream2 border-r border-border h-full flex flex-col items-center py-3 gap-2">
        <button onClick={onToggleMinimized}
          title="Expand palette"
          className="w-7 h-7 rounded hover:bg-cream flex items-center justify-center text-muted text-base">
          »
        </button>
        <div className="w-full border-t border-border my-1" />
        {lanes.map((lane) => {
          const count = library.filter((n) => n.lane === lane).length;
          if (count === 0) return null;
          return (
            <div key={lane}
              title={`${LANE_META[lane].label} (${count})`}
              className="w-3 h-3 rounded-full"
              style={{ background: laneAccentColor(lane) }} />
          );
        })}
      </div>
    );
  }

  return (
    <div className="w-72 shrink-0 bg-cream2 border-r border-border h-full overflow-y-auto">
      <div className="p-4 border-b border-border flex items-start gap-2">
        <div className="flex-1">
          <h2 className="font-semibold text-sm">Nodes</h2>
          <p className="text-[11px] text-muted mt-0.5">
            Click any node to add it. Wires only connect ports of the same color.
          </p>
        </div>
        <button onClick={onToggleMinimized}
          title="Minimize palette"
          className="w-6 h-6 rounded hover:bg-cream flex items-center justify-center text-muted text-base shrink-0">
          «
        </button>
      </div>

      {/* ── My Custom Nodes (AI-generated, user-saved) ──────────────────── */}
      <div className="border-b border-border bg-money/[0.03]">
        <div className="px-4 pt-3 pb-2 flex items-center gap-2">
          <span className="w-1.5 h-3 rounded-sm bg-money" />
          <span className="text-xs uppercase tracking-widest text-muted flex-1">My Custom Nodes</span>
          <span className="text-[10px] text-muted">{customNodes.length}</span>
        </div>

        <button
          onClick={onOpenCustomNodeBuilder}
          className="w-full mx-0 px-4 py-2 text-left text-[12px] text-money hover:bg-money/10 transition-colors
                     flex items-center gap-1.5 font-medium"
        >
          <span className="text-base leading-none">✨</span>
          Create with AI…
        </button>

        {customNodes.length > 0 && (
          <ul className="pb-1">
            {customNodes.map((cn) => (
              <li key={cn.id} className="group">
                <div className="flex items-stretch hover:bg-cream transition-colors">
                  <button
                    onClick={() => onAddCustomNode(cn)}
                    className="flex-1 text-left px-4 py-2"
                    title={cn.description || cn.name}
                  >
                    <div className="text-sm font-medium leading-tight">{cn.name}</div>
                    {cn.description && (
                      <div className="text-[10px] text-muted leading-snug mt-0.5 line-clamp-2">
                        {cn.description}
                      </div>
                    )}
                    <div className="text-[9px] text-muted mt-0.5 font-mono">
                      {cn.graph.nodes.length} nodes
                    </div>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`Delete custom node "${cn.name}"?`)) deleteCustomNode(cn.id);
                    }}
                    title="Delete this custom node"
                    className="px-2 text-muted hover:text-down opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        {customNodes.length === 0 && (
          <p className="px-4 pb-3 text-[10px] text-muted italic leading-snug">
            Describe a piece of logic, get back a reusable node. Lives in your browser only.
          </p>
        )}
      </div>

      {lanes.map((lane) => {
        const meta  = LANE_META[lane];
        const nodes = library.filter((n) => n.lane === lane);
        if (nodes.length === 0) return null;
        const isOpen = !collapsed[lane];
        return (
          <div key={lane} className="border-b border-border">
            <button
              onClick={() => setCollapsed((s) => ({ ...s, [lane]: !s[lane] }))}
              className="w-full px-4 pt-3 pb-2 flex items-center gap-2 hover:bg-cream transition-colors"
            >
              <span className="w-1.5 h-3 rounded-sm" style={{ background: laneAccentColor(lane) }} />
              <span className="text-xs uppercase tracking-widest text-muted flex-1 text-left">
                {meta.label}
              </span>
              <span className="text-[10px] text-muted">{nodes.length}</span>
              <span className="text-muted text-xs">{isOpen ? "−" : "+"}</span>
            </button>
            {isOpen && (
              <>
                <p className="px-4 text-[10px] text-muted italic mb-1.5">{meta.hint}</p>
                <ul>
                  {nodes.map((n) => (
                    <li key={n.type}>
                      <button
                        onClick={() => onAdd(n)}
                        className="w-full text-left px-4 py-2 hover:bg-cream transition-colors group"
                      >
                        <div className="text-sm font-medium leading-tight">{n.label}</div>
                        <div className="text-[10px] text-muted leading-snug mt-0.5">{n.description}</div>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        );
      })}

      {/* Legend */}
      <div className="px-4 py-4 border-t border-border bg-cream/40">
        <div className="text-[10px] uppercase tracking-widest text-muted mb-2">Port types</div>
        <div className="grid grid-cols-2 gap-x-2 gap-y-1">
          {Object.entries(PORT_COLORS).map(([t, c]) => (
            <div key={t} className="flex items-center gap-1.5 text-[10px]">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: c.bg }} />
              <span className="text-muted">{c.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
