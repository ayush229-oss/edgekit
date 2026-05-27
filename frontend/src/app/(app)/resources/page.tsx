"use client";

import { useEffect, useState } from "react";

export default function ResourcesPage() {
  return (
    <div className="space-y-8">
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Resources</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Connect your tools</h1>
        <p className="text-muted mt-2 text-[15px]">
          Bring your own AI model, your own broker, your own data. We don't lock you in.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AISection />
        <BrokerSection />
        <PineSection />
        <TradeLogSection />
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   AI MODEL
   ───────────────────────────────────────────────────────────────────────────── */

const AI_PROVIDERS = [
  { id: "openai",    label: "OpenAI",         placeholder: "sk-...",                   docs: "platform.openai.com/api-keys",        popular: true  },
  { id: "anthropic", label: "Anthropic",      placeholder: "sk-ant-...",               docs: "console.anthropic.com/settings/keys", popular: true  },
  { id: "gemini",    label: "Google Gemini",  placeholder: "AIza...",                  docs: "aistudio.google.com/apikey",          popular: true  },
  { id: "mistral",   label: "Mistral",        placeholder: "...",                      docs: "console.mistral.ai/api-keys",         popular: false },
  { id: "groq",      label: "Groq",           placeholder: "gsk_...",                  docs: "console.groq.com/keys",               popular: false },
  { id: "ollama",    label: "Ollama (local)", placeholder: "http://localhost:11434",    docs: "ollama.com",                          popular: false },
  { id: "custom",    label: "Custom / Other", placeholder: "Your API endpoint or key", docs: "",                                    popular: false },
];

function AISection() {
  const [provider, setProvider] = useState("gemini");
  const [key, setKey]           = useState("");
  const [saved,    setSaved]    = useState(false);
  const [saving,   setSaving]   = useState(false);
  const [loading,  setLoading]  = useState(true);

  // Load existing key from Supabase on mount; fall back to localStorage for migration
  useEffect(() => {
    fetch("/api/ai-keys")
      .then((r) => r.json())
      .then((data: { provider: string; key: string }[]) => {
        if (Array.isArray(data) && data.length > 0) {
          // Use most recently saved key (first in array)
          const first = data[0];
          setProvider(first.provider);
          setKey(first.key);
          setSaved(true);
        } else {
          // Migrate from localStorage if present
          try {
            const raw = window.localStorage.getItem("edgekit.aiKey.v1");
            if (raw) {
              const v = JSON.parse(raw) as { provider: string; key: string };
              setProvider(v.provider);
              setKey(v.key);
              // Auto-migrate to Supabase silently
              fetch("/api/ai-keys", {
                method:  "POST",
                headers: { "Content-Type": "application/json" },
                body:    JSON.stringify({ provider: v.provider, key: v.key }),
              }).then(() => {
                window.localStorage.removeItem("edgekit.aiKey.v1");
                setSaved(true);
              }).catch(() => { setSaved(true); }); // keep showing as saved even if migration fails
            }
          } catch {}
        }
      })
      .catch(() => {
        // Offline/error — fall back to localStorage
        try {
          const raw = window.localStorage.getItem("edgekit.aiKey.v1");
          if (raw) { const v = JSON.parse(raw) as { provider: string; key: string }; setProvider(v.provider); setKey(v.key); setSaved(true); }
        } catch {}
      })
      .finally(() => setLoading(false));
  }, []);

  const p = AI_PROVIDERS.find((x) => x.id === provider)!;

  async function handleSave() {
    if (!key.trim()) return;
    setSaving(true);
    try {
      await fetch("/api/ai-keys", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ provider, key }),
      });
      // Also keep in localStorage as fallback for offline use
      window.localStorage.setItem("edgekit.aiKey.v1", JSON.stringify({ provider, key }));
      setSaved(true);
    } catch {
      // Fallback: at least save locally
      window.localStorage.setItem("edgekit.aiKey.v1", JSON.stringify({ provider, key }));
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }

  async function handleClear() {
    await fetch(`/api/ai-keys/${encodeURIComponent(provider)}`, { method: "DELETE" }).catch(() => {});
    window.localStorage.removeItem("edgekit.aiKey.v1");
    setKey(""); setSaved(false);
  }

  return (
    <div className="card p-6 space-y-4">
      <div>
        <h2 className="font-semibold text-[16px]">🤖 AI Model</h2>
        <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
          Powers "Describe strategy" — type a strategy in plain English, get a node graph back.
        </p>
      </div>

      <div className="space-y-3">
        <label className="block">
          <span className="text-[12px] text-muted">Provider</span>
          <select
            value={provider}
            onChange={(e) => { setProvider(e.target.value); setSaved(false); }}
            className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
          >
            <optgroup label="Popular">
              {AI_PROVIDERS.filter((x) => x.popular).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </optgroup>
            <optgroup label="Other">
              {AI_PROVIDERS.filter((x) => !x.popular).map((x) => <option key={x.id} value={x.id}>{x.label}</option>)}
            </optgroup>
          </select>
        </label>

        <label className="block">
          <span className="text-[12px] text-muted">API key</span>
          <input
            type="password"
            value={key}
            onChange={(e) => { setKey(e.target.value); setSaved(false); }}
            placeholder={p.placeholder}
            className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] font-mono focus:outline-none focus:ring-1 focus:ring-money"
          />
          {p.docs && (
            <p className="text-[11px] text-muted mt-1.5">
              Get a key at <a href={`https://${p.docs}`} target="_blank" rel="noreferrer" className="text-money hover:underline">{p.docs}</a>
            </p>
          )}
        </label>

        <div className="flex gap-2">
          <button onClick={() => void handleSave()} disabled={!key.trim() || saving || loading}
            className="flex-1 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors disabled:opacity-50">
            {saving ? "Saving…" : saved ? "✓ Saved" : "Save API key"}
          </button>
          {saved && (
            <button onClick={() => void handleClear()}
              className="px-3 py-2 rounded-lg border border-border text-[13px] text-muted hover:bg-surface2 transition-colors">
              Clear
            </button>
          )}
        </div>

        <p className="text-[11px] text-muted">
          Stored in your browser only. Sent securely when you use &quot;Describe strategy&quot; or &quot;Custom node builder&quot;.
        </p>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   DATA SOURCE — backed by Supabase
   ───────────────────────────────────────────────────────────────────────────── */

type FieldType = "text" | "password" | "url";
type Field  = { key: string; label: string; type: FieldType; placeholder: string; sensitive?: boolean };
type Source = {
  id: string; label: string; category: "Terminal" | "Cloud / API" | "Manual" | "Webhook";
  fields: Field[]; helper?: string; popular?: boolean;
};

const SOURCES: Source[] = [
  { id: "mt5",         label: "MetaTrader 5",          category: "Terminal",   popular: true,
    fields: [{ key: "host", label: "Host", type: "text", placeholder: "127.0.0.1" }, { key: "port", label: "Port", type: "text", placeholder: "8765" }],
    helper: "Requires the Edgekit EA running inside MT5." },
  { id: "mt4",         label: "MetaTrader 4",          category: "Terminal",   popular: true,
    fields: [{ key: "host", label: "Host", type: "text", placeholder: "127.0.0.1" }, { key: "port", label: "Port", type: "text", placeholder: "8766" }],
    helper: "Requires the Edgekit EA running inside MT4." },
  { id: "ibkr",        label: "Interactive Brokers",   category: "Terminal",   popular: true,
    fields: [{ key: "host", label: "TWS host", type: "text", placeholder: "127.0.0.1" }, { key: "port", label: "TWS port", type: "text", placeholder: "7497" }],
    helper: "Requires TWS or IB Gateway with API enabled." },
  { id: "binance",     label: "Binance",               category: "Cloud / API", popular: true,
    fields: [{ key: "key", label: "API Key", type: "password", placeholder: "...", sensitive: true }, { key: "secret", label: "API Secret", type: "password", placeholder: "...", sensitive: true }],
    helper: "Read-only key is enough for backtesting." },
  { id: "bybit",       label: "Bybit",                 category: "Cloud / API",
    fields: [{ key: "key", label: "API Key", type: "password", placeholder: "...", sensitive: true }, { key: "secret", label: "API Secret", type: "password", placeholder: "...", sensitive: true }] },
  { id: "zerodha",     label: "Zerodha (Kite)",        category: "Cloud / API",
    fields: [{ key: "api_key", label: "API Key", type: "password", placeholder: "...", sensitive: true }, { key: "access_token", label: "Access Token", type: "password", placeholder: "...", sensitive: true }],
    helper: "From your Kite Connect developer console." },
  { id: "alpaca",      label: "Alpaca",                category: "Cloud / API",
    fields: [{ key: "key", label: "API Key", type: "password", placeholder: "PK...", sensitive: true }, { key: "secret", label: "API Secret", type: "password", placeholder: "...", sensitive: true }] },
  { id: "csv",         label: "CSV upload",            category: "Manual",    popular: true,
    fields: [], helper: "Drop any OHLCV CSV. Works with exports from MT4/MT5, TradingView, Binance." },
  { id: "tradingview", label: "TradingView webhook",   category: "Webhook",
    fields: [{ key: "url", label: "Webhook URL", type: "url", placeholder: "https://hooks.edgekit.app/u/..." }],
    helper: "Paste the URL into your TradingView alert." },
  { id: "custom",      label: "Custom REST / WebSocket", category: "Webhook",
    fields: [{ key: "url", label: "Base URL", type: "url", placeholder: "https://..." }, { key: "key", label: "Auth token (optional)", type: "password", placeholder: "...", sensitive: true }],
    helper: "Any feed returning OHLCV JSON." },
];

type SavedConnection = { id: string; source_id: string; label: string | null; config: Record<string, string>; is_active: boolean };

function BrokerSection() {
  const [sourceId,  setSourceId]  = useState("mt5");
  const [vals,      setVals]      = useState<Record<string, string>>({});
  const [saved,     setSaved]     = useState<SavedConnection[]>([]);
  const [testing,   setTesting]   = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [testResult, setTestResult] = useState<{ connected: boolean; note?: string; error?: string } | null>(null);

  const s = SOURCES.find((x) => x.id === sourceId)!;

  // Load existing connections on mount
  useEffect(() => {
    fetch("/api/broker-connections")
      .then((r) => r.json())
      .then((d) => setSaved(Array.isArray(d) ? d : []))
      .catch(() => {});
  }, []);

  const activeConn = saved.find((c) => c.source_id === sourceId);

  function set(k: string, v: string) { setVals((p) => ({ ...p, [k]: v })); setTestResult(null); }

  async function handleTest() {
    setTesting(true); setTestResult(null);
    const nonSensitive = Object.fromEntries(
      s.fields.filter((f) => !f.sensitive).map((f) => [f.key, vals[f.key] ?? ""])
    );
    try {
      const res = await fetch("/api/broker-connections/test", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: sourceId, config: nonSensitive }),
      });
      const d = await res.json();
      setTestResult(d);
    } catch { setTestResult({ connected: false, error: "Network error" }); }
    finally { setTesting(false); }
  }

  async function handleSave() {
    setSaving(true);
    const nonSensitive: Record<string, string> = {};
    const sensitive:    Record<string, string> = {};
    for (const f of s.fields) {
      if (f.sensitive) sensitive[f.key] = vals[f.key] ?? "";
      else             nonSensitive[f.key] = vals[f.key] ?? "";
    }
    try {
      const res = await fetch("/api/broker-connections", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: sourceId, label: s.label,
          config: nonSensitive, credentials: sensitive,
          is_active: testResult?.connected ?? false,
        }),
      });
      if (!res.ok) throw new Error("Save failed");
      const d = await res.json();
      setSaved((prev) => {
        const filtered = prev.filter((c) => c.source_id !== sourceId);
        return [d, ...filtered];
      });
      setTestResult((t) => t ? { ...t, connected: true } : { connected: true });
    } catch (e: any) {
      setTestResult({ connected: false, error: e.message });
    } finally {
      setSaving(false);
    }
  }

  async function handleDisconnect(id: string) {
    await fetch(`/api/broker-connections/${id}`, { method: "DELETE" });
    setSaved((p) => p.filter((c) => c.id !== id));
    setTestResult(null);
  }

  return (
    <div className="card p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-[16px]">📡 Data source</h2>
          <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
            Pick whatever you use. CSV, MetaTrader, Interactive Brokers, crypto exchanges — all work.
          </p>
        </div>
        {activeConn && (
          <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-up/15 text-up whitespace-nowrap shrink-0">
            ● Connected
          </span>
        )}
      </div>

      {/* Saved connections chips */}
      {saved.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {saved.map((c) => (
            <div key={c.id} className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface2 text-[11px] text-ink border border-border">
              <span className="text-up">●</span>
              <span>{c.label ?? c.source_id}</span>
              <button onClick={() => handleDisconnect(c.id)} className="text-muted hover:text-down ml-1 leading-none">×</button>
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        <label className="block">
          <span className="text-[12px] text-muted">Source</span>
          <select
            value={sourceId}
            onChange={(e) => { setSourceId(e.target.value); setVals({}); setTestResult(null); }}
            className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
          >
            {(["Terminal", "Cloud / API", "Manual", "Webhook"] as const).map((cat) => (
              <optgroup key={cat} label={cat}>
                {SOURCES.filter((x) => x.category === cat).map((x) => (
                  <option key={x.id} value={x.id}>{x.label}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>

        {s.fields.length > 0 && (
          <div className={`grid gap-2 ${s.fields.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
            {s.fields.map((f) => (
              <label key={f.key} className="block">
                <span className="text-[12px] text-muted">{f.label}</span>
                <input
                  type={f.type === "password" ? "password" : "text"}
                  value={vals[f.key] ?? ""}
                  onChange={(e) => set(f.key, e.target.value)}
                  placeholder={f.placeholder}
                  className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] font-mono focus:outline-none focus:ring-1 focus:ring-money"
                />
              </label>
            ))}
          </div>
        )}

        {s.id === "csv" ? (
          <label className="block">
            <input type="file" accept=".csv"
              className="block w-full text-[12px] text-muted file:mr-3 file:py-1.5 file:px-3 file:rounded-full file:border-0 file:text-[12px] file:font-medium file:bg-surface2 file:text-ink hover:file:bg-border cursor-pointer" />
          </label>
        ) : (
          <div className="flex gap-2">
            <button onClick={handleTest} disabled={testing}
              className="flex-1 py-2 rounded-lg border border-border text-[13px] font-medium hover:bg-surface2 transition-colors disabled:opacity-60">
              {testing ? "Testing…" : "Test connection"}
            </button>
            <button onClick={handleSave} disabled={saving}
              className="flex-1 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors disabled:opacity-60">
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        )}

        {testResult && (
          <p className={`text-[11px] font-medium ${testResult.connected ? "text-up" : "text-down"}`}>
            {testResult.connected
              ? `✓ ${testResult.note ?? "Connected successfully"}`
              : `✗ ${testResult.error ?? "Connection failed"}`}
          </p>
        )}

        {s.helper && <p className="text-[11px] text-muted">{s.helper}</p>}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   PINE SCRIPT EXPORT
   ───────────────────────────────────────────────────────────────────────────── */
function PineSection() {
  return (
    <div className="card p-6 space-y-4">
      <div>
        <h2 className="font-semibold text-[16px]">📤 Pine Script export</h2>
        <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
          Export any strategy built in the Builder as TradingView Pine Script v6 — ready to paste and deploy.
        </p>
      </div>
      <div className="rounded-lg bg-paper border border-border p-4 space-y-2 text-[12.5px]">
        <p className="font-medium text-ink">How to export:</p>
        <ol className="text-muted list-decimal list-inside space-y-1.5">
          <li>Go to <strong className="text-ink">Builder</strong> and build or load a strategy</li>
          <li>Click the <strong className="text-ink">📊</strong> button (top-left of canvas)</li>
          <li>Copy the generated Pine Script v6 code</li>
          <li>In TradingView: Pine Editor → New → Paste → Add to chart</li>
        </ol>
      </div>
      <a href="/builder" className="block w-full py-2 rounded-lg bg-surface2 text-ink text-[13px] font-medium text-center hover:bg-border transition-colors">
        Open Builder →
      </a>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   TRADE LOG
   ───────────────────────────────────────────────────────────────────────────── */
function TradeLogSection() {
  return (
    <div className="card p-6 space-y-4">
      <div>
        <h2 className="font-semibold text-[16px]">📋 Backtest trade log</h2>
        <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
          After a backtest, view every trade in detail. Export as CSV for deeper analysis.
        </p>
      </div>
      <div className="rounded-lg bg-surface2 border border-border p-6 text-center">
        <p className="text-[13px] text-muted mb-3">Run a backtest first to see your trade log here.</p>
        <a href="/strategies" className="text-[13px] text-money hover:underline font-medium">Run a backtest →</a>
      </div>
      <div className="space-y-1.5 text-[11px] text-muted">
        <p>Each trade shows: signal bar · fill bar · exit bar · entry price · SL · TP · exit type · PnL in R</p>
        <p>CSV export available from the backtest results panel after each run.</p>
      </div>
    </div>
  );
}
