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
  typeof window === "undefined"
    // Server-side (SSR/RSC): call VPS directly; on Vercel default to VPS IP.
    // Strip BOM/non-printables — Vercel env values can carry a BOM prefix
    // that makes fetch() reject the URL.
    ? (process.env.NEXT_PUBLIC_API_URL ||
       (process.env.VERCEL ? "http://165.232.178.128:8765" : "http://127.0.0.1:8765"))
        .replace(/[^\x20-\x7E]/g, "").trim()
    // Browser: always use /api proxy to avoid mixed-content (HTTPS → HTTP) blocks
    : "/api";

// fetch wrapper that injects the shared API key on SERVER-side calls only.
// Server (SSR/RSC) calls hit the VPS directly and must carry the key.
// Browser calls go through /api → the Next.js middleware injects the key there,
// so we must NOT expose it client-side (window defined → no header added).
export function efetch(input: string, init: Parameters<typeof fetch>[1] = {}): Promise<Response> {
  if (typeof window === "undefined" && process.env.EDGEKIT_API_KEY) {
    const apiKey = process.env.EDGEKIT_API_KEY.replace(/[^\x20-\x7E]/g, "");
    if (apiKey) {
      init = { ...init, headers: { ...(init?.headers || {}), "x-api-key": apiKey } };
    }
  }
  return fetch(input, init);
}

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
  avg_win: number; avg_loss: number; avg_rr: number; final_equity: number;
  sharpe?: number | null; sortino?: number | null;
  calmar?: number | null; cagr?: number | null;
  n_setups: number; n_unresolved: number;
  exit_counts: Record<string, number>;
};

export type ChallengeParams = {
  account_size:         number;  // e.g. 10000
  daily_loss_limit_pct: number;  // e.g. 5
  max_drawdown_pct:     number;  // e.g. 10
  profit_target_pct:    number;  // e.g. 10
  min_trading_days:     number;  // e.g. 4
};

export type ChallengeDayResult = {
  date: string; pnl_usd: number; equity: number;
  status: "ok" | "fail" | "target_hit";
};

export type ChallengeResult = {
  passed:          boolean;
  verdict:         string;
  failure_rule?:   string;
  failure_day?:    string;
  profit_hit_day?: string;
  trading_days:    number;
  final_equity:    number;
  account_size:    number;
  daily:           ChallengeDayResult[];
};

export type DataSource = {
  provider?: string;   // "mt5" | "yahoo" | "unknown"
  via?:      string;   // "terminal" | "bridge" | "fallback"
  symbol?:   string;
  label?:    string;   // e.g. "MT5 · XAUUSD" or "Yahoo (fallback) · GC=F"
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
  data_source?: DataSource;
  challenge?: ChallengeResult;
};

export async function listStrategies(): Promise<StrategySummary[]> {
  const r = await efetch(`${API_URL}/strategies`, { next: { revalidate: 300 } });
  if (!r.ok) throw new Error(`listStrategies: ${r.status}`);
  return r.json();
}

