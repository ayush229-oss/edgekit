import Link from "next/link";
import { listStrategies, API_URL, efetch } from "@/lib/api";
import { LogoMark } from "@/components/LogoMark";
import { TradeClipPair } from "@/components/TradeClip";

export const revalidate = 300;

const PAIN_POINTS = [
  "Checking each candle manually takes 15+ hours per strategy",
  "Pine Script and Python require months of learning just to get started",
  "Buying someone else's strategy doesn't teach you why it works — or when it will stop working",
  "You keep taking trades you \"feel\" are right — and wondering why you keep losing",
];

const STEPS = [
  {
    n: "01",
    title: "Describe your strategy",
    body: "Type it in plain English. \"Buy when the 20 EMA crosses above the 50 EMA. Stop loss below the recent swing low. Take profit at 2R.\" That's it.",
  },
  {
    n: "02",
    title: "See it as a strategy graph",
    body: "Edgekit converts your words into a visual node map — every rule, every condition, every exit laid out in front of you.",
  },
  {
    n: "03",
    title: "Run the backtest",
    body: "See every trade your strategy would have taken — entries, exits, winners, losers, drawdowns — across real market data.",
  },
  {
    n: "04",
    title: "Iterate",
    body: "Change a rule. Tighten the stop. Add a filter. Run it again. In 2 minutes, not 20 hours.",
  },
];

const FEATURES = [
  {
    icon: "🤖",
    title: "AI Strategy Builder",
    what: "Describe your idea in plain English. Edgekit builds the logic automatically.",
    why: "No syntax. No semicolons. No Stack Overflow.",
  },
  {
    icon: "🧩",
    title: "Visual Node Editor",
    what: "See your strategy as a connected graph — every condition and exit rule laid out visually.",
    why: "Tweak any node and re-run instantly.",
  },
  {
    icon: "📊",
    title: "Honest Backtesting",
    what: "Real historical data. Real trade simulation. Real results — wins, losses, max drawdown, R-multiples.",
    why: "No inflated numbers. No curve-fitting.",
  },
  {
    icon: "📚",
    title: "Starter Templates",
    what: "Turtle Trading, Donchian Breakout, Ichimoku TK Cross, SMC Order Block, RSI+BB, EMA Cross.",
    why: "Start from a proven framework, customise your edge.",
  },
  {
    icon: "📤",
    title: "Export to TradingView",
    what: "Export your strategy to Pine Script with one click.",
    why: "Deploy on TradingView when you're ready to go live.",
  },
  {
    icon: "🎬",
    title: "Trade-by-Trade Replay",
    what: "Click any trade in the results list. The chart jumps to that exact moment.",
    why: "See exactly what your strategy saw — and validate it.",
  },
];

const CONFIDENCE_POINTS = [
  "You stop second-guessing your entries",
  "You take losses without panic — because you know they're part of the system",
  "You iterate logically instead of emotionally",
  "You start thinking like a professional",
];

const COMPARISON = [
  { label: "Requires coding",        edgekit: "No",        pine: "Yes",          manual: "No" },
  { label: "Time to first backtest", edgekit: "5 minutes", pine: "Days / weeks", manual: "10–20 hours" },
  { label: "Visual strategy map",    edgekit: "Yes",       pine: "No",           manual: "No" },
  { label: "AI plain-English input", edgekit: "Yes",       pine: "No",           manual: "No" },
  { label: "Free to start",          edgekit: "Yes",       pine: "Yes",          manual: "Yes" },
];

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

