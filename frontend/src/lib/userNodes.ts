/**
 * User-defined nodes — stored in localStorage per browser.
 *
 * Supports all lanes: indicator, alpha, filter, sizing, risk, exit.
 * The formula approach differs per lane:
 *
 *   indicator  — returns a scalar (number) or full array (series) per output port
 *   alpha      — single "main" formula returns "Bull", "Bear", or None
 *   filter     — single "main" formula returns True (pass) or False (block)
 *   sizing     — single "main" formula returns a risk fraction (0.0–1.0)
 *   risk       — single "main" formula returns SL distance in pips
 *   exit       — single "main" formula returns target R multiple
 *
 * The def is serialised into V2Graph.user_defs when sent to the backend.
 */
import type { V2NodeSpec } from "@/lib/api";

const STORAGE_KEY = "edgekit.userNodes.v1";

export type UserLane = "indicator" | "alpha" | "filter" | "sizing" | "risk" | "exit";

export type UserPortDef = {
  name: string;
  type: "number" | "series" | "insight" | "target" | "adjusted";
};

export type UserParamDef = {
  key:     string;
  label:   string;
  type:    "int" | "float";
  default: number;
  min?:    number;
  max?:    number;
  step?:   number;
};

export type UserNodeDef = {
  id:           string;
  type:         string;            // "user.<id>"
  label:        string;
  description:  string;
  lane:         UserLane;
  outputs:      UserPortDef[];     // indicator only — other lanes are auto
  extra_inputs: UserPortDef[];     // additional wired inputs beyond lane defaults
  params_spec:  UserParamDef[];
  formulas:     Record<string, string>;  // indicator: {port_name: expr}; others: {main: expr}
  created_at:   number;
};

// Lane colours (match the existing portColors palette)
export const LANE_COLORS: Record<UserLane, string> = {
  indicator: "#3B82F6",
  alpha:     "#8B5CF6",
  filter:    "#F59E0B",
  sizing:    "#10B981",
  risk:      "#EF4444",
  exit:      "#F97316",
};

export const LANE_DESCRIPTIONS: Record<UserLane, string> = {
  indicator: "Computes a value or series from price data. Wire to Alpha nodes.",
  alpha:     "Generates Bull/Bear signals from wired indicator values.",
  filter:    "Passes or blocks incoming signals based on a condition.",
  sizing:    "Returns a risk fraction (e.g. 0.02 = 2% of equity).",
  risk:      "Returns a stop-loss distance in pips.",
  exit:      "Returns a target R multiple (e.g. 3.0).",
};

export const FORMULA_VARS: Record<UserLane, { name: string; desc: string }[]> = {
  indicator: [
    { name: "close",   desc: "Close price array" },
    { name: "open",    desc: "Open price array" },
    { name: "high",    desc: "High price array" },
    { name: "low",     desc: "Low price array" },
    { name: "volume",  desc: "Volume array" },
    { name: "i",       desc: "Current bar index" },
    { name: "pip",     desc: "Instrument pip size" },
    { name: "np",      desc: "NumPy" },
    { name: "pd",      desc: "Pandas" },
  ],
  alpha: [
    { name: "close",      desc: "Close array (up to bar i)" },
    { name: "high",       desc: "High array" },
    { name: "low",        desc: "Low array" },
    { name: "i",          desc: "Current bar index" },
    { name: "pip",        desc: "Pip size" },
    { name: "<input>",    desc: "Any wired extra input by name" },
  ],
  filter: [
    { name: "close",      desc: "Close array" },
    { name: "i",          desc: "Current bar index" },
    { name: "direction",  desc: '"Bull" or "Bear" (from insight)' },
    { name: "confidence", desc: "Insight confidence (0–1)" },
    { name: "pip",        desc: "Pip size" },
    { name: "<input>",    desc: "Any wired extra input by name" },
  ],
  sizing: [
    { name: "close",      desc: "Close array" },
    { name: "direction",  desc: '"Bull" or "Bear"' },
    { name: "confidence", desc: "Signal confidence (0–1)" },
    { name: "pip",        desc: "Pip size" },
    { name: "<input>",    desc: "Any wired extra input by name" },
  ],
  risk: [
    { name: "close",      desc: "Close array" },
    { name: "entry_px",   desc: "Planned entry price" },
    { name: "direction",  desc: '"Bull" or "Bear"' },
    { name: "pip",        desc: "Pip size" },
    { name: "<input>",    desc: "Any wired extra input by name" },
  ],
  exit: [
    { name: "close",      desc: "Close array" },
    { name: "entry_px",   desc: "Entry price" },
    { name: "direction",  desc: '"Bull" or "Bear"' },
    { name: "pip",        desc: "Pip size" },
    { name: "<input>",    desc: "Any wired extra input by name" },
  ],
};

