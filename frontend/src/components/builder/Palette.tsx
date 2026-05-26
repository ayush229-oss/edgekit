"use client";

/**
 * Left-side palette — every available node, grouped by category.
 * Click a node row to drop it onto the canvas (center coordinates).
 *
 * Drag-to-canvas is a nice v2 — for v1, click-to-add is faster to learn
 * and works on touch devices without extra wiring.
 */
import type { NodeSpec } from "@/lib/api";

const CATS: { key: string; label: string; hint: string }[] = [
  { key: "signal", label: "Signals",  hint: "What triggers a setup" },
  { key: "filter", label: "Filters",  hint: "Extra conditions (AND)" },
  { key: "entry",  label: "Entry",    hint: "Where to enter the trade" },
  { key: "risk",   label: "Risk",     hint: "Where the initial stop goes" },
];

const CAT_DOT: Record<string, string> = {
  signal: "bg-sage", filter: "bg-amber", entry: "bg-muted", risk: "bg-terra",
};

export function Palette({
  library, onAdd,
}: {
  library: NodeSpec[];
  onAdd:   (spec: NodeSpec) => void;
}) {
  return (
    <div className="w-64 shrink-0 bg-cream2 border-r border-border h-full overflow-y-auto">
      <div className="p-4 border-b border-border">
        <h2 className="font-semibold text-sm">Nodes</h2>
        <p className="text-[11px] text-muted mt-0.5">Click any node to add it.</p>
      </div>
      {CATS.map(({ key, label, hint }) => {
        const nodes = library.filter((n) => n.category === key);
        return (
          <div key={key} className="border-b border-border">
            <div className="px-4 pt-3 pb-1.5 flex items-center gap-2">
              <span className={`w-1.5 h-1.5 rounded-full ${CAT_DOT[key]}`} />
              <span className="text-xs uppercase tracking-widest text-muted">{label}</span>
            </div>
            <p className="px-4 text-[10px] text-muted italic mb-1.5">{hint}</p>
            <ul>
              {nodes.map((n) => (
                <li key={n.type}>
                  <button
                    onClick={() => onAdd(n)}
                    className="w-full text-left px-4 py-2 hover:bg-cream transition-colors"
                  >
                    <div className="text-sm font-medium leading-tight">{n.label}</div>
                    <div className="text-[10px] text-muted leading-snug mt-0.5">{n.description}</div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
