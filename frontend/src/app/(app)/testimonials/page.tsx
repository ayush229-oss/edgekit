"use client";

import { useEffect, useState } from "react";

type Testimonial = {
  id:         string;
  name:       string;
  role:       string | null;
  text:       string;
  tags:       string[];
  avatar:     string | null;
  created_at: string;
};

// ── Testimonial submit form (client) ──────────────────────────────────────────
function SubmitForm() {
  const [form,      setForm]      = useState({ name: "", role: "", text: "" });
  const [submitted, setSubmitted] = useState(false);
  const [saving,    setSaving]    = useState(false);
  const [err,       setErr]       = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setErr(null);
    try {
      const res = await fetch("/api/testimonials", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(form),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.error || `Server error ${res.status}`);
      }
      setSubmitted(true);
    } catch (e: any) {
      setErr(e.message ?? "Something went wrong. Try again.");
    } finally {
      setSaving(false);
    }
  }

  if (submitted) {
    return (
      <div className="text-center py-10">
        <div className="w-12 h-12 mx-auto rounded-full bg-money/15 flex items-center justify-center text-money text-2xl mb-4">✓</div>
        <h3 className="font-semibold text-[16px] mb-2">Thank you!</h3>
        <p className="text-[13px] text-muted">We'll review your submission and publish it within 48 hours.</p>
      </div>
    );
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block">
          <span className="text-[12px] text-muted">Your name *</span>
          <input
            required
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="Arjun M."
            className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
          />
        </label>
        <label className="block">
          <span className="text-[12px] text-muted">Role / background</span>
          <input
            value={form.role}
            onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
            placeholder="Retail trader · NSE"
            className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
          />
        </label>
      </div>

      <label className="block">
        <span className="text-[12px] text-muted">Your experience with Edgekit *</span>
        <textarea
          required
          rows={4}
          value={form.text}
          onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
          placeholder="What did you use Edgekit for? What changed for you as a trader?"
          className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money resize-none"
        />
      </label>

      {err && <p className="text-[12px] text-down">{err}</p>}

      <button
        type="submit"
        disabled={saving}
        className="w-full py-2.5 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors disabled:opacity-60"
      >
        {saving ? "Submitting…" : "Submit testimonial"}
      </button>
      <p className="text-[11px] text-muted text-center">We review and publish within 48 hours. No spam.</p>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function TestimonialsPage() {
  const [testimonials, setTestimonials] = useState<Testimonial[]>([]);
  const [loading,      setLoading]      = useState(true);

  useEffect(() => {
    fetch("/api/testimonials")
      .then((r) => r.json())
      .then((data) => setTestimonials(Array.isArray(data) ? data : []))
      .catch(() => setTestimonials([]))
      .finally(() => setLoading(false));
  }, []);

  // Seed cards shown when DB has no approved testimonials yet
  const SEED: Testimonial[] = [
    { id: "s1", name: "Rohan S.",     role: "Intraday trader · NSE",   text: "Finally a backtester that moves at trader speed. I ran 40 variations of my OB strategy in one afternoon — that would've taken a week in Python.", tags: ["Speed", "OB strategy"], avatar: "R", created_at: "" },
    { id: "s2", name: "Priya K.",     role: "Swing trader · Crypto",   text: "The node system clicked for me instantly. I actually understand my own strategy now instead of copying setups blindly. Win rate went from 38% to 51%.", tags: ["Node builder", "Win rate"], avatar: "P", created_at: "" },
    { id: "s3", name: "Alex M.",      role: "Algo developer",           text: "I use it to validate ideas before coding them in Python. The Pine Script export sometimes means I never need to code at all.", tags: ["Pine Script", "Workflow"], avatar: "A", created_at: "" },
    { id: "s4", name: "Siddharth R.", role: "Prop firm trader",         text: "The equity curve reacts in real time as I tune parameters. That instant feedback loop is something I've never had in any tool before.", tags: ["Equity curve", "Iteration"], avatar: "S", created_at: "" },
    { id: "s5", name: "Mei L.",       role: "Quantitative analyst",     text: "I was skeptical about no-code trading tools. But the node system is clean and results match what I'd expect from coded strategies.", tags: ["Accuracy", "No-code"], avatar: "M", created_at: "" },
    { id: "s6", name: "Aditya P.",    role: "Retail trader · NSE/MCX", text: "Set up and ran my first backtest in 10 minutes. Never written a line of Pine Script. This is exactly what the market needed.", tags: ["Beginner-friendly", "Speed"], avatar: "A", created_at: "" },
  ];

  const displayList = testimonials.length > 0 ? testimonials : (!loading ? SEED : []);

  return (
    <div className="space-y-10">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Community</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Traders talk.</h1>
        <p className="text-muted mt-2 text-[15px]">
          Real traders sharing real experiences. No paid reviews, no incentives.
        </p>
      </div>

      {/* ── Testimonials grid ──────────────────────────────────────────────── */}
      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="card p-6 animate-pulse space-y-3">
              <div className="h-3 bg-surface2 rounded w-full" />
              <div className="h-3 bg-surface2 rounded w-4/5" />
              <div className="h-3 bg-surface2 rounded w-3/5" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {displayList.map((t) => (
            <div key={t.id} className="card p-6 flex flex-col gap-4">
              <p className="text-[13.5px] leading-relaxed text-ink2 flex-1">"{t.text}"</p>
              {t.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {t.tags.map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded-full bg-money/10 text-money text-[10px] font-medium">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-center gap-3 pt-3 border-t border-border">
                <div className="w-8 h-8 rounded-full bg-money/15 flex items-center justify-center text-money font-semibold text-[13px] shrink-0">
                  {t.avatar || t.name[0]}
                </div>
                <div>
                  <div className="font-medium text-[13px]">{t.name}</div>
                  {t.role && <div className="text-[11px] text-muted">{t.role}</div>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Submit form ────────────────────────────────────────────────────── */}
      <div className="card p-8 max-w-2xl">
        <h2 className="text-[20px] font-semibold mb-2">Share your experience</h2>
        <p className="text-[13px] text-muted mb-6 leading-relaxed">
          Using Edgekit? Your story helps other traders decide. We review all
          submissions before publishing.
        </p>
        <SubmitForm />
      </div>
    </div>
  );
}
