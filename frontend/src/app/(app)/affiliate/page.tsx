"use client";

import { useState } from "react";

export default function AffiliatePage() {
  return (
    <div className="space-y-8 max-w-2xl">

      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Affiliate</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Refer traders. Earn rewards.</h1>
        <p className="text-muted mt-2 text-[15px]">
          Edgekit's affiliate program is coming soon. Join the waitlist to be first in line.
        </p>
      </div>

      <div className="card p-8 space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          {[
            { icon: "🔗", title: "Your unique link", body: "Share your personal referral link with traders in your network." },
            { icon: "📈", title: "Earn per signup",  body: "Get a commission for every trader who signs up and upgrades via your link." },
            { icon: "💸", title: "Monthly payouts",  body: "Earnings are paid out monthly. No minimum threshold." },
          ].map((item) => (
            <div key={item.title} className="flex flex-col gap-2">
              <div className="text-3xl">{item.icon}</div>
              <h3 className="font-semibold text-[14px]">{item.title}</h3>
              <p className="text-[12.5px] text-muted leading-relaxed">{item.body}</p>
            </div>
          ))}
        </div>

        <div className="border-t border-border pt-6">
          <p className="text-[13px] font-medium mb-3">Get notified when the program launches</p>
          <AffiliateWaitlistForm />
        </div>
      </div>
    </div>
  );
}

function AffiliateWaitlistForm() {
  const [email,     setEmail]     = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [saving,    setSaving]    = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch("/api/affiliate-waitlist", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ email }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error || `Error ${res.status}`);
      }
      setSubmitted(true);
    } catch (err: any) {
      alert(err.message ?? "Failed to submit. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (submitted) {
    return (
      <p className="text-[13px] text-up font-medium">✓ You're on the list! We'll email you when the program launches.</p>
    );
  }

  return (
    <form className="flex gap-2" onSubmit={handleSubmit}>
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="flex-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
      />
      <button
        type="submit"
        disabled={saving}
        className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors whitespace-nowrap disabled:opacity-60"
      >
        {saving ? "Saving…" : "Notify me"}
      </button>
    </form>
  );
}
