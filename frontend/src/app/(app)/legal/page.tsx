export const dynamic = "force-dynamic";

export default function LegalPage() {
  return (
    <div className="space-y-8 max-w-2xl">

      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Legal</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Legal information</h1>
        <p className="text-muted mt-2 text-[15px]">
          Operated by Satyasakshi. Edgekit is a research and backtesting tool — not a broker, not a financial adviser.
        </p>
      </div>

      <Section title="Terms of use">
        <p>Edgekit provides backtesting and strategy-building tools for educational and research purposes only. By using Edgekit you agree that:</p>
        <ul>
          <li>Backtest results are historical simulations and do not guarantee future performance.</li>
          <li>You will not use Edgekit as the sole basis for making real-money trading decisions.</li>
          <li>You are solely responsible for any trades you execute in live markets.</li>
          <li>You will not attempt to reverse-engineer, scrape, or abuse the platform.</li>
        </ul>
      </Section>

      <Section title="Not investment advice">
        <p>Nothing on Edgekit — including strategy templates, backtest results, metrics, or equity curves — constitutes investment advice, financial advice, or a recommendation to buy or sell any financial instrument.</p>
        <p className="mt-2">Edgekit is a tool. You are the trader. All decisions are yours.</p>
      </Section>

      <Section title="Privacy">
        <p>We collect only what we need to run the service:</p>
        <ul>
          <li>Account data (email, name) via Clerk for authentication.</li>
          <li>Strategy graphs and backtest results you explicitly save.</li>
          <li>Basic usage telemetry (last seen date, backtest counts) stored in Supabase.</li>
        </ul>
        <p className="mt-2">We do not sell your data. We do not share it with third parties except the services powering the product (Clerk, Supabase, Vercel).</p>
        <p className="mt-2">API keys you enter in Resources are encrypted at rest using AES-256-GCM and stored only in your account.</p>
      </Section>

      <Section title="Data deletion">
        <p>To delete your account and all associated data, email us at <a href="mailto:support@edgekit.app" className="text-money hover:underline">support@edgekit.app</a> with the subject line "Delete my account". We'll process it within 7 business days.</p>
      </Section>

      <Section title="Contact">
        <p>Questions, concerns, or DMCA notices: <a href="mailto:support@edgekit.app" className="text-money hover:underline">support@edgekit.app</a></p>
        <p className="mt-2 text-muted text-[12px]">Last updated: May 2026</p>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-7">
      <h2 className="font-semibold text-[16px] mb-4">{title}</h2>
      <div className="text-[13.5px] text-ink2 leading-relaxed space-y-2 [&_ul]:list-disc [&_ul]:list-inside [&_ul]:space-y-1.5 [&_ul]:text-muted">
        {children}
      </div>
    </div>
  );
}
