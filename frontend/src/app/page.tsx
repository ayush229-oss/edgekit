import Link from "next/link";
import { listStrategies } from "@/lib/api";
import { TradeClipPair } from "@/components/TradeClip";

export const revalidate = 300;

const TESTIMONIALS = [
  {
    text: "Finally a backtester that moves at trader speed. I ran 40 variations of my OB strategy in one afternoon — would've taken a week in Python.",
    name: "Rohan S.", role: "Intraday trader · NSE", avatar: "R",
  },
  {
    text: "The node system clicked for me instantly. I actually understand my own strategy now instead of copying setups blindly. Win rate went from 38% to 51% after 2 weeks.",
    name: "Priya K.", role: "Swing trader · Crypto", avatar: "P",
  },
  {
    text: "I validate ideas before I code them in Python. The Pine Script export sometimes means I never code at all — I just ship straight from Edgekit.",
    name: "Alex M.", role: "Algo developer", avatar: "A",
  },
];

const MOAT = [
  {
    icon: "⚡",
    title: "2-second backtests",
    body: "Years of real market data, processed in under 2 seconds. Iterate 20× before most platforms finish one run.",
  },
  {
    icon: "🧩",
    title: "No code, ever",
    body: "Every entry condition, filter, and risk rule is a node. Wire them like Lego. Nothing to install, nothing to learn but the market.",
  },
  {
    icon: "📤",
    title: "Live on TradingView in one click",
    body: "When you're ready, export your node graph as Pine Script v6. Copy, paste, deploy. No translation layer.",
  },
];

const STEPS = [
  { n: "01", title: "Pick a template", body: "Start from 10+ proven strategies — EMA Cross, OB+FVG, Liquidity Engulf, RSI Mean Reversion, and more. Or start blank." },
  { n: "02", title: "Wire your logic", body: "Drag nodes onto the canvas. Connect outputs to inputs. Signal, filter, entry, risk — snap them together." },
  { n: "03", title: "Backtest on real data", body: "Hit Run. Years of XAUUSD M15 data processed in under 2 seconds. Real fills. No lookahead. Honest numbers." },
  { n: "04", title: "Iterate until it clicks", body: "Tune one param, re-run, watch the equity curve react. When it works, export as Pine Script v6 for TradingView." },
];

