"use client";
// force-dynamic is implicit for "use client" pages — no export needed
import { useState } from "react";

const CATEGORIES = ["Builder / Nodes", "Strategies & Templates", "Analytics", "Data sources", "Pine Script export", "Performance", "Other"];

export default function SuggestionsPage() {
  const [form,      setForm]      = useState({ category: "Builder / Nodes", title: "", detail: "" });
  const [submitted, setSubmitted] = useState(false);
  const [saving,    setSaving]    = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch("/api/suggestions", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(form),
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

  return (
    <div className="space-y-8 max-w-2xl">

      <div>
        <p className="text-[11px] uppercase tracking-[0.25em] text-money font-semibold mb-2">Feedback</p>
        <h1 className="text-[32px] font-bold tracking-tight text-ink">Suggestions</h1>
        <p className="text-muted mt-2 text-[15px]">
          Tell us what to build next. Every request is read by the team.
        </p>
      </div>

      <div className="card p-7">
        {!submitted ? (
          <form className="space-y-5" onSubmit={handleSubmit}>
            <label className="block">
              <span className="text-[12px] text-muted">Category</span>
              <select
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
              >
                {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>

            <label className="block">
              <span className="text-[12px] text-muted">Feature title *</span>
              <input
                required
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="e.g. Multi-timeframe backtesting"
                className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money"
              />
            </label>

            <label className="block">
              <span className="text-[12px] text-muted">Details (optional)</span>
              <textarea
                rows={4}
                value={form.detail}
                onChange={(e) => setForm((f) => ({ ...f, detail: e.target.value }))}
                placeholder="Describe the problem you're trying to solve and how this feature would help…"
                className="w-full mt-1 rounded-lg bg-paper border border-border px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-money resize-none"
              />
            </label>

            <button
              type="submit"
              disabled={saving}
              className="w-full py-2.5 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors disabled:opacity-60"
            >
              {saving ? "Submitting…" : "Submit suggestion"}
            </button>
          </form>
        ) : (
          <div className="text-center py-10">
            <div className="w-12 h-12 mx-auto rounded-full bg-money/15 flex items-center justify-center text-money text-2xl mb-4">💡</div>
            <h3 className="font-semibold text-[16px] mb-2">Got it — thank you!</h3>
            <p className="text-[13px] text-muted max-w-sm mx-auto">We read every suggestion. Highly voted features move up the roadmap.</p>
            <button
              onClick={() => { setSubmitted(false); setForm({ category: "Builder / Nodes", title: "", detail: "" }); }}
              className="mt-6 text-[13px] text-money hover:underline font-medium"
            >
              Submit another →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