export const FORMULA_EXAMPLES: Record<UserLane, { label: string; expr: string }[]> = {
  indicator: [
    { label: "Last close",      expr: "close[-1]" },
    { label: "SMA(period)",     expr: "pd.Series(close).rolling(period).mean().values" },
    { label: "Momentum",        expr: "close[-1] - close[-period] if len(close) > period else 0" },
    { label: "ATR approx",      expr: "pd.Series(high - low).rolling(period).mean().values" },
    { label: "EWM mean",        expr: "pd.Series(close).ewm(span=period).mean().values" },
  ],
  alpha: [
    { label: "Price vs SMA",    expr: '"Bull" if close[-1] > close[-period] else ("Bear" if close[-1] < close[-period] else None)' },
    { label: "Crossover",       expr: '"Bull" if close[-2] < close[-period-1] and close[-1] > close[-period] else ("Bear" if close[-2] > close[-period-1] and close[-1] < close[-period] else None)' },
    { label: "Use wired value", expr: '"Bull" if ema_fast > ema_slow else ("Bear" if ema_fast < ema_slow else None)' },
    { label: "Threshold cross", expr: '"Bull" if rsi_value < 30 else ("Bear" if rsi_value > 70 else None)' },
  ],
  filter: [
    { label: "Session hours",   expr: "8 <= i % 24 <= 20" },
    { label: "ATR range gate",  expr: "min_atr <= atr_value <= max_atr" },
    { label: "Trend aligned",   expr: '(direction == "Bull" and close[-1] > close[-20]) or (direction == "Bear" and close[-1] < close[-20])' },
    { label: "Always pass",     expr: "True" },
  ],
  sizing: [
    { label: "Fixed 1% risk",   expr: "0.01" },
    { label: "Volatility-adj",  expr: "min(0.02, 0.005 / max((high[-1] - low[-1]) / close[-1], 0.001))" },
    { label: "Confidence-based",expr: "confidence * 0.02" },
  ],
  risk: [
    { label: "Fixed 20 pips",   expr: "20.0" },
    { label: "ATR × 1.5",       expr: "atr_value / pip * 1.5" },
    { label: "Prior bar range",  expr: "(high[-2] - low[-2]) / pip" },
  ],
  exit: [
    { label: "Fixed 3R",        expr: "3.0" },
    { label: "ATR-based",       expr: "max(2.0, atr_value / pip / 10)" },
    { label: "Volatility-adj",  expr: "3.0 if (high[-1] - low[-1]) < pd.Series(high - low).rolling(20).mean().values[-1] else 2.0" },
  ],
};

/** Convert a UserNodeDef to the V2NodeSpec shape the canvas/palette expect. */
export function toV2NodeSpec(def: UserNodeDef): V2NodeSpec {
  // For non-indicator lanes, auto-derive ports from lane conventions
  let inputs: V2NodeSpec["inputs"] = [];
  let outputs: V2NodeSpec["outputs"] = [];

  const extraInputs = def.extra_inputs ?? [];

  if (def.lane === "indicator") {
    inputs  = extraInputs.map((p) => ({ name: p.name, type: p.type as any }));
    outputs = (def.outputs ?? []).map((p) => ({ name: p.name, type: p.type as any }));
  } else {
    // Standard inputs per lane
    const stdInputs: Record<string, { name: string; type: string } | null> = {
      alpha:  null,
      filter: { name: "insight",  type: "insight"  },
      sizing: { name: "insight",  type: "insight"  },
      risk:   { name: "target",   type: "target"   },
      exit:   { name: "adjusted", type: "adjusted" },
    };
    const stdInput = stdInputs[def.lane];
    if (stdInput) {
      inputs = [{ name: stdInput.name, type: stdInput.type as any }];
    }
    inputs = [...inputs, ...extraInputs.map((p) => ({ name: p.name, type: p.type as any }))];

    // Standard outputs per lane
    const stdOutput: Record<string, { name: string; type: string }> = {
      alpha:  { name: "insight",  type: "insight"  },
      filter: { name: "insight",  type: "insight"  },
      sizing: { name: "target",   type: "target"   },
      risk:   { name: "adjusted", type: "adjusted" },
      exit:   { name: "adjusted", type: "adjusted" },
    };
    const so = stdOutput[def.lane];
    if (so) outputs = [{ name: so.name, type: so.type as any }];
  }

  return {
    type:        def.type,
    lane:        def.lane as any,
    label:       def.label,
    description: def.description,
    inputs,
    outputs,
    params:      (def.params_spec ?? []).map((p) => ({
      key:         p.key,
      label:       p.label,
      type:        p.type,
      default:     p.default,
      description: "",
      group:       "General",
      ...(p.min  !== undefined && { min:  p.min }),
      ...(p.max  !== undefined && { max:  p.max }),
      ...(p.step !== undefined && { step: p.step }),
    })),
  };
}

function safeRead(): UserNodeDef[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch { return []; }
}

function safeWrite(nodes: UserNodeDef[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nodes));
    window.dispatchEvent(new CustomEvent("edgekit:userNodes:changed"));
  } catch { /* quota */ }
}

export function listUserNodes(): UserNodeDef[] {
  return safeRead().sort((a, b) => b.created_at - a.created_at);
}

export function getUserNode(id: string): UserNodeDef | undefined {
  return safeRead().find((n) => n.id === id);
}

export function saveUserNode(
  input: Omit<UserNodeDef, "id" | "type" | "created_at"> & { id?: string },
): UserNodeDef {
  const all = safeRead();
  const id  = input.id ?? `un_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
  const next: UserNodeDef = {
    ...input,
    id,
    type:       `user.${id}`,
    label:      input.label.trim() || "Untitled node",
    description: input.description.trim(),
    created_at: Date.now(),
  };
  safeWrite([next, ...all.filter((n) => n.id !== id)]);
  return next;
}

export function deleteUserNode(id: string) {
  safeWrite(safeRead().filter((n) => n.id !== id));
}

export function onUserNodesChange(handler: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const inPage = () => handler();
  const cross  = (e: StorageEvent) => { if (e.key === STORAGE_KEY) handler(); };
  window.addEventListener("edgekit:userNodes:changed", inPage);
  window.addEventListener("storage", cross);
  return () => {
    window.removeEventListener("edgekit:userNodes:changed", inPage);
    window.removeEventListener("storage", cross);
  };
}
