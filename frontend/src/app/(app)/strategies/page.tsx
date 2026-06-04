/**
 * Unified Templates page.
 *
 * Every template — including "Build from scratch" — opens the same node-based
 * Builder canvas. Cards share one design language.
 *
 * Templates come from the v2 graph system (the only system with a node-based
 * representation). Where a v2 template happens to mirror a v1 strategy, we
 * reuse the v1 trade-preview clips. Otherwise we show a clean static preview.
 */
import Link from "next/link";
import { auth } from "@clerk/nextjs/server";
import { supabaseAdmin } from "@/lib/supabase-server";
import { TradeClipPair } from "@/components/TradeClip";
import { API_URL, efetch } from "@/lib/api";

export const revalidate = 0; // always fresh so saved strategies show immediately

// ── v2 template → v1 preview-strategy mapping ────────────────────────────────
// When a v2 template shares logic with a v1 strategy, we show its TradeClipPair
// previews. Otherwise the card falls back to a clean icon-only thumbnail.
const PREVIEW_FOR: Record<string, string> = {
  ema_cross_v2:         "ema_cross",
  donchian_breakout_v2: "donchian",
  turtle_system_1:      "donchian",
  smc_fvg_v2:           "ob_fvg_liq",
  rsi_bb_rich:          "rsi_mr",
};

// ── icon assignment per template (no PREVIEW_FOR fallback) ───────────────────
const ICON_FOR: Record<string, string> = {
  livermore_pivot:   "📍",
  ichimoku_tk_cross: "☁️",
};

type V2Template = { id: string; name: string; description: string };

async function fetchTemplates(): Promise<V2Template[]> {
  try {
    const r = await efetch(`${API_URL}/graph/v2/templates`, {
      next: { revalidate: 300 },
    } as any);
    if (!r.ok) return [];
    return await r.json();
  } catch {
    return [];
  }
}

async function fetchPreview(strategyId: string) {
  try {
    const r = await efetch(`${API_URL}/strategies/${strategyId}/preview-trades`, {
      next: { revalidate: 3600 },
    } as any);
    return r.ok ? r.json() : null;
  } catch {
    return null;
  }
}

type SavedStrategy = { id: string; name: string; symbol: string; timeframe: string; updated_at: string };

async function fetchSavedStrategies(userId: string): Promise<SavedStrategy[]> {
  const { data } = await supabaseAdmin
    .from("saved_strategies")
    .select("id, name, symbol, timeframe, updated_at")
    .eq("user_id", userId)
    .order("updated_at", { ascending: false })
    .limit(12);
  return (data ?? []) as SavedStrategy[];
}

