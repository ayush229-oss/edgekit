"use client";

import { useEffect, useState } from "react";
import { forwardGenerateBridgeToken } from "@/lib/api";

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
        <MT5ConnectorSection />
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
   MT5 CONNECTOR
   ───────────────────────────────────────────────────────────────────────────── */

const EA_DOWNLOAD = "https://raw.githubusercontent.com/ayush229-oss/edgekit/main/bridge/EdgekitConnector.mq5";

function MT5ConnectorSection() {
  const [token,      setToken]      = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [copied,     setCopied]     = useState(false);
  const [error,      setError]      = useState<string | null>(null);

  async function generate() {
    setGenerating(true); setError(null);
    try {
      const d = await forwardGenerateBridgeToken();
      setToken(d.token);
    } catch (e: any) {
      setError(e?.message ?? "Failed to generate token");
    } finally {
      setGenerating(false);
    }
  }

  async function copy() {
    if (!token) return;
    try { await navigator.clipboard.writeText(token); setCopied(true); setTimeout(() => setCopied(false), 2000); }
    catch { /* blocked */ }
  }

  const isConnected = !!token;

  return (
    <div className="card p-6 space-y-5">
      <div>
        <h2 className="font-semibold text-[16px]">🔌 Connect your MT5</h2>
        <p className="text-[12.5px] text-muted mt-1 leading-relaxed">
          Run live-demo forward tests on your real broker feed.
          An EA inside MT5 executes orders and Edgekit records real spread, slippage &amp; commission.
          <strong className="text-ink"> No Python. No terminal. 3 steps.</strong>
        </p>
      </div>

      {/* ── Step 1 ── */}
      <div className={`rounded-xl border p-4 space-y-3 ${isConnected ? "border-money/40 bg-money/5" : "border-border bg-paper"}`}>
        <div className="flex items-center gap-2">
          <span className={`w-5 h-5 rounded-full text-[11px] font-bold flex items-center justify-center shrink-0 ${isConnected ? "bg-money text-white" : "bg-surface2 text-muted"}`}>
            {isConnected ? "✓" : "1"}
          </span>
          <p className="text-[13px] font-semibold text-ink">Get your token</p>
        </div>

        {token ? (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 rounded-lg bg-surface2 border border-border px-3 py-2 text-[11px] font-mono text-ink break-all leading-relaxed">
                {token}
              </code>
              <button onClick={() => void copy()}
                className="shrink-0 px-3 py-2 rounded-lg border border-border text-[12px] hover:bg-surface2 transition-colors">
                {copied ? "✓ Copied" : "Copy"}
              </button>
            </div>
            <p className="text-[11px] text-amber-700">Keep this private. Treat it like a password.</p>
            <button onClick={() => void generate()} disabled={generating}
              className="text-[11px] text-muted hover:text-ink underline">
              {generating ? "Regenerating…" : "Regenerate token"}
            </button>
          </div>
        ) : (
          <>
            <p className="text-[12px] text-muted">One token per account — links your MT5 to your Edgekit profile.</p>
            <button onClick={() => void generate()} disabled={generating}
              className="w-full py-2.5 rounded-lg bg-money text-white text-[13px] font-semibold hover:bg-moneyDark transition-colors disabled:opacity-50">
              {generating ? "Generating…" : "Generate token"}
            </button>
          </>
        )}
        {error && <p className="text-[11px] text-down">{error}</p>}
      </div>

      {/* ── Step 2 ── */}
      <div className="rounded-xl border border-border bg-paper p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-surface2 text-muted text-[11px] font-bold flex items-center justify-center shrink-0">2</span>
          <p className="text-[13px] font-semibold text-ink">Install the EA in MetaTrader 5</p>
        </div>
        <ol className="text-[12px] text-muted space-y-2 ml-7">
          <li>
            <a href={EA_DOWNLOAD} download="EdgekitConnector.mq5"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-money/10 text-money font-medium hover:bg-money/20 transition-colors text-[12px]">
              ⬇ Download EdgekitConnector.mq5
            </a>
          </li>
          <li>In MT5: <strong className="text-ink">File → Open Data Folder</strong> → go to <code className="bg-surface2 px-1 rounded text-[11px]">MQL5 / Experts</code> → paste the file there</li>
          <li>Back in MT5: press <strong className="text-ink">F5</strong> in Navigator to refresh — the EA appears under <em>Experts</em></li>
          <li><strong className="text-ink">Tools → Options → Expert Advisors</strong> → tick <em>"Allow WebRequest"</em> → add this URL:
            <code className="block bg-surface2 rounded px-2 py-1 mt-1 text-[11px] font-mono text-ink">http://165.232.178.128:8765</code>
          </li>
        </ol>
      </div>

      {/* ── Step 3 ── */}
      <div className="rounded-xl border border-border bg-paper p-4 space-y-3">
        <div className="flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-surface2 text-muted text-[11px] font-bold flex items-center justify-center shrink-0">3</span>
          <p className="text-[13px] font-semibold text-ink">Attach to a chart &amp; enter your token</p>
        </div>
        <ol className="text-[12px] text-muted space-y-1.5 ml-7">
          <li>MT5 must be logged into a <strong className="text-ink">DEMO account</strong></li>
          <li>Drag <strong className="text-ink">EdgekitConnector</strong> from Navigator onto any chart</li>
          <li>In the EA Properties (F7) → <strong className="text-ink">Inputs</strong> → paste your token into <code className="bg-surface2 px-1 rounded text-[11px]">Bridge token</code></li>
          <li>Click OK — the EA is now live</li>
        </ol>
        <p className="text-[11px] text-muted ml-7">
          Then go to <a href="/builder" className="text-money hover:underline">Builder</a>,
          finish a backtest, and click <strong className="text-ink">🔴 Live (demo)</strong> to start a forward test.
          The EA will place orders the next time your strategy signals.
        </p>
      </div>

      <p className="text-[11px] text-muted border-t border-border pt-3">
        The EA only trades your <strong>DEMO</strong> account and only touches positions it opened itself (magic 770011). Real-money trading is blocked in code.
      </p>
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
