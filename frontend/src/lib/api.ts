// Edgekit API client — thin fetch wrapper.
//
// API_URL resolution strategy:
//   • Browser:  /api  → goes through Next.js rewrite to the backend.
//               This way the friend-shareable Cloudflare tunnel only needs
//               port 3000 exposed; backend stays internal.
//   • Server:   http://127.0.0.1:8765  → direct, because Node's fetch can't
//               resolve relative URLs and the SSR runner is on the same box
//               as the backend anyway.
//   • Override: set NEXT_PUBLIC_API_URL to force a specific origin
//               (e.g. when hosting backend on a different domain).
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== "/api"
    ? process.env.NEXT_PUBLIC_API_URL
    : (typeof window === "undefined" ? "http://127.0.0.1:8765" : "/api");

export type ParamSpec = {
  key: string; label: string; type: "int" | "float" | "select" | "bool";
  default: any; min?: number; max?: number; step?: number;
  options?: any[]; description: string; group: string;
};

export type StrategySummary = {
  id: string; name: string; description: string;
  timeframes: string[]; instruments: string[]; params: ParamSpec[];
};

export type BacktestMetrics = {
  trades: number; wr: number; ev: number; total_r: number;
  profit_factor: number; max_dd: number;
  avg_win: number; avg_loss: number; final_equity: number;
  n_setups: number; n_unresolved: number;
  exit_counts: Record<string, number>;
};

export type BacktestResponse = {
  strategy_id: string;
  data_range: [string, string];
  bars: number;
  pip: number;
  metrics: BacktestMetrics;
  equity_curve: number[];
  pnl_series:   number[];
  issues: Record<string, any>;
};

export async function listStrategies(): Promise<StrategySummary[]> {
  const r = await fetch(`${API_URL}/strategies`, { next: { revalidate: 300 } });
  if (!r.ok) throw new Error(`listStrategies: ${r.status}`);
  return r.json();
}

export async function runBacktest(body: any): Promise<BacktestResponse> {
  const r = await fetch(`${API_URL}/backtest`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `backtest: ${r.status}`);
  return r.json();
}


// ─── Visual node builder ────────────────────────────────────────────────────
export type NodeCategory = "signal" | "filter" | "entry" | "risk";

export type NodeSpec = {
  type:        string;
  category:    NodeCategory;
  label:       string;
  description: string;
  params:      ParamSpec[];
};

export type GraphNode = {
  id:       string;
  type:     string;
  params:   Record<string, any>;
  position?: { x: number; y: number };
};

export type GraphEdge = { from: string; to: string };

export type StrategyGraph = {
  name:  string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type TemplateSummary = {
  id:          string;
  name:        string;
  description: string;
};

export async function listNodeLibrary(): Promise<NodeSpec[]> {
  const r = await fetch(`${API_URL}/graph/nodes`, { cache: "no-store" });
  if (!r.ok) throw new Error(`listNodeLibrary: ${r.status}`);
  return r.json();
}

export async function listGraphTemplates(): Promise<TemplateSummary[]> {
  const r = await fetch(`${API_URL}/graph/templates`, { cache: "no-store" });
  if (!r.ok) throw new Error(`listGraphTemplates: ${r.status}`);
  return r.json();
}

export async function getGraphTemplate(id: string): Promise<StrategyGraph> {
  const r = await fetch(`${API_URL}/graph/templates/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`getGraphTemplate: ${r.status}`);
  return r.json();
}

export async function runGraphBacktest(body: any): Promise<BacktestResponse> {
  const r = await fetch(`${API_URL}/graph/backtest`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `graph backtest: ${r.status}`);
  return r.json();
}


// ─── v2 graph builder — typed-port, multi-lane ──────────────────────────────
export type V2PortType =
  | "number" | "series" | "direction" | "insight" | "target"
  | "adjusted" | "order" | "symbol" | "context";

export type V2Lane =
  | "universe" | "indicator" | "alpha" | "filter"
  | "sizing"   | "risk"      | "exit"  | "execution";

export type V2Port = { name: string; type: V2PortType };

export type V2NodeSpec = {
  type:        string;
  lane:        V2Lane;
  label:       string;
  description: string;
  inputs:      V2Port[];
  outputs:     V2Port[];
  params:      ParamSpec[];
};

export type V2GraphNode = {
  id:        string;
  type:      string;
  params:    Record<string, any>;
  position?: { x: number; y: number };
};

export type V2GraphEdge = {
  from:      string;
  to:        string;
  from_port: string;
  to_port:   string;
};

export type V2Graph = {
  name:  string;
  nodes: V2GraphNode[];
  edges: V2GraphEdge[];
};

export type V2Complexity = {
  score:       number;
  params:      number;
  alpha_count: number;
  level:       "green" | "amber" | "red";
  message:     string;
};


export type SymbolInfo = {
  symbol:      string;
  description: string;
  category:    string;
};

export async function v2ListSymbols(): Promise<{ source: "mt5" | "static"; symbols: SymbolInfo[] }> {
  const r = await fetch(`${API_URL}/graph/v2/symbols`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListSymbols: ${r.status}`);
  return r.json();
}

export async function v2ListNodes(): Promise<V2NodeSpec[]> {
  const r = await fetch(`${API_URL}/graph/v2/nodes`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListNodes: ${r.status}`);
  return r.json();
}

export async function v2ListTemplates(): Promise<TemplateSummary[]> {
  const r = await fetch(`${API_URL}/graph/v2/templates`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListTemplates: ${r.status}`);
  return r.json();
}

export async function v2GetTemplate(id: string): Promise<V2Graph> {
  const r = await fetch(`${API_URL}/graph/v2/templates/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2GetTemplate: ${r.status}`);
  return r.json();
}

export async function v2Complexity(graph: V2Graph): Promise<V2Complexity> {
  const r = await fetch(`${API_URL}/graph/v2/complexity`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ graph }),
  });
  if (!r.ok) throw new Error(`v2Complexity: ${r.status}`);
  return r.json();
}

