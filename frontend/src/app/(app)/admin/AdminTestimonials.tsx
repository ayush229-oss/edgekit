"use client";

import { useState } from "react";

type Testimonial = {
  id:         string;
  user_id:    string | null;
  name:       string;
  role:       string | null;
  text:       string;
  tags:       string[];
  status:     string;
  avatar:     string | null;
  created_at: string;
};

const STATUS_COLORS: Record<string, string> = {
  pending:  "bg-amber-100 text-amber-700 border-amber-200",
  approved: "bg-up/10 text-up border-up/20",
  rejected: "bg-down/10 text-down border-down/20",
};

export function AdminTestimonials({ initialData }: { initialData: Testimonial[] }) {
  const [items,  setItems]  = useState<Testimonial[]>(initialData);
  const [busy,   setBusy]   = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("pending");

  async function updateStatus(id: string, status: "approved" | "rejected") {
    setBusy(id);
    try {
      const res = await fetch(`/api/testimonials/${id}`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ status }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setItems((prev) => prev.map((t) => t.id === id ? { ...t, status } : t));
    } catch (e: any) {
      alert(`Failed to update: ${e.message}`);
    } finally {
      setBusy(null);
    }
  }

  const filtered = filter === "all" ? items : items.filter((t) => t.status === filter);

  const counts = {
    all:      items.length,
    pending:  items.filter((t) => t.status === "pending").length,
    approved: items.filter((t) => t.status === "approved").length,
    rejected: items.filter((t) => t.status === "rejected").length,
  };

  return (
    <div className="space-y-4">
      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {(["pending", "all", "approved", "rejected"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border
              ${filter === f
                ? "bg-money text-white border-money"
                : "bg-paper border-border text-muted hover:bg-surface2"}`}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            <span className="ml-1.5 opacity-70">({counts[f]})</span>
          </button>
        ))}
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="card p-10 text-center text-muted text-[13px]">
          No {filter === "all" ? "" : filter} testimonials.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((t) => (
            <div key={t.id} className="card p-5 space-y-3">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="font-medium text-[13px]">{t.name}</span>
                    {t.role && <span className="text-[11px] text-muted">· {t.role}</span>}
                    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${STATUS_COLORS[t.status] ?? "bg-surface2 text-muted border-border"}`}>
                      {t.status}
                    </span>
                  </div>
                  <p className="text-[13px] text-ink2 leading-relaxed">"{t.text}"</p>
                  {t.tags.length > 0 && (
                    <div className="flex gap-1 mt-2 flex-wrap">
                      {t.tags.map((tag) => (
                        <span key={tag} className="px-2 py-0.5 rounded-full bg-money/10 text-money text-[10px]">{tag}</span>
                      ))}
                    </div>
                  )}
                  <p className="text-[10px] text-muted mt-2">
                    {new Date(t.created_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                    {t.user_id && <span className="ml-2 font-mono">{t.user_id.slice(0, 12)}…</span>}
                  </p>
                </div>

                {/* Action buttons */}
                <div className="flex gap-2 shrink-0">
                  {t.status !== "approved" && (
                    <button
                      onClick={() => updateStatus(t.id, "approved")}
                      disabled={busy === t.id}
                      className="px-3 py-1.5 rounded-lg bg-up/10 text-up text-[12px] font-medium hover:bg-up/20 transition-colors disabled:opacity-60 border border-up/20"
                    >
                      {busy === t.id ? "…" : "Approve"}
                    </button>
                  )}
                  {t.status !== "rejected" && (
                    <button
                      onClick={() => updateStatus(t.id, "rejected")}
                      disabled={busy === t.id}
                      className="px-3 py-1.5 rounded-lg bg-down/10 text-down text-[12px] font-medium hover:bg-down/20 transition-colors disabled:opacity-60 border border-down/20"
                    >
                      {busy === t.id ? "…" : "Reject"}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
