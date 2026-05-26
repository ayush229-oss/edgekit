/**
 * Custom Nodes — user-saved AI-generated sub-graphs.
 *
 * Stored in localStorage (browser-local, per user). Each custom node is a
 * pre-built V2 graph fragment that can be dropped onto the canvas as a unit.
 *
 * Why localStorage and not server-side?
 *   - No auth in the app yet — no per-user identity
 *   - Custom nodes feel personal; users expect them under their own browser
 *   - We can migrate to a DB-backed registry later without changing the shape
 */
import type { V2Graph } from "@/lib/api";

const STORAGE_KEY = "edgekit.customNodes.v1";

export type CustomNode = {
  id:          string;        // unique slug, used as palette key
  name:        string;        // display label in palette
  description: string;        // tooltip / hover text
  graph:       V2Graph;       // the actual nodes + edges to inline
  prompt:      string;        // original user description (for editing later)
  created_at:  number;        // unix ms
};

function safeRead(): CustomNode[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function safeWrite(nodes: CustomNode[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nodes));
    // Notify any in-page listeners (the palette refreshes itself this way).
    window.dispatchEvent(new CustomEvent("edgekit:customNodes:changed"));
  } catch {
    /* quota / private-browsing: silently fail */
  }
}

export function listCustomNodes(): CustomNode[] {
  return safeRead().sort((a, b) => b.created_at - a.created_at);
}

export function getCustomNode(id: string): CustomNode | undefined {
  return safeRead().find((n) => n.id === id);
}

export function saveCustomNode(input: Omit<CustomNode, "id" | "created_at"> & { id?: string }): CustomNode {
  const all = safeRead();
  const id  = input.id || `cn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
  const next: CustomNode = {
    id,
    name:        input.name.trim() || "Untitled custom node",
    description: input.description.trim(),
    graph:       input.graph,
    prompt:      input.prompt,
    created_at:  Date.now(),
  };
  const filtered = all.filter((n) => n.id !== id);
  safeWrite([next, ...filtered]);
  return next;
}

export function deleteCustomNode(id: string) {
  safeWrite(safeRead().filter((n) => n.id !== id));
}

/**
 * Subscribe to changes from any tab / component in the same window.
 * Returns an unsubscribe function.
 */
export function onCustomNodesChange(handler: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const inPage = () => handler();
  const cross  = (e: StorageEvent) => { if (e.key === STORAGE_KEY) handler(); };
  window.addEventListener("edgekit:customNodes:changed", inPage);
  window.addEventListener("storage", cross);
  return () => {
    window.removeEventListener("edgekit:customNodes:changed", inPage);
    window.removeEventListener("storage", cross);
  };
}
