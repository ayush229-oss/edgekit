"use client";

/**
 * Conversational custom node builder.
 *
 * Phase 1 "chat"    — multi-turn AI chat to define the node
 * Phase 2 "confirm" — review params/formula before saving
 * Phase 3 "saving"  — brief saving animation
 */
import { useEffect, useRef, useState } from "react";
import { v2NodeChat, type ChatMessage } from "@/lib/api";
import { saveUserNode, type UserNodeDef, type UserLane, LANE_COLORS } from "@/lib/userNodes";
import { SuggestionsPanel } from "./SuggestionsPanel";

type Phase = "chat" | "confirm" | "saving";

function greeting(): ChatMessage {
  return {
    role: "assistant",
    content:
      "Hey! Tell me what you want this node to do and I'll build it for you.\n\n" +
      "Examples:\n" +
      "• _\"An RSI that signals oversold below 30\"_ → alpha node\n" +
      "• _\"A custom moving average with adjustable period\"_ → indicator node\n" +
      "• _\"Only trade during London hours\"_ → filter node\n\n" +
      "What should this node do?",
  };
}

export function UserNodeBuilder({
  open,
  onClose,
  onCreated,
}: {
  open:       boolean;
  onClose:    () => void;
  onCreated?: (def: UserNodeDef) => void;
}) {
  const [phase,    setPhase]    = useState<Phase>("chat");
  const [messages, setMessages] = useState<ChatMessage[]>([greeting()]);
  const [input,    setInput]    = useState("");
  const [busy,     setBusy]     = useState(false);
  const [err,      setErr]      = useState<string | null>(null);
  const [draft,    setDraft]    = useState<any | null>(null);   // raw node_def from API
  const [label,    setLabel]    = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) {
      setPhase("chat");
      setMessages([greeting()]);
      setInput("");
      setBusy(false);
      setErr(null);
      setDraft(null);
      setLabel("");
      setTimeout(() => inputRef.current?.focus(), 80);
    }
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function send(text?: string) {
    const content = (text ?? input).trim();
    if (!content || busy) return;
    setInput("");
    setErr(null);
    const next: ChatMessage[] = [...messages, { role: "user", content }];
    setMessages(next);
    setBusy(true);
    try {
      const res = await v2NodeChat({ messages: next });
      if (res.type === "node_def") {
        setDraft(res.def);
        setLabel((res.def as any).label || "Custom node");
        const summary = buildSummaryMessage(res.def);
        setMessages((m) => [...m, { role: "assistant", content: summary }]);
        setPhase("confirm");
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.content }]);
      }
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }

  function buildSummaryMessage(def: any): string {
    const lane     = def.lane ?? "indicator";
    const paramCnt = (def.params_spec ?? []).length;
    const paramList = (def.params_spec ?? [])
      .map((p: any) => `**${p.label}** (${p.type}, default ${p.default})`)
      .join(", ");
    return (
      `✓ Got it! Here's what I'll create:\n\n` +
      `**${def.label}** — *${lane}* node\n` +
      `${def.description ?? ""}\n\n` +
      `**Variables (${paramCnt}):** ${paramCnt > 0 ? paramList : "none"}\n\n` +
      `Review the details below and click **Save to palette** when ready.`
    );
  }

  function save() {
    if (!draft) return;
    setPhase("saving");
    const saved = saveUserNode({
      label:       label.trim() || draft.label,
      description: draft.description ?? "",
      lane:        draft.lane as UserLane,
      outputs:     draft.outputs ?? [],
      extra_inputs: draft.extra_inputs ?? [],
      params_spec: draft.params_spec ?? [],
      formulas:    draft.formulas ?? {},
    });
    onCreated?.(saved);
    setTimeout(() => { onClose(); }, 600);
  }

  function backToChat() {
    setPhase("chat");
    setDraft(null);
    setMessages((m) => [
      ...m,
      { role: "assistant", content: "No problem — let's refine it. What would you like to change?" },
    ]);
    setTimeout(() => inputRef.current?.focus(), 80);
  }

  function close() {
    onClose();
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  if (!open) return null;

  const laneColor = draft ? (LANE_COLORS[draft.lane as UserLane] ?? "#6B7280") : "#6B7280";
  const params    = draft?.params_spec ?? [];
  const outputs   = draft?.outputs ?? [];
  const formulas  = draft?.formulas ?? {};

  return (
    <div className="fixed inset-0 z-50 bg-paper/95 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl shadow-float w-full max-w-3xl h-[80vh] flex flex-col overflow-hidden">

        {/* Header */}
        <div className="px-5 py-3.5 border-b border-border flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <span className="text-[10px] uppercase tracking-widest text-muted font-semibold">AI Generated</span>
            {draft && (
              <span className="text-[10px] px-2 py-0.5 rounded-full font-medium text-white"
                style={{ background: laneColor }}>
                {draft.lane}
              </span>
            )}
          </div>
          <h2 className="text-[15px] font-semibold text-ink absolute left-1/2 -translate-x-1/2">
            Create a custom node
          </h2>
          <button onClick={close} className="text-muted hover:text-ink text-xl leading-none px-1">×</button>
        </div>

        {/* Body */}
        <div className="flex-1 flex overflow-hidden">

          {/* ── CHAT PHASE ────────────────────────────────────────────── */}
          {phase === "chat" && (
            <>
              {/* Messages */}
              <div className="flex-1 flex flex-col overflow-hidden">
                <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
                  {messages.map((m, i) => (
                    <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div className={`max-w-[82%] rounded-xl px-3.5 py-2.5 text-[13px] leading-relaxed ${
                        m.role === "user"
                          ? "bg-sage text-white rounded-br-sm"
                          : "bg-cream2 border border-border text-ink rounded-bl-sm"
                      }`}>
                        {m.content.split("\n").map((line, j) => {
                          const parts = line.split(/(\*\*[^*]+\*\*|\*[^*]+\*|_[^_]+_)/g);
                          return (
                            <p key={j} className={j > 0 ? "mt-1" : ""}>
                              {parts.map((part, k) => {
                                if (part.startsWith("**") && part.endsWith("**"))
                                  return <strong key={k}>{part.slice(2, -2)}</strong>;
                                if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_")))
                                  return <em key={k}>{part.slice(1, -1)}</em>;
                                return part;
                              })}
                            </p>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                  {busy && (
                    <div className="flex justify-start">
                      <div className="bg-cream2 border border-border rounded-xl rounded-bl-sm px-4 py-2.5">
                        <span className="text-muted text-[13px] animate-pulse">Thinking…</span>
                      </div>
                    </div>
                  )}
                  {err && (
                    <div className="rounded-lg bg-down/5 border border-down/30 p-3 text-[12.5px] text-down">
                      {err}
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>

                {/* Input */}
                <div className="px-4 pb-4 shrink-0">
                  <div className="flex gap-2 items-end bg-cream border border-border rounded-xl px-3 py-2 focus-within:ring-1 focus-within:ring-sage/40">
                    <textarea
                      ref={inputRef}
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={handleKey}
                      disabled={busy}
                      rows={1}
                      placeholder="Describe what this node should do…"
                      className="flex-1 bg-transparent text-[13px] resize-none focus:outline-none leading-relaxed placeholder:text-muted/60"
                      style={{ maxHeight: "100px", overflowY: "auto" }}
                    />
                    <button
                      onClick={() => send()}
                      disabled={busy || !input.trim()}
                      className="shrink-0 px-3 py-1.5 rounded-lg bg-sage text-white text-[12.5px] font-medium
                                 hover:bg-sageMid transition-colors disabled:opacity-40"
                    >
                      Send →
                    </button>
                  </div>
                </div>
              </div>

              {/* Suggestions panel */}
              <SuggestionsPanel
                messages={messages}
                onSuggest={(text) => { setInput(text); inputRef.current?.focus(); }}
                label="Suggestions"
              />
            </>
          )}

          {/* ── CONFIRM PHASE ─────────────────────────────────────────── */}
          {phase === "confirm" && draft && (
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">

              {/* Lane badge + name */}
              <div className="flex items-center gap-3 p-3 rounded-xl border"
                style={{ borderColor: laneColor + "40", background: laneColor + "08" }}>
                <span className="w-4 h-4 rounded-full shrink-0" style={{ background: laneColor }} />
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] uppercase tracking-widest text-muted font-semibold">{draft.lane} node</div>
                  <div className="text-[13px] font-medium text-ink mt-0.5">{draft.description}</div>
                </div>
              </div>

              {/* Editable name */}
              <div>
                <label className="text-[11px] text-muted font-medium uppercase tracking-wide">Node name</label>
                <input
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  className="w-full mt-1.5 rounded-lg bg-paper border border-border px-3 py-2 text-[13.5px]
                             focus:outline-none focus:ring-1 focus:ring-sage"
                />
              </div>

              {/* Variables table */}
              <div>
                <div className="text-[11px] text-muted font-medium uppercase tracking-wide mb-1.5">
                  Variables ({params.length})
                </div>
                {params.length > 0 ? (
                  <div className="rounded-lg border border-border overflow-hidden">
                    <table className="w-full text-[12px]">
                      <thead>
                        <tr className="bg-cream2 border-b border-border">
                          <th className="text-left px-3 py-2 text-muted font-medium">Name</th>
                          <th className="text-left px-3 py-2 text-muted font-medium">Type</th>
                          <th className="text-right px-3 py-2 text-muted font-medium">Default</th>
                          <th className="text-right px-3 py-2 text-muted font-medium">Range</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {params.map((p: any) => (
                          <tr key={p.key} className="bg-paper">
                            <td className="px-3 py-2 font-mono text-ink font-medium">{p.label}</td>
                            <td className="px-3 py-2 text-muted">{p.type}</td>
                            <td className="px-3 py-2 text-right font-mono text-ink">{p.default}</td>
                            <td className="px-3 py-2 text-right text-muted font-mono">
                              {p.min !== undefined ? `${p.min}–${p.max}` : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-[11.5px] text-muted italic">No adjustable parameters</p>
                )}
              </div>

              {/* Outputs (indicator only) */}
              {draft.lane === "indicator" && outputs.length > 0 && (
                <div>
                  <div className="text-[11px] text-muted font-medium uppercase tracking-wide mb-1.5">
                    Outputs ({outputs.length})
                  </div>
                  <div className="rounded-lg border border-border divide-y divide-border overflow-hidden">
                    {outputs.map((o: any) => (
                      <div key={o.name} className="flex items-center justify-between px-3 py-2 bg-paper">
                        <span className="font-mono text-[12.5px] text-ink">{o.name}</span>
                        <span className="text-[10.5px] text-muted px-2 py-0.5 rounded bg-cream2 border border-border">
                          {o.type}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Formula */}
              <div>
                <div className="text-[11px] text-muted font-medium uppercase tracking-wide mb-1.5">Formula</div>
                <div className="rounded-lg border border-border bg-ink/[0.02] divide-y divide-border overflow-hidden">
                  {Object.entries(formulas).map(([port, expr]) => (
                    <div key={port} className="px-3 py-2.5">
                      {Object.keys(formulas).length > 1 && (
                        <div className="text-[10px] text-muted font-mono mb-1">{port}</div>
                      )}
                      <code className="text-[11.5px] text-ink break-all leading-relaxed block font-mono">
                        {expr as string}
                      </code>
                    </div>
                  ))}
                </div>
              </div>

              <p className="text-[11px] text-muted italic">
                Saved under <strong>My Custom Nodes</strong> — lives in your browser. Wire it to other nodes on the canvas.
              </p>
            </div>
          )}

          {/* ── SAVING PHASE ──────────────────────────────────────────── */}
          {phase === "saving" && (
            <div className="flex-1 flex flex-col items-center justify-center gap-3">
              <div className="text-4xl animate-pulse">💾</div>
              <p className="text-[13px] text-muted">Saving to palette…</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-border flex items-center justify-between bg-cream2/30 shrink-0">
          {phase === "chat" && (
            <button onClick={close} className="text-[12.5px] text-muted hover:text-ink px-2 py-1.5">
              Cancel
            </button>
          )}

          {phase === "confirm" && (
            <>
              <button
                onClick={backToChat}
                className="text-[12.5px] text-muted hover:text-ink px-2 py-1.5"
              >
                ← Refine
              </button>
              <button
                onClick={save}
                disabled={!label.trim()}
                className="px-4 py-2 rounded-lg bg-sage text-white text-[13px] font-medium
                           hover:bg-sageMid transition-colors disabled:opacity-50"
              >
                Save to palette →
              </button>
            </>
          )}

          {phase === "saving" && (
            <span className="text-[12px] text-muted ml-auto">Saving…</span>
          )}
        </div>
      </div>
    </div>
  );
}
