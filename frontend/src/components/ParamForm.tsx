/**
 * Renders strategy parameters as labeled controls (slider/number/select/toggle).
 * Each param shows a description tooltip below the input.
 */
"use client";

import type { ParamSpec } from "@/lib/api";

export function ParamForm({
  params, values, onChange,
}: {
  params: ParamSpec[];
  values: Record<string, any>;
  onChange: (key: string, val: any) => void;
}) {
  return (
    <div className="space-y-4">
      {params.map((p) => {
        const v = values[p.key];
        return (
          <div key={p.key} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <label htmlFor={p.key} className="font-medium">{p.label}</label>
              <span className="font-mono text-xs text-sage">
                {typeof v === "boolean" ? (v ? "ON" : "OFF") : String(v)}
              </span>
            </div>
            {renderInput(p, v, (val) => onChange(p.key, val))}
            {p.description && (
              <p className="text-[11px] italic text-muted leading-snug">{p.description}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function renderInput(p: ParamSpec, value: any, onChange: (v: any) => void) {
  if (p.type === "bool") {
    return (
      <input
        type="checkbox"
        checked={!!value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 accent-sage"
      />
    );
  }
  if (p.type === "select") {
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md bg-cream border border-border px-2 py-1.5 text-sm"
      >
        {(p.options ?? []).map((o) => (
          <option key={String(o)} value={o}>{String(o)}</option>
        ))}
      </select>
    );
  }
  // numeric — render as slider when bounded
  const hasRange = p.min !== undefined && p.max !== undefined;
  if (hasRange) {
    return (
      <input
        type="range"
        min={p.min} max={p.max} step={p.step ?? 1}
        value={Number(value)}
        onChange={(e) => onChange(p.type === "int"
          ? parseInt(e.target.value)
          : parseFloat(e.target.value))}
        className="w-full accent-sage"
      />
    );
  }
  return (
    <input
      type="number"
      step={p.step ?? 1}
      value={Number(value)}
      onChange={(e) => onChange(p.type === "int"
        ? parseInt(e.target.value || "0")
        : parseFloat(e.target.value || "0"))}
      className="w-full rounded-md bg-cream border border-border px-2 py-1.5 text-sm"
    />
  );
}