export default async function TemplatesPage() {
  const { userId } = await auth();
  const [templates, savedStrategies] = await Promise.all([
    fetchTemplates(),
    userId ? fetchSavedStrategies(userId) : Promise.resolve([] as SavedStrategy[]),
  ]);

  // Prefetch all v1-mapped previews in parallel
  const previewEntries = await Promise.all(
    templates.map(async (t) => {
      const v1id = PREVIEW_FOR[t.id];
      if (!v1id) return [t.id, null] as const;
      const data = await fetchPreview(v1id);
      return [t.id, { v1id, data }] as const;
    })
  );
  const previews = Object.fromEntries(previewEntries) as Record<
    string,
    { v1id: string; data: any } | null
  >;

  return (
    <div className="space-y-8">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Templates</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Pick a starting point</h1>
        <p className="text-muted mt-2 text-[15px] max-w-2xl">
          Every template is a node graph that opens in the Builder — wire it up, tune it,
          re-run. Start blank or pick a proven setup.
        </p>
      </div>

      {/* ── User guide ─────────────────────────────────────────────────────── */}
      <div className="card p-6 border-money/20 bg-money/5">
        <h3 className="font-semibold text-[14px] text-ink mb-3">How templates work</h3>
        <ol className="text-[13px] text-muted space-y-1.5 list-decimal list-inside">
          <li>Click any card — the Builder opens with that template's nodes wired up</li>
          <li>Hit <strong className="text-ink">Run backtest</strong> — results appear in under 2 seconds</li>
          <li>Drag new nodes from the palette, edit parameters, connect outputs to inputs</li>
          <li>Every change is yours — duplicate, delete, rewire freely</li>
          <li>When happy, export to Pine Script v6 to take live on TradingView</li>
        </ol>
      </div>

      {/* ── My saved strategies ────────────────────────────────────────────── */}
      {savedStrategies.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-[16px] font-semibold">My strategies</h2>
            <span className="text-[11px] text-muted">{savedStrategies.length} saved</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {savedStrategies.map((s) => (
              <Link
                key={s.id}
                href={`/builder?saved=${s.id}`}
                className="card-hover p-4 flex items-center gap-3 group"
              >
                <div className="w-10 h-10 rounded-lg bg-money/10 flex items-center justify-center text-money text-xl shrink-0">💾</div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-[13.5px] text-ink group-hover:text-money transition-colors truncate">{s.name}</div>
                  <div className="text-[11px] text-muted mt-0.5">
                    {s.symbol} · {s.timeframe} · edited {new Date(s.updated_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short" })}
                  </div>
                </div>
                <span className="text-[11px] text-money font-medium shrink-0">Open →</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── Unified grid: Build-from-scratch + all v2 templates ───────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">

        {/* Build from scratch — same card design as templates */}
        <Link
          href="/builder?template=blank"
          className="card-hover p-4 flex flex-col gap-4 group border-dashed border-money/40"
        >
          <BlankPreview />
          <div className="px-1 pb-1">
            <div className="flex items-center justify-between mb-1.5">
              <h3 className="font-semibold text-[14.5px] text-ink group-hover:text-money transition-colors">
                Build from scratch
              </h3>
              <span className="text-[10px] font-mono text-muted">blank</span>
            </div>
            <p className="text-[12.5px] text-muted line-clamp-2 leading-relaxed">
              Start with an empty canvas. Drag nodes from the palette and wire your own logic.
              Maximum freedom, zero scaffolding.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
              <span className="px-2 py-0.5 rounded-full bg-money/10 text-money font-medium">Custom</span>
              <span className="px-2 py-0.5 rounded-full bg-surface2 text-ink2 font-medium ml-auto">
                Self-design
              </span>
            </div>
          </div>
        </Link>

        {/* All v2 templates */}
        {templates.map((t) => {
          const preview = previews[t.id];
          return (
            <Link
              key={t.id}
              href={`/builder?template=${t.id}`}
              className="card-hover p-4 flex flex-col gap-4 group"
            >
              {preview && preview.data ? (
                <TradeClipPair strategyId={preview.v1id} initialData={preview.data} />
              ) : (
                <StaticPreview icon={ICON_FOR[t.id] ?? "🧩"} />
              )}
              <div className="px-1 pb-1">
                <div className="flex items-center justify-between mb-1.5">
                  <h3 className="font-semibold text-[14.5px] text-ink group-hover:text-money transition-colors">
                    {t.name}
                  </h3>
                  <span className="text-[10px] font-mono text-muted">{t.id}</span>
                </div>
                <p className="text-[12.5px] text-muted line-clamp-2 leading-relaxed">
                  {t.description}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5 text-[10px]">
                  <span className="px-2 py-0.5 rounded-full bg-surface2 text-ink2 font-medium">Node graph</span>
                  <span className="px-2 py-0.5 rounded-full bg-money/10 text-money font-medium ml-auto">
                    Open in Builder
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>

      {templates.length === 0 && (
        <div className="card p-12 text-center text-muted">
          <p className="mb-3">Couldn't load templates.</p>
          <p className="text-[12px]">Make sure the backend is running on port 8765.</p>
        </div>
      )}

      <p className="text-[11px] text-muted text-center italic">
        Trade clips are real winning + losing trades from a live backtest. Refreshes hourly.
      </p>
    </div>
  );
}

// ── Static thumbnail components (matched to TradeClipPair dimensions) ─────────
function StaticPreview({ icon }: { icon: string }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded-md border border-border bg-surface2 h-[120px] flex items-center justify-center text-4xl opacity-70">
        {icon}
      </div>
      <div className="rounded-md border border-border bg-surface2 h-[120px] flex flex-col items-center justify-center gap-1 text-[10px] text-muted">
        <div className="font-mono text-money">●─●─●</div>
        <div className="font-mono text-money/60">│ │ │</div>
        <div className="font-mono text-money">●─●─●</div>
        <div className="mt-1 uppercase tracking-widest text-[9px]">Node graph</div>
      </div>
    </div>
  );
}

function BlankPreview() {
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="rounded-md border border-dashed border-money/40 bg-money/5 h-[120px] flex items-center justify-center text-4xl">
        ✨
      </div>
      <div className="rounded-md border border-dashed border-money/40 bg-money/5 h-[120px] flex flex-col items-center justify-center text-[10px] text-money">
        <div className="text-2xl mb-1">＋</div>
        <div className="uppercase tracking-widest text-[9px] font-semibold">Empty canvas</div>
      </div>
    </div>
  );
}
