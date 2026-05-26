"use client";

/**
 * Right-side property panel — edits the params of the currently-selected
 * node. Renders a control per ParamSpec.type ("int" | "float" | "select" | "bool").
 */
import type { NodeSpec, ParamSpec } from "@/lib/api";

export function PropertyPanel({
  spec, params, onChange, onDelete,
}: {
  spec:     NodeSpec | null;
  params:   Record<string, any>;
  onChange: (k: string, v: any) => void;
  onDelete: () => void;
}) {
  if (!spec) {
    return (
      <div className="p-5 text-sm text-muted">
        <p className="italic">Click a node on the canvas to edit it.</p>
      </div>
    );
  }
  return (
    <div className="p-5 space-y-4">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted">{spec.category}</div>
        <h3 className="text-base font-semibold mt-0.5">{spec.label}</h3>
        <p className="text-xs text-muted mt-1 leading-snug">{spec.description}</p>
      </div>

      <div className="space-y-3">
        {spec.params.map((p) => (
          <ParamRow key={p.key} p={p} value={params[p.key]} onChange={(v) => onChange(p.key, v)} />
        ))}
        {spec.params.length === 0 && (
          <p className="text-xs italic text-muted">No parameters — drop it on the canvas and wire it up.</p>
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
  p, value, onChange,
}: { p: ParamSpec; value: any; onChange: (v: any) => void }) {
  return (
    <label className="block">
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium">{p.label}</span>
        {(p.type === "int" || p.type === "float") && (
          <span className="font-mono text-sage text-[11px]">{value ?? p.default}</span>
        )}
      </div>
      {p.description && (
        <p className="text-[10px] italic text-muted leading-snug mb-1">{p.description}</p>
      )}
      {(p.type === "int" || p.type === "float") && (
        <input
          type="range"
          min={p.min ?? 0} max={p.max ?? 100}
          step={p.step ?? (p.type === "int" ? 1 : 0.1)}
          value={value ?? p.default}
          onChange={(e) => onChange(p.type === "int" ? parseInt(e.target.value) : parseFloat(e.target.value))}
          className="w-full mt-1 accent-sage"
        />
      )}
      {p.type === "select" && (
        <select
          value={value ?? p.default}
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
          <input type="checkbox"
            checked={!!(value ?? p.default)}
            onChange={(e) => onChange(e.target.checked)}
            className="accent-sage" />
          <span className="text-muted text-xs">Enabled</span>
        </label>
      )}
    </label>
  );
}
