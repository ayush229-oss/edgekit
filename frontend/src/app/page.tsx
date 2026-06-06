import Link from "next/link";
import { listStrategies, API_URL, efetch } from "@/lib/api";
import { LogoMark } from "@/components/LogoMark";
import { TradeClipPair } from "@/components/TradeClip";

export const revalidate = 300;

const TESTIMONIALS = [
  {
    text: "I was blowing FTMO challenges every month. I thought I was just unlucky. Edgekit showed me I had no edge — the backtest was flat. Built a new system in a week. Passed my next challenge.",
    name: "Arjun V.", role: "Forex trader · FTMO funded", avatar: "A",
  },
  {
    text: "My win rate looked fine in my head. Then I backtested it — 34%. Building it as a system forced me to define every rule. Two months later I'm at 52% with positive expectancy.",
    name: "Sneha R.", role: "Price action trader · The Funded Trader", avatar: "S",
  },
  {
    text: "I was taking 10 trades a day on gut feel. Edgekit made me realise I only had 2 valid setups. Fewer trades, more money, zero stress.",
    name: "Karan M.", role: "Intraday trader · Forex · India", avatar: "K",
  },
];

const MOAT = [
  {
    icon: "🎯",
    title: "Validate before you risk",
    body: "Test your strategy on years of real market data before you put a dollar on the line. Know if your edge is real — not just in your head.",
  },
  {
    icon: "🔁",
    title: "Iterate until it holds up",
    body: "Run 20 variations in minutes. Tweak a parameter, re-run, watch the equity curve react. Find what actually works, not what feels right.",
  },
  {
    icon: "📋",
    title: "Prop firm ready",
    body: "Forward test in close-to-real conditions before paying for a challenge. Know your drawdown, your consistency, your worst losing streak — in advance.",
  },
];

const STEPS = [
  { n: "01", title: "Define your rules", body: "Most traders lose because they have no system. Drag nodes onto the canvas — entry signal, filter, stop loss, take profit. Make every rule explicit." },
  { n: "02", title: "Backtest on real data", body: "Hit Run. Years of forex data processed in under 2 seconds. Real fills. No lookahead. No wishful thinking — just the truth about your strategy." },
  { n: "03", title: "Iterate until it holds up", body: "Tune one parameter, re-run, watch the equity curve. Repeat until you have positive expectancy and drawdown you can actually stomach." },
  { n: "04", title: "Forward test before you fund", body: "Run your strategy on unseen bars in paper mode. See if it holds up outside the data you optimised on. Only then put money behind it." },
];

const PROBLEMS = [
  { label: "Taking trades based on gut feel or a YouTube setup" },
  { label: "No idea what your actual win rate or expectancy is" },
  { label: "Blowing prop firm challenges and not knowing why" },
  { label: "Switching strategies every week looking for something that 'feels right'" },
];

