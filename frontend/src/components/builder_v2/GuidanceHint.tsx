"use client";

/**
 * Inline guidance phrase. Rendered as a small amber callout next to the
 * UI it's teaching. Hidden when guidance is OFF.
 *
 * Usage:
 *   <GuidanceHint show={guideOn}>
 *     Click any node in the palette to add it. Drag from a colored dot to wire it.
 *   </GuidanceHint>
 */
import type { ReactNode } from "react";


export function GuidanceHint({
  show, children, tone = "info",
}: {
  show:     boolean;
  children: ReactNode;
  tone?:    "info" | "tip" | "warn";
}) {
  if (!show) return null;
  const tones = {
    info: "bg-sky-50 border-sky-200 text-sky-900",
    tip:  "bg-amber/15 border-amber/30 text-amber-900",
    warn: "bg-terra/10 border-terra/30 text-terra",
  };
  return (
    <div className={`rounded-md border px-2.5 py-1.5 text-[11px] leading-snug ${tones[tone]} flex gap-1.5`}>
      <span className="font-semibold">💡</span>
      <span>{children}</span>
    </div>
  );
}
