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
  listUserNodes, deleteUserNode, saveUserNode, onUserNodesChange, toV2NodeSpec,
  LANE_COLORS, type UserNodeDef, type UserLane,
} from "@/lib/userNodes";


export function PaletteV2({
  library, onAdd,
  onAddUserNode, onOpenUserNodeBuilder,
  minimized, onToggleMinimized,
}: {
  library:               V2NodeSpec[];
  onAdd:                 (spec: V2NodeSpec) => void;
  onAddUserNode:         (def: UserNodeDef) => void;
  onOpenUserNodeBuilder: () => void;
  minimized:             boolean;
  onToggleMinimized:     () => void;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const [userNodes, setUserNodes] = useState<UserNodeDef[]>([]);
  useEffect(() => {
    setUserNodes(listUserNodes());
    return onUserNodesChange(() => setUserNodes(listUserNodes()));
  }, []);

  // Inline edit state
  const [editId,    setEditId]    = useState<string | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editDesc,  setEditDesc]  = useState("");

  function startEdit(un: UserNodeDef, e: React.MouseEvent) {
    e.stopPropagation();
    setEditId(un.id);
    setEditLabel(un.label);
    setEditDesc(un.description ?? "");
  }

  function saveEdit() {
    if (!editId) return;
    const node = userNodes.find((n) => n.id === editId);
    if (node) saveUserNode({ ...node, label: editLabel.trim() || node.label, description: editDesc.trim(), id: editId });
    setEditId(null);
  }

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

      {/* ── My Custom Nodes ─────────────────────────────────────────────── */}
      <div className="border-b border-border bg-sage/[0.03]">
        <div className="px-4 pt-3 pb-2 flex items-center gap-2">
          <span className="w-1.5 h-3 rounded-sm bg-sage" />
          <span className="text-xs uppercase tracking-widest text-muted flex-1">My Custom Nodes</span>
          <span className="text-[10px] text-muted">{userNodes.length}</span>
        </div>

        <button
          onClick={onOpenUserNodeBuilder}
          className="w-full px-4 py-2 text-left text-[12px] text-sage hover:bg-sage/10 transition-colors
                     flex items-center gap-1.5 font-medium"
        >
          <span className="text-base leading-none">✨</span>
          Create with AI…
        </button>

        {/* Inline edit form */}
        {editId && (
          <div className="mx-3 mb-2 p-2.5 rounded-lg border border-sage/30 bg-sage/5 space-y-2">
            <input
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              placeholder="Node name"
              className="w-full text-[12px] bg-paper border border-border rounded px-2 py-1.5
                         focus:outline-none focus:ring-1 focus:ring-sage"
              autoFocus
            />
            <input
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              placeholder="Short description (optional)"
              className="w-full text-[11px] bg-paper border border-border rounded px-2 py-1
                         focus:outline-none focus:ring-1 focus:ring-sage text-muted"
            />
            <div className="flex gap-1.5">
              <button onClick={saveEdit}
                className="flex-1 text-[11px] py-1 rounded bg-sage text-white font-medium hover:bg-sageMid transition-colors">
                Save
              </button>
              <button onClick={() => setEditId(null)}
                className="px-2 text-[11px] py-1 rounded border border-border text-muted hover:bg-cream transition-colors">
                Cancel
              </button>
            </div>
          </div>
        )}

        {userNodes.length > 0 && (
          <ul className="pb-1">
            {userNodes.map((un) => (
              <li key={un.id} className="group">
                {editId === un.id ? null : (
                  <div className="flex items-stretch hover:bg-cream transition-colors">
                    <button
                      onClick={() => onAddUserNode(un)}
                      className="flex-1 text-left px-4 py-2 min-w-0"
                      title={un.description || un.label}
                    >
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="w-2 h-2 rounded-full shrink-0"
                          style={{ background: LANE_COLORS[un.lane as UserLane] ?? "#6B7280" }} />
                        <div className="text-[12.5px] font-medium leading-tight truncate">{un.label}</div>
                      </div>
                      {un.description && (
                        <div className="text-[10px] text-muted leading-snug mt-0.5 line-clamp-1 pl-3.5">
                          {un.description}
                        </div>
                      )}
                      <div className="text-[9px] text-muted mt-0.5 font-mono uppercase tracking-wide pl-3.5">
                        {un.lane}
                      </div>
                    </button>
                    {/* Edit button */}
                    <button
                      onClick={(e) => startEdit(un, e)}
                      title="Edit name / description"
                      className="px-1.5 text-muted hover:text-ink opacity-0 group-hover:opacity-100 transition-opacity text-[11px]"
                    >
                      ✎
                    </button>
                    {/* Delete button */}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (confirm(`Delete "${un.label}"?`)) deleteUserNode(un.id);
                      }}
                      title="Delete"
                      className="px-2 text-muted hover:text-down opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ×
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}

        {userNodes.length === 0 && (
          <p className="px-4 pb-3 text-[10px] text-muted italic leading-snug">
            Describe any node — indicator, signal, filter, sizing, risk, or exit. The AI builds it.
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