export default async function LandingPage() {
  let strategies: Awaited<ReturnType<typeof listStrategies>> = [];
  try { strategies = await listStrategies(); } catch {}

  const featured = strategies.slice(0, 3);
  const previewResults = await Promise.allSettled(
    featured.map((s) =>
      fetch(`http://127.0.0.1:8765/strategies/${s.id}/preview-trades`, { next: { revalidate: 3600 } })
        .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    )
  );
  const previewMap = Object.fromEntries(
    featured.map((s, i) => [s.id, previewResults[i].status === "fulfilled" ? previewResults[i].value : null])
  );

  return (
    <div className="bg-paper min-h-screen">

      {/* ── NAV ──────────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-border bg-paper/90 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-2 group">
            <div className="w-6 h-6 rounded-md bg-ink flex items-center justify-center text-paper font-bold text-[11px] group-hover:bg-money transition-colors">E</div>
            <span className="font-semibold tracking-tight text-[15px]">Edgekit</span>
            <span className="text-[10px] uppercase tracking-widest text-muted px-1.5 py-0.5 rounded bg-surface2 ml-1">beta</span>
          </Link>
          <nav className="hidden md:flex items-center gap-1 text-[13.5px] text-muted">
            <a href="#how-it-works" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">How it works</a>
            <a href="#strategies"   className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Strategies</a>
            <a href="#testimonials" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Testimonials</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/home" className="btn-secondary text-[13px] py-1.5 px-4">Log in</Link>
            <Link href="/home" className="btn-primary text-[13px] py-1.5 px-4">Get started free</Link>
          </div>
        </div>
      </header>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <section className="hero-grad max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-[11.5px] text-muted mb-8 shadow-soft">
          <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
          Live trade previews on real XAUUSD M15 data
        </div>
        <h1 className="text-[44px] sm:text-[60px] md:text-display-1 font-bold tracking-tight leading-[1.04] text-ink mb-6">
          Your edge is<br />
          <span className="text-money">one backtest away.</span>
        </h1>
        <p className="text-[17px] sm:text-[19px] text-ink2 max-w-2xl mx-auto leading-relaxed mb-10">
          Wire trading logic with nodes. Run honest backtests on real data.
          Iterate until you find what actually works — then ship to TradingView.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-6">
          <Link href="/home" className="btn-primary px-8 py-3.5 text-[15px] shadow-lift">
            Start building free →
          </Link>
          <a href="#how-it-works" className="btn-secondary px-8 py-3.5 text-[15px]">
            See how it works
          </a>
        </div>
        <p className="text-[12px] text-muted">No signup · No credit card · MT5 + CSV supported · Pine Script export</p>
      </section>

      {/* ── PROOF BAR ────────────────────────────────────────────────────────── */}
      <div className="border-y border-border bg-surface">
        <div className="max-w-5xl mx-auto px-6 py-5 grid grid-cols-2 sm:grid-cols-4 gap-6 text-center">
          {[
            { v: "< 2s",      l: "Per backtest" },
            { v: "10+",       l: "Strategy templates" },
            { v: "M1 → D1",   l: "Every timeframe" },
            { v: "1-click",   l: "Pine Script export" },
          ].map(({ v, l }) => (
            <div key={l}>
              <div className="text-[22px] font-bold text-ink num">{v}</div>
              <div className="text-[12px] text-muted mt-0.5">{l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── MOAT ─────────────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Why Edgekit</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
          Built for speed. Designed for clarity.
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {MOAT.map((m) => (
            <div key={m.title} className="card p-7">
              <div className="text-3xl mb-4">{m.icon}</div>
              <h3 className="font-semibold text-[16px] mb-2 text-ink">{m.title}</h3>
              <p className="text-[13.5px] text-muted leading-relaxed">{m.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── HOW IT WORKS ─────────────────────────────────────────────────────── */}
      <section id="how-it-works" className="bg-surface2 py-24">
        <div className="max-w-5xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Process</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
            From idea to live strategy in minutes.
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
            {STEPS.map((s) => (
              <div key={s.n} className="card p-6">
                <div className="text-[11px] font-mono text-money mb-3 font-semibold">{s.n}</div>
                <h3 className="font-semibold text-[15px] mb-2 text-ink">{s.title}</h3>
                <p className="text-[13px] text-muted leading-relaxed">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── STRATEGY PREVIEW ─────────────────────────────────────────────────── */}
      {featured.length > 0 && (
        <section id="strategies" className="max-w-7xl mx-auto px-6 py-24">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Templates</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-4">
            Start from a proven setup.
          </h2>
          <p className="text-center text-[15px] text-muted mb-12 max-w-xl mx-auto">
            Every template ships with live trade previews from a real backtest. Pick one, iterate, make it yours.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {featured.map((s) => (
              <Link key={s.id} href={`/strategy/${s.id}`} className="card-hover p-4 flex flex-col gap-4 group">
                <TradeClipPair strategyId={s.id} initialData={previewMap[s.id]} />
                <div className="px-1 pb-1">
                  <h3 className="font-semibold text-[14.5px] text-ink group-hover:text-money transition-colors mb-1">{s.name}</h3>
                  <p className="text-[12.5px] text-muted line-clamp-2">{s.description}</p>
                </div>
              </Link>
            ))}
          </div>
          <div className="text-center mt-10">
            <Link href="/strategies" className="btn-secondary px-6 py-2.5 text-[14px]">
              See all {strategies.length} strategies →
            </Link>
          </div>
        </section>
      )}

      {/* ── TESTIMONIALS ─────────────────────────────────────────────────────── */}
      <section id="testimonials" className="bg-surface2 py-24">
        <div className="max-w-6xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Traders say</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
            Real traders. Real results.
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {TESTIMONIALS.map((t) => (
              <div key={t.name} className="card p-7 flex flex-col gap-4">
                <p className="text-[14px] leading-relaxed text-ink2 flex-1">"{t.text}"</p>
                <div className="flex items-center gap-3 pt-3 border-t border-border">
                  <div className="w-8 h-8 rounded-full bg-money/15 flex items-center justify-center text-money font-semibold text-[13px] shrink-0">{t.avatar}</div>
                  <div>
                    <div className="font-medium text-[13px]">{t.name}</div>
                    <div className="text-[11px] text-muted">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="text-center mt-10">
            <Link href="/testimonials" className="text-[13px] text-money hover:underline font-medium">
              Submit your own story →
            </Link>
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ────────────────────────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-6 py-28 text-center">
        <h2 className="text-[36px] sm:text-display-2 font-bold tracking-tight text-ink mb-6">
          Stop guessing. Start backtesting.
        </h2>
        <p className="text-[17px] text-muted mb-10 max-w-xl mx-auto">
          Your next winning strategy is in there. Find it.
        </p>
        <Link href="/home" className="btn-primary px-10 py-4 text-[16px] shadow-float">
          Open Edgekit — it's free →
        </Link>
        <p className="mt-5 text-[12px] text-muted">No signup required · Works in the browser · MT5 + CSV data supported</p>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4 text-[12px] text-muted">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-ink flex items-center justify-center text-paper font-bold text-[10px]">E</div>
            <span>Edgekit · Operated by Satyasakshi</span>
          </div>
          <div className="flex items-center gap-5">
            <span>© {new Date().getFullYear()}</span>
            <span className="italic">For research only — not investment advice.</span>
            <Link href="/waitlist" className="hover:text-ink transition-colors">Get access</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