export type ChartBar = { t: number; o: number; h: number; l: number; c: number };
export type ChartTrade = {
  signal_idx: number;
  fill_idx:   number | null;
  exit_idx:   number | null;
  direction:  "Bull" | "Bear";
  entry:      number;
  sl:         number;
  result:     string;
  exit_type:  string;
  pnl_r:      number;
};
export type ChartIndicator = {
  id:         string;
  node_id:    string;
  node_type:  string;
  label:      string;
  color:      string;
  line_style: "solid" | "dashed" | "dotted";
  line_width: number;
  values:     (number | null)[];   // bar-aligned, NaN/warmup = null
};

export type ChartPreview = {
  symbol:    string;
  timeframe: string;
  pip:       number;
  bars:      ChartBar[];
  trades:    ChartTrade[];
  n_setups:  number;
  indicators?: ChartIndicator[];   // optional — server may omit on old builds
};

export async function v2ChartPreview(body: any): Promise<ChartPreview> {
  const r = await fetch(`${API_URL}/graph/v2/chart-preview`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `chart preview: ${r.status}`);
  return r.json();
}

// Read the user's Gemini key from localStorage (set on /resources). Sent as
// an X-Gemini-Key header so the backend can use it without us needing a
// server-side env var.
function getUserGeminiKey(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("edgekit.aiKey.v1");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { provider: string; key: string };
    return parsed.provider === "gemini" && parsed.key ? parsed.key : null;
  } catch { return null; }
}

export function hasUserGeminiKey(): boolean {
  return !!getUserGeminiKey();
}

// Pull the clean error reason out of FastAPI's standard response envelope.
// FastAPI wraps HTTPExceptions as `{"detail": "<message>"}`, but raw 500s
// from unhandled exceptions are just plain text. Handle both gracefully.
async function readApiError(r: Response): Promise<string> {
  const raw = await r.text();
  if (!raw) return `${r.status} ${r.statusText || "request failed"}`;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed?.detail === "string") return parsed.detail;
    if (Array.isArray(parsed?.detail))      return parsed.detail.map((d: any) => d.msg || JSON.stringify(d)).join("; ");
    return raw;
  } catch {
    return raw;
  }
}

export async function v2FromText(body: { description: string; symbol?: string; timeframe?: string }): Promise<V2Graph> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const k = getUserGeminiKey();
  if (k) headers["X-Gemini-Key"] = k;

  const r = await fetch(`${API_URL}/graph/v2/from-text`, {
    method:  "POST",
    headers,
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function v2ExportPineScript(body: any): Promise<{ code: string; lines: number }> {
  const r = await fetch(`${API_URL}/graph/v2/pinescript`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `pinescript: ${r.status}`);
  return r.json();
}

export async function v2RunBacktest(body: any): Promise<BacktestResponse> {
  const r = await fetch(`${API_URL}/graph/v2/backtest`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `v2 backtest: ${r.status}`);
  return r.json();
}