export async function runBacktest(body: any): Promise<BacktestResponse> {
  const r = await efetch(`${API_URL}/backtest`, {
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

export type V2UserNodeDef = {
  id:           string;
  type:         string;
  label:        string;
  description:  string;
  lane:         "indicator" | "alpha" | "filter" | "sizing" | "risk" | "exit";
  outputs:      { name: string; type: string }[];
  extra_inputs: { name: string; type: string }[];
  params_spec:  { key: string; label: string; type: "int" | "float"; default: number; min?: number; max?: number }[];
  formulas:     Record<string, string>;
  created_at:   number;
};

export type V2Graph = {
  name:       string;
  nodes:      V2GraphNode[];
  edges:      V2GraphEdge[];
  user_defs?: V2UserNodeDef[];
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
  const r = await efetch(`${API_URL}/graph/v2/symbols`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListSymbols: ${r.status}`);
  return r.json();
}

export async function v2ListNodes(): Promise<V2NodeSpec[]> {
  const r = await efetch(`${API_URL}/graph/v2/nodes`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListNodes: ${r.status}`);
  return r.json();
}

export async function v2ListTemplates(): Promise<TemplateSummary[]> {
  const r = await efetch(`${API_URL}/graph/v2/templates`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2ListTemplates: ${r.status}`);
  return r.json();
}

export async function v2GetTemplate(id: string): Promise<V2Graph> {
  const r = await efetch(`${API_URL}/graph/v2/templates/${id}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`v2GetTemplate: ${r.status}`);
  return r.json();
}

export async function v2Complexity(graph: V2Graph): Promise<V2Complexity> {
  const r = await efetch(`${API_URL}/graph/v2/complexity`, {
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
  timeframe: string;   // strategy TF (bars were run on this)
  pip:       number;
  bars:      ChartBar[];        // strategy-TF bars (used for trade idx mapping)
  view_bars?: ChartBar[];       // optional view-TF bars (used for candle display)
  view_tf?:   string;           // the view TF if different from timeframe
  trades:    ChartTrade[];
  n_setups:  number;
  indicators?: ChartIndicator[];   // optional — server may omit on old builds
  artifacts?:  ChartArtifact[];    // structural shapes: OB zones, FVG gaps, swept levels
  data_source?: DataSource;
};

// A structure the engine actually decided, for drawing on the chart.
export type ChartArtifact = {
  kind:        "zone" | "level" | "marker";
  node_id?:    string;
  node_type?:  string;
  lane?:       string;
  label?:      string;
  color_hint?: "bull" | "bear" | "neutral";
  // zone (rectangle): bar range + price band
  from_idx?:   number;
  to_idx?:     number;
  price_hi?:   number;
  price_lo?:   number;
  // level / marker: single price at a bar
  at_idx?:     number;
  price?:      number;
};

export async function v2ChartPreview(body: any): Promise<ChartPreview> {
  const r = await efetch(`${API_URL}/graph/v2/chart-preview`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `chart preview: ${r.status}`);
  return r.json();
}

// Read the user's AI key from localStorage (set on /resources).
// Supports any provider: gemini, anthropic, openai, groq, mistral.
function getUserAIKey(): { provider: string; key: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem("edgekit.aiKey.v1");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { provider: string; key: string };
    return parsed.provider && parsed.key ? parsed : null;
  } catch { return null; }
}

export function hasUserAIKey(): boolean {
  return !!getUserAIKey();
}

// The provider the user configured on /resources (gemini, anthropic, ...).
export function getAIProvider(): string {
  return getUserAIKey()?.provider ?? "gemini";
}

// Optional model override, chosen in the AI Strategy Builder. Empty = "Auto"
// (backend picks its default). Stored per-browser in localStorage.
const AI_MODEL_KEY = "edgekit.aiModel.v1";

export function getAIModel(): string {
  if (typeof window === "undefined") return "";
  try { return window.localStorage.getItem(AI_MODEL_KEY) ?? ""; }
  catch { return ""; }
}

export function setAIModel(model: string): void {
  if (typeof window === "undefined") return;
  try {
    if (model) window.localStorage.setItem(AI_MODEL_KEY, model);
    else        window.localStorage.removeItem(AI_MODEL_KEY);
  } catch { /* ignore */ }
}

// Model menu shown in the chat, keyed by provider.
export const AI_MODEL_OPTIONS: Record<string, { value: string; label: string }[]> = {
  gemini: [
    { value: "",                  label: "Auto (recommended)" },
    { value: "gemini-2.5-flash",  label: "Gemini 2.5 Flash" },
    { value: "gemini-2.5-pro",    label: "Gemini 2.5 Pro" },
    { value: "gemini-2.0-flash",  label: "Gemini 2.0 Flash" },
    { value: "gemini-1.5-flash",  label: "Gemini 1.5 Flash" },
    { value: "gemini-1.5-pro",    label: "Gemini 1.5 Pro" },
  ],
  anthropic: [
    { value: "",                        label: "Auto (recommended)" },
    { value: "claude-opus-4-1",         label: "Claude Opus 4.1 (most capable)" },
    { value: "claude-opus-4-20250514",  label: "Claude Opus 4" },
    { value: "claude-sonnet-4-5",       label: "Claude Sonnet 4.5" },
    { value: "claude-sonnet-4-20250514",label: "Claude Sonnet 4" },
    { value: "claude-3-7-sonnet-latest",label: "Claude 3.7 Sonnet" },
    { value: "claude-3-5-sonnet-latest",label: "Claude 3.5 Sonnet" },
    { value: "claude-3-5-haiku-latest", label: "Claude 3.5 Haiku (cheapest)" },
  ],
  openai: [
    { value: "",         label: "Auto (recommended)" },
    { value: "gpt-4o",   label: "GPT-4o" },
    { value: "gpt-4o-mini", label: "GPT-4o mini" },
  ],
  groq: [
    { value: "", label: "Auto (recommended)" },
    { value: "llama-3.3-70b-versatile", label: "Llama 3.3 70B" },
  ],
  mistral: [
    { value: "", label: "Auto (recommended)" },
    { value: "mistral-large-latest", label: "Mistral Large" },
  ],
};

/** @deprecated use hasUserAIKey */
export function hasUserGeminiKey(): boolean {
  return hasUserAIKey();
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

export async function v2NodeChat(body: {
  messages: ChatMessage[];
}): Promise<{ type: "message"; content: string } | { type: "node_def"; def: any }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ai = getUserAIKey();
  if (ai) { headers["X-AI-Key"] = ai.key; headers["X-AI-Provider"] = ai.provider; }
  const model = getAIModel();
  if (model) headers["X-AI-Model"] = model;
  const r = await efetch(`${API_URL}/graph/v2/node-chat`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function v2NodeFromText(description: string): Promise<{
  label: string; description: string; lane: "indicator";
  outputs: { name: string; type: "number" | "series" }[];
  params_spec: { key: string; label: string; type: "int" | "float"; default: number; min?: number; max?: number }[];
  formulas: Record<string, string>;
}> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ai = getUserAIKey();
  if (ai) {
    headers["X-AI-Key"]      = ai.key;
    headers["X-AI-Provider"] = ai.provider;
  }
  const r = await efetch(`${API_URL}/graph/v2/node-from-text`, {
    method:  "POST",
    headers,
    body:    JSON.stringify({ description }),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function v2FromText(body: { description: string; symbol?: string; timeframe?: string; image?: string }): Promise<V2Graph> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ai = getUserAIKey();
  if (ai) {
    headers["X-AI-Key"]      = ai.key;
    headers["X-AI-Provider"] = ai.provider;
  }

  const r = await efetch(`${API_URL}/graph/v2/from-text`, {
    method:  "POST",
    headers,
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type GraphDecisionSetting = {
  key: string; label: string; value: any; default: any; is_default: boolean;
  /** true = value came from the user's own words; false = AI assumed it */
  user_specified?: boolean;
  // Editing metadata (mirrors the node's ParamSpec) so the review panel can
  // render the right input control.
  type?: "int" | "float" | "select" | "string" | "bool";
  min?: number | null;
  max?: number | null;
  step?: number | null;
  options?: string[] | null;
};
export type GraphDecision = {
  node_id: string; node_label: string; lane: string;
  settings: GraphDecisionSetting[];
};
export type ChatResponse =
  | { type: "message"; content: string }
  | { type: "graph"; graph: V2Graph; decisions?: GraphDecision[]; open_questions?: string[] };

export async function v2Chat(body: {
  messages:  ChatMessage[];
  symbol?:   string;
  timeframe?: string;
  current_graph?:  V2Graph | null;
  result_summary?: string | null;
  image?:    string;
}): Promise<ChatResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ai = getUserAIKey();
  if (ai) {
    headers["X-AI-Key"]      = ai.key;
    headers["X-AI-Provider"] = ai.provider;
  }
  const model = getAIModel();
  if (model) headers["X-AI-Model"] = model;
  const r = await efetch(`${API_URL}/graph/v2/chat`, {
    method:  "POST",
    headers,
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export type ExplainErrorResponse = { explanation: string; suggestions: string[] };

/** Turn a raw backtest/setup error into a plain-language explanation plus a few
 *  AI-generated fix suggestions. Uses the user's AI key when set, else the
 *  server's. Throws on failure (e.g. no key) so callers can show a fallback. */
export async function v2ExplainError(body: {
  error: string;
  graph?: V2Graph | null;
  symbol?: string;
  timeframe?: string;
}): Promise<ExplainErrorResponse> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const ai = getUserAIKey();
  if (ai) { headers["X-AI-Key"] = ai.key; headers["X-AI-Provider"] = ai.provider; }
  const model = getAIModel();
  if (model) headers["X-AI-Model"] = model;
  const r = await efetch(`${API_URL}/graph/v2/explain-error`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function getGlobalStats(): Promise<{ total_backtests: number; total_users: number }> {
  const r = await efetch(`${API_URL}/stats/global`, { next: { revalidate: 60 } } as any);
  if (!r.ok) return { total_backtests: 0, total_users: 0 };
  return r.json();
}

export async function v2ExportPineScript(body: any): Promise<{ code: string; lines: number }> {
  const r = await efetch(`${API_URL}/graph/v2/pinescript`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `pinescript: ${r.status}`);
  return r.json();
}

export async function v2RunBacktest(body: any): Promise<BacktestResponse> {
  const r = await efetch(`${API_URL}/graph/v2/backtest`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export type SweepParamRange = { node_id: string; param_key: string; values: any[] };
export type SweepResultRow  = { params: Record<string, any>; trades: number; wr: number; total_r: number; profit_factor: number; max_dd: number; sharpe?: number | null; sortino?: number | null };

export async function v2Sweep(body: {
  graph: V2Graph; param_ranges: SweepParamRange[];
  data_source?: string; symbol?: string; timeframe?: string; n_bars?: number;
  csv_data_id?: string; target_r?: number; trail_mode?: string;
  spread_pips?: number; commission?: number; slippage_pips?: number;
}): Promise<{ results: SweepResultRow[]; combinations_tried: number }> {
  const r = await efetch(`${API_URL}/graph/v2/sweep`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function v2WalkForward(body: {
  graph: V2Graph; data_source?: string; symbol?: string; timeframe?: string;
  n_bars?: number; csv_data_id?: string; n_splits?: number; is_pct?: number;
  target_r?: number; trail_mode?: string; spread_pips?: number; commission?: number;
}): Promise<{ windows: any[]; oos_equity: number[]; n_splits: number }> {
  const r = await efetch(`${API_URL}/graph/v2/walk-forward`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}

export async function v2MonteCarlo(body: {
  graph: V2Graph; data_source?: string; symbol?: string; timeframe?: string;
  n_bars?: number; csv_data_id?: string; n_sims?: number;
  target_r?: number; trail_mode?: string; spread_pips?: number; commission?: number;
}): Promise<{ n_sims: number; n_trades: number; percentiles: Record<string, number[]>; base_metrics: any }> {
  const r = await efetch(`${API_URL}/graph/v2/monte-carlo`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await readApiError(r));
  return r.json();
}


// ─── Forward (paper) testing ──────────────────────────────────────────────
export type ForwardMetrics = {
  trades: number; wr: number; ev?: number; total_r?: number;
  profit_factor?: number; max_dd?: number; final_equity?: number;
  // live (Grade-3) only:
  total_profit?: number; open_positions?: number;
};
export type ForwardLatest = {
  mode?:    "sim" | "live_demo";
  metrics?: ForwardMetrics;
  costs?:   { total_spread?: number; total_slippage?: number };
  trades?:  any[];
  equity?:  number[];
  bars_seen?: number;
  data_source?: DataSource;
  last_run?: string;
  error?: string;
  events?: number;
};
export type ForwardTest = {
  id: number; name: string; symbol: string; timeframe: string; status: string;
  mode?: "sim" | "live_demo";
  started_at?: string; created_at?: string; updated_at?: string;
  baseline?: Record<string, any>;
  latest?: ForwardLatest;
};

export async function forwardStart(body: {
  graph: V2Graph; name?: string; symbol?: string; timeframe?: string;
  mode?: "sim" | "live_demo";
  mgmt?: Record<string, any>; baseline?: Record<string, any>;
}): Promise<ForwardTest> {
  const r = await efetch(`${API_URL}/forward/start`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await readApiError(r)) || `forward start: ${r.status}`);
  return r.json();
}
export async function forwardList(): Promise<ForwardTest[]> {
  const r = await efetch(`${API_URL}/forward/list`, { cache: "no-store" });
  if (!r.ok) throw new Error(`forward list: ${r.status}`);
  return r.json();
}
export async function forwardRefresh(id: number): Promise<ForwardTest> {
  const r = await efetch(`${API_URL}/forward/${id}/refresh`, { method: "POST" });
  if (!r.ok) throw new Error(`forward refresh: ${r.status}`);
  return r.json();
}
export async function forwardStop(id: number): Promise<ForwardTest> {
  const r = await efetch(`${API_URL}/forward/${id}/stop`, { method: "POST" });
  if (!r.ok) throw new Error(`forward stop: ${r.status}`);
  return r.json();
}

export async function forwardGenerateBridgeToken(): Promise<{ token: string; vps_url: string }> {
  const r = await efetch(`${API_URL}/forward/bridge/token`, { method: "POST" });
  if (!r.ok) throw new Error(`generate bridge token: ${r.status}`);
  return r.json();
}