const FAQ = [
  {
    q: "Is Edgekit really free?",
    a: "Yes. The free tier is free — no trial clock, no credit card. Paid tiers exist for heavier usage (like CSV data uploads and higher backtest quotas), but you can describe, build, and backtest strategies on the free tier today.",
  },
  {
    q: "What data do the backtests run on?",
    a: "Real historical market data — MT5 price history for forex pairs, metals and indices, with CSV upload supported so you can test on your own data. Every simulated trade is shown to you individually; nothing is aggregated away or hidden.",
  },
  {
    q: "Do I need to know how to code?",
    a: "No. You describe your strategy in plain English or build it visually with nodes. If you eventually want code, Edgekit exports your finished strategy to Pine Script for TradingView.",
  },
  {
    q: "Will Edgekit give me trading signals?",
    a: "No — and that's deliberate. Edgekit is a research and validation tool, not a signal service. It tells you honestly whether your idea held up on historical data. The strategy, and the decisions, stay yours.",
  },
  {
    q: "Who is behind Edgekit?",
    a: "Edgekit is operated by Satyasakshi and built hands-on by a small team for forex and prop-firm traders. You can reach us any time at support@edgekit.app — real humans read it.",
  },
  {
    q: "Is this investment advice?",
    a: "No. Backtest results are historical simulations and never a guarantee of future performance. Edgekit is for research and education — see our legal page for the full terms.",
  },
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
            <a href="#how-it-works" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">How it works</a>
            <a href="#features"     className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Features</a>
            <a href="#strategies"   className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Strategies</a>
            <a href="#testimonials" className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">Traders</a>
            <a href="#faq"          className="px-3 py-1.5 rounded-full hover:text-ink hover:bg-surface2 transition-colors">FAQ</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link href="/home" className="btn-secondary text-[13px] py-1.5 px-4">Log in</Link>
            <Link href="/home" className="btn-primary text-[13px] py-1.5 px-4">Try it free</Link>
          </div>
        </div>
      </header>

      {/* ── HERO ─────────────────────────────────────────────────────────────── */}
      <section className="hero-grad max-w-5xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-surface border border-border text-[11.5px] text-muted mb-8 shadow-soft">
          <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
          Built for forex & prop firm traders
        </div>
        <h1 className="text-[44px] sm:text-[60px] md:text-display-1 font-bold tracking-tight leading-[1.04] text-ink mb-6">
          You have a trading strategy<br />
          in your head. <span className="text-money">Now prove it works.</span>
        </h1>
        <p className="text-[17px] sm:text-[19px] text-ink2 max-w-2xl mx-auto leading-relaxed mb-10">
          Edgekit lets you backtest any trading idea in minutes — no code, no Excel,
          no 20-hour manual chart analysis. Just describe your strategy, see if it
          ever worked, and trade with real confidence.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-6">
          <Link href="/home" className="btn-primary px-8 py-3.5 text-[15px] shadow-lift">
            Prove your strategy works — free →
          </Link>
          <a href="#strategies" className="btn-secondary px-8 py-3.5 text-[15px]">
            See example backtests
          </a>
        </div>
        <p className="text-[12px] text-muted">No credit card · No code · MT5 + CSV supported · Works in the browser</p>
      </section>

      {/* ── PROOF BAR ────────────────────────────────────────────────────────── */}
      <div className="border-y border-border bg-surface">
        <div className="max-w-5xl mx-auto px-6 py-5 flex items-center justify-center gap-12 text-center flex-wrap">
          {[
            { v: "5 min",   l: "Idea to first backtest" },
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

      {/* ── PAIN ─────────────────────────────────────────────────────────────── */}
      <section id="pain" className="max-w-4xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">The problem</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-6">
          Still trading on gut feel?
        </h2>
        <p className="text-center text-[15px] text-muted mb-12 max-w-2xl mx-auto">
          You already know the problem. You've read the books. You've watched the
          YouTubers. Everyone says the same thing: "Backtest your strategy."
          But when you try to actually do it:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-12">
          {PAIN_POINTS.map((p) => (
            <div key={p} className="flex items-start gap-3 p-4 rounded-xl border border-border bg-surface">
              <span className="text-down text-[16px] mt-0.5 shrink-0">✕</span>
              <span className="text-[13.5px] text-ink2 leading-snug">{p}</span>
            </div>
          ))}
        </div>
        <p className="text-center text-[15px] text-ink2 max-w-xl mx-auto">
          The traders who go pro aren't smarter than you. They just
          <strong className="text-ink"> stopped guessing and started testing.</strong>
        </p>
      </section>

      {/* ── SOLUTION / HOW IT WORKS ──────────────────────────────────────────── */}
      <section id="how-it-works" className="bg-surface2 py-24">
        <div className="max-w-5xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">The solution</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-4">
            Edgekit closes the gap.
          </h2>
          <p className="text-center text-[15px] text-muted mb-14 max-w-2xl mx-auto">
            Edgekit is the missing step between "I have a trading idea" and
            "I'm confident enough to trade it with real money."
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
        </div>
      </section>

      {/* ── FEATURES ─────────────────────────────────────────────────────────── */}
      <section id="features" className="max-w-6xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Features</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
          Built for traders who think in trades, not code.
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {FEATURES.map((f) => (
            <div key={f.title} className="card p-7">
              <div className="text-3xl mb-4">{f.icon}</div>
              <h3 className="font-semibold text-[16px] mb-2 text-ink">{f.title}</h3>
              <p className="text-[13.5px] text-ink2 leading-relaxed mb-3">{f.what}</p>
              <p className="text-[12.5px] text-muted leading-relaxed">{f.why}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── CONFIDENCE ───────────────────────────────────────────────────────── */}
      <section className="bg-surface2 py-24">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Why it matters</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-6">
            Confidence isn't arrogance.<br />It's preparation.
          </h2>
          <p className="text-center text-[15px] text-muted mb-12 max-w-2xl mx-auto">
            The difference between a trader who quits after 6 months and one who goes
            on to trade full-time isn't talent. It's having a system they've actually
            tested. When your strategy has a backtest behind it, everything changes:
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl mx-auto mb-12">
            {CONFIDENCE_POINTS.map((c) => (
              <div key={c} className="flex items-start gap-3 p-4 rounded-xl border border-border bg-surface">
                <span className="text-up text-[16px] mt-0.5 shrink-0">✓</span>
                <span className="text-[13.5px] text-ink2 leading-snug">{c}</span>
              </div>
            ))}
          </div>
          <p className="text-center text-[15px] text-ink2 max-w-xl mx-auto">
            That's what Edgekit gives you. Not a winning strategy — a tested one.
            <strong className="text-ink"> And a tested one you understand is worth more
            than a winning one you don't.</strong>
          </p>
        </div>
      </section>

      {/* ── STRATEGY PREVIEW ─────────────────────────────────────────────────── */}
      {featured.length > 0 && (
        <section id="strategies" className="max-w-7xl mx-auto px-6 py-24">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Starting points</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-4">
            {strategies.length}+ systematic strategies — ready to backtest.
          </h2>
          <p className="text-center text-[15px] text-muted mb-12 max-w-xl mx-auto">
            Not signals. Not tips. Full rule-based systems with entry, filter, stop loss,
            and take profit defined. Pick one, backtest it, make it yours.
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

      {/* ── COMPARISON ───────────────────────────────────────────────────────── */}
      <section id="compare" className="bg-surface2 py-24">
        <div className="max-w-4xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Why not just…</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
            Not another Pine Script tutorial.
          </h2>
          <div className="card overflow-x-auto">
            <table className="w-full text-left text-[13.5px]">
              <thead>
                <tr className="border-b border-border text-muted">
                  <th className="p-4 font-medium"></th>
                  <th className="p-4 font-semibold text-money">Edgekit</th>
                  <th className="p-4 font-medium">TradingView Pine Script</th>
                  <th className="p-4 font-medium">Manual backtesting</th>
                </tr>
              </thead>
              <tbody>
                {COMPARISON.map((row) => (
                  <tr key={row.label} className="border-b border-border last:border-0">
                    <td className="p-4 text-muted">{row.label}</td>
                    <td className="p-4 font-semibold text-ink">{row.edgekit}</td>
                    <td className="p-4 text-ink2">{row.pine}</td>
                    <td className="p-4 text-ink2">{row.manual}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── TESTIMONIALS ─────────────────────────────────────────────────────── */}
      <section id="testimonials" className="max-w-6xl mx-auto px-6 py-24">
        <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">Traders say</p>
        <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-6">
          From gambling to systematic.
        </h2>
        <p className="text-center text-[14px] text-muted mb-14 max-w-2xl mx-auto">
          Every result below comes from the same engine you get on the free tier — real
          historical data, every simulated trade visible, nothing aggregated away.
        </p>
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

      {/* ── FAQ ──────────────────────────────────────────────────────────────── */}
      <section id="faq" className="bg-surface2 py-24">
        <div className="max-w-3xl mx-auto px-6">
          <p className="text-[11px] uppercase tracking-[0.25em] text-money mb-4 font-semibold text-center">FAQ</p>
          <h2 className="text-[32px] sm:text-display-3 font-semibold tracking-tight text-ink text-center mb-14">
            Fair questions. Straight answers.
          </h2>
          <div className="space-y-4">
            {FAQ.map((item) => (
              <details key={item.q} className="card p-6 group">
                <summary className="font-semibold text-[15px] text-ink cursor-pointer list-none flex items-center justify-between gap-4">
                  {item.q}
                  <span className="text-muted text-[18px] shrink-0 transition-transform group-open:rotate-45">+</span>
                </summary>
                <p className="text-[13.5px] text-ink2 leading-relaxed mt-4">{item.a}</p>
              </details>
            ))}
          </div>
          <p className="text-center text-[13px] text-muted mt-10">
            Something else on your mind?{" "}
            <a href="mailto:support@edgekit.app" className="text-money hover:underline font-medium">
              support@edgekit.app
            </a>{" "}
            — we answer.
          </p>
        </div>
      </section>

      {/* ── FINAL CTA ────────────────────────────────────────────────────────── */}
      <section className="py-28">
        <div className="max-w-4xl mx-auto px-6 text-center">
          <h2 className="text-[36px] sm:text-display-2 font-bold tracking-tight text-ink mb-6">
            Your strategy deserves a fair test.
          </h2>
          <p className="text-[17px] text-muted mb-10 max-w-xl mx-auto">
            Stop trading ideas you haven't tested. Stop losing money to guesses.
            Give your strategy 5 minutes in Edgekit — and find out if it's worth trading.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-6">
            <Link href="/home" className="btn-primary px-10 py-4 text-[16px] shadow-float">
              Start testing free →
            </Link>
            <Link href="/strategies" className="btn-secondary px-10 py-4 text-[16px]">
              See example backtests
            </Link>
          </div>
          <p className="text-[12px] text-muted">No credit card. No code. No excuses.</p>
          <p className="mt-3 text-[12px] text-muted">
            The free tier stays free — paid tiers only add heavier usage like CSV uploads and bigger backtest quotas.
          </p>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────────────────────────── */}
      <footer className="border-t border-border">
        <div className="max-w-7xl mx-auto px-6 py-10 flex flex-col gap-6">
          <p className="text-center text-[14px] text-ink2 italic">
            "Built for traders who are done guessing."
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-[12px] text-muted">
            <div className="flex items-center gap-2">
              <LogoMark size={20} />
              <span>Edgekit · Operated by Satyasakshi</span>
            </div>
            <div className="flex items-center gap-5 flex-wrap justify-center">
              <span>© {new Date().getFullYear()}</span>
              <span className="italic">For research only — not investment advice.</span>
              <a href="mailto:support@edgekit.app" className="hover:text-ink transition-colors">support@edgekit.app</a>
              <Link href="/legal" className="hover:text-ink transition-colors">Legal</Link>
              <Link href="/waitlist" className="hover:text-ink transition-colors">Get access</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