export default async function LandingPage() {
  let strategies: Awaited<ReturnType<typeof listStrategies>> = [];
  try { strategies = await listStrategies(); } catch {}

  const featured = strategies.slice(0, 3);
  const previewResults = await Promise.allSettled(
    featured.map((s) =>
      efetch(`${API_URL}/strategies/${s.id}/preview-trades`, { next: { revalidate: 3600 } } as any)
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
            <LogoMark size={24} />
            <span className="font-semibold tracking-tight text-[15px]">Edgekit</span>
            <span className="text-[10px] uppercase tracking-widest text-muted px-1.5 py-0.5 rounded bg-surface2 ml-1">beta</span>
          </Link>
          <nav className="hidden md:flex items-center gap-1 text-[13.5px] text-muted">
            <a href="#problem"      className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">The problem</a>
            <a href="#how-it-works" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">How it works</a>
            <a href="#strategies"   className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Strategies</a>
            <a href="#testimonials" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Traders</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/home" className="btn-secondary text-[13px] py-1.5 px-4">Log in</Link>
            <Link href="/home" className="btn-primary text-[13px] py-1.5 px-4">Start free</Link>
          </div>
        </div>
      </header>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <section className="hero-grad max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-[11.5px] text-muted mb-8 shadow-soft">
          <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
          Built for Indian forex & prop firm traders
        </div>
        <h1 className="text-[44px] sm:text-[60px] md:text-display-1 font-bold tracking-tight leading-[1.04] text-ink mb-6">
          Stop trading on gut feel.<br />
          <span className="text-money">Build a system.</span>
        </h1>
        <p className="text-[17px] sm:text-[19px] text-ink2 max-w-2xl mx-auto leading-relaxed mb-10">
          Most forex traders fail prop firm challenges not because markets are hard —
          but because they have no tested edge. Edgekit gives you the tools to build,
          backtest, and trust a real strategy before you risk a rupee.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-6">
          <Link href="/home" className="btn-primary px-8 py-3.5 text-[15px] shadow-lift">
            Build your strategy free →
          </Link>
          <a href="#how-it-works" className="btn-secondary px-8 py-3.5 text-[15px]">
            See how it works
          </a>
        </div>
        <p className="text-[12px] text-muted">No signup · No credit card · MT5 + CSV supported · Works in the browser</p>
      </section>

      {/* ── PROOF BAR ────────────────────────────────────────────────────────── */}
      <div className="border-y border-border bg-surface">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-center gap-12 text-center flex-wrap">
          {[
            { v: "M1 → D1", l: "Every timeframe" },
            { v: "2 sec",   l: "Average backtest time" },
          ].map(({ v, l }) => (
            <div key={l}>
              <div className="text-[22px] font-bold text-ink num">{v}</div>
              <div className="text-[12px] text-muted mt-0.5">{l}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── PROBLEM ──────────────────────────────────────────────────────────── */}
      <section id="problem" className="max-w-4xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">The problem</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-6">
          Most traders are gambling.<br />They just don't know it yet.
        </h2>
        <p className="text-center text-[15px] text-muted mb-12 max-w-2xl mx-auto">
          It's not about the setup. It's not about the indicator. The real problem is
          trading without a system you've actually tested. Sound familiar?
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-12">
          {PROBLEMS.map((p) => (
            <div key={p.label} className="flex items-start gap-3 p-4 rounded-xl border border-border bg-surface">
              <span className="text-down text-[16px] mt-0.5 shrink-0">✕</span>
              <span className="text-[13.5px] text-ink2 leading-snug">{p.label}</span>
            </div>
          ))}
        </div>
        <p className="text-center text-[15px] text-ink2 max-w-xl mx-auto">
          Edgekit doesn't give you signals or tips. It gives you a framework to
          <strong className="text-ink"> build, test, and own</strong> a strategy that holds up on real data.
        </p>
      </section>

      {/* ── MOAT ─────────────────────────────────────────────────────────────── */}
      <section className="bg-surface2 py-24">
        <div className="max-w-6xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Why Edgekit</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
            From gut feel to a system you trust.
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
        </div>
      </section>

      {/* ── HOW IT WORKS ─────────────────────────────────────────────────────── */}
      <section id="how-it-works" className="max-w-5xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">The process</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-4">
          Build it. Test it. Trust it.
        </h2>
        <p className="text-center text-[15px] text-muted mb-14 max-w-xl mx-auto">
          No code. No Python. Just a canvas, real market data, and an honest answer about whether your idea actually works.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
          {STEPS.map((s) => (
            <div key={s.n} className="card p-6">
              <div className="text-[11px] font-mono text-money mb-3 font-semibold">{s.n}</div>
              <h3 className="font-semibold text-[15px] mb-2 text-ink">{s.title}</h3>
              <p className="text-[13px] text-muted leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── STRATEGY PREVIEW ─────────────────────────────────────────────────── */}
      {featured.length > 0 && (
        <section id="strategies" className="bg-surface2 py-24">
          <div className="max-w-7xl mx-auto px-6">
            <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Starting points</p>
            <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-4">
              10+ systematic strategies — ready to backtest.
            </h2>
            <p className="text-center text-[15px] text-muted mb-12 max-w-xl mx-auto">
              Not signals. Not tips. Full rule-based systems with entry, filter, stop loss, and take profit defined. Pick one, backtest it, make it yours.
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
          </div>
        </section>
      )}

      {/* ── TESTIMONIALS ─────────────────────────────────────────────────────── */}
      <section id="testimonials" className="max-w-6xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Traders say</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
          From gambling to systematic.
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
      </section>

      {/* ── FINAL CTA ────────────────────────────────────────────────────────── */}
      <section className="bg-surface2 py-28">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-[36px] sm:text-display-2 font-bold tracking-tight text-ink mb-6">
            Your strategy either works on data<br />or it doesn't. Find out now.
          </h2>
          <p className="text-[17px] text-muted mb-10 max-w-xl mx-auto">
            Stop paying for prop firm challenges with an untested edge.
            Build your system, backtest it, forward test it — then fund it.
          </p>
          <Link href="/home" className="btn-primary px-10 py-4 text-[16px] shadow-float">
            Start building free →
          </Link>
          <p className="mt-5 text-[12px] text-muted">No signup required · No credit card · MT5 + CSV data supported</p>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col sm:flex-row items-center justify-between gap-4 text-[12px] text-muted">
          <div className="flex items-center gap-2">
            <LogoMark size={20} />
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
