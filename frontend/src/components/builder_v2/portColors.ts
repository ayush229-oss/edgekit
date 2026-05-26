// Single source of truth for port-type → color, used by node handles,
// palette legends, and the connection validator's UI feedback.

import type { V2PortType, V2Lane } from "@/lib/api";

export const PORT_COLORS: Record<V2PortType, { bg: string; ring: string; label: string }> = {
  number:    { bg: "#5A8DEE", ring: "#5A8DEE", label: "Number"    },
  series:    { bg: "#2C5C9E", ring: "#2C5C9E", label: "Series"    },
  direction: { bg: "#6B9B7A", ring: "#6B9B7A", label: "Direction" },
  insight:   { bg: "#D4A574", ring: "#D4A574", label: "Insight"   },
  target:    { bg: "#C97B63", ring: "#C97B63", label: "Target"    },
  adjusted:  { bg: "#9E4A3B", ring: "#9E4A3B", label: "Adjusted"  },
  order:     { bg: "#2C3E36", ring: "#2C3E36", label: "Order"     },
  symbol:    { bg: "#8A8071", ring: "#8A8071", label: "Symbol"    },
  context:   { bg: "#A8A095", ring: "#A8A095", label: "Context"   },
};

export const LANE_META: Record<V2Lane, { label: string; chip: string; order: number; hint: string }> = {
  universe:  { label: "Universe",  chip: "bg-cream3 text-ink",  order: 0,
               hint: "Which asset are we trading?" },
  indicator: { label: "Indicator", chip: "bg-sky-100 text-sky-800", order: 1,
               hint: "Pure compute — numbers in, numbers out" },
  alpha:     { label: "Alpha",     chip: "bg-amber/30 text-amber-900", order: 2,
               hint: "Generate the trade idea (Insight)" },
  filter:    { label: "Filter",    chip: "bg-yellow-100 text-yellow-800", order: 3,
               hint: "Block or pass insights conditionally" },
  sizing:    { label: "Sizing",    chip: "bg-sage/30 text-sage", order: 4,
               hint: "How much to risk" },
  risk:      { label: "Risk",      chip: "bg-terra/30 text-terra", order: 5,
               hint: "Initial stop loss" },
  exit:      { label: "Exit",      chip: "bg-rose-200 text-rose-900", order: 6,
               hint: "Targets, trails, time-outs (stackable)" },
  execution: { label: "Execution", chip: "bg-ink/15 text-ink",  order: 7,
               hint: "How the order is placed" },
};

export function laneAccentColor(lane: V2Lane): string {
  return ({
    universe:  "#8A8071",
    indicator: "#5A8DEE",
    alpha:     "#D4A574",
    filter:    "#E6C84D",
    sizing:    "#6B9B7A",
    risk:      "#C97B63",
    exit:      "#E47BA0",
    execution: "#2C3E36",
  } as Record<V2Lane, string>)[lane];
}
