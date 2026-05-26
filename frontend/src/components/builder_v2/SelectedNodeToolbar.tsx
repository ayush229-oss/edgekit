"use client";

/**
 * Floating toolbar shown above the canvas whenever a node is selected.
 * Surfaces the actions users couldn't find: Delete, Duplicate, Deselect.
 * Also reminds the user of the keyboard shortcut.
 */
import type { V2NodeSpec } from "@/lib/api";


export function SelectedNodeToolbar({
  spec, onDelete, onDuplicate, onDeselect,
}: {
  spec:        V2NodeSpec | null;
  onDelete:    () => void;
  onDuplicate: () => void;
  onDeselect:  () => void;
}) {
  if (!spec) return null;
  return (
    <div className="absolute right-3 top-3 z-20
                    bg-cream2 border border-border rounded-full shadow-md
                    px-3 py-1.5 flex items-center gap-2 text-xs">
      <span className="font-medium">{spec.label}</span>
      <span className="text-muted">selected</span>
      <span className="text-muted">·</span>
      <button onClick={onDuplicate}
        className="px-2 py-0.5 rounded hover:bg-cream text-sage">
        Duplicate
      </button>
      <button onClick={onDelete}
        className="px-2 py-0.5 rounded hover:bg-terra/10 text-terra">
        Delete <span className="text-muted ml-1">(Del)</span>
      </button>
      <button onClick={onDeselect}
        className="px-2 py-0.5 rounded hover:bg-cream text-muted">
        ×
      </button>
    </div>
  );
}
