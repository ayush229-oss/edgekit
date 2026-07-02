"use client";

import { useEffect, useRef, useState } from "react";
import {
  v2Chat, hasUserAIKey, getAIProvider, getAIModel, setAIModel, AI_MODEL_OPTIONS,
  type ChatMessage, type V2Graph, type GraphDecision, type GraphDecisionSetting,
} from "@/lib/api";
import Link from "next/link";
import { SuggestionsPanel } from "./SuggestionsPanel";

// ── Multi-chat persistence ─────────────────────────────────────────────────
const CHATS_KEY  = "edgekit.chats.v2";
const ACTIVE_KEY = "edgekit.chat.active";
const LEGACY_KEY = "edgekit.chat.v1";

type SavedChat = {
  id:        string;
  name:      string;
  createdAt: number;
  updatedAt: number;
  messages:  ChatMessage[];
  graph:     V2Graph | null;
  decisions: GraphDecision[];
};

function genId(): string {
  return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

function chatName(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === "user");
  if (!first) return "New Chat";
  const t = typeof first.content === "string" ? first.content : "New Chat";
  return t.length > 45 ? t.slice(0, 45) + "…" : t;
}

function formatDate(ts: number): string {
  const d   = new Date(ts);
  const now = new Date();
  const age = now.getTime() - d.getTime();
  if (age < 86_400_000)         return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (age < 7 * 86_400_000)     return d.toLocaleDateString([], { weekday: "short" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function loadAllChats(): SavedChat[] {
  if (typeof window === "undefined") return [];
  try {
    const existing = window.localStorage.getItem(CHATS_KEY);
    if (existing) return JSON.parse(existing) as SavedChat[];

    // Migrate from legacy single-chat format
    const legacy = window.localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy) as { messages: ChatMessage[]; graph: V2Graph | null; decisions: GraphDecision[] };
      if (parsed?.messages?.length > 1) {
        const migrated: SavedChat = {
          id: genId(), name: chatName(parsed.messages),
          createdAt: Date.now(), updatedAt: Date.now(),
          messages: parsed.messages, graph: parsed.graph ?? null, decisions: parsed.decisions ?? [],
        };
        saveAllChats([migrated]);
        window.localStorage.removeItem(LEGACY_KEY);
        return [migrated];
      }
    }
    return [];
  } catch { return []; }
}

function saveAllChats(chats: SavedChat[]): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(CHATS_KEY, JSON.stringify(chats)); } catch {}
}

function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(ACTIVE_KEY); } catch { return null; }
}

function saveActiveId(id: string): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(ACTIVE_KEY, id); } catch {}
}

// ── Starters ───────────────────────────────────────────────────────────────
const STARTER_PROMPTS = [
  "EMA 20 crosses above EMA 50 — buy, ATR stop, trail behind candles",
  "RSI drops below 30 and bounces — buy, stop below swing low, 2R target",
  "Donchian 20-bar breakout, ATR-sized position, turtle-style exit",
  "SMC: liquidity sweep into order block entry, limit order, 3R target",
  "Gold breaks above 20-day high, tight ATR stop, let winners run",
  "MACD crossover above zero — buy, fixed 30-pip stop, 3R trail",
];

// ── Component ──────────────────────────────────────────────────────────────
export function StrategyChat({
  open,
  onClose,
  onLoadGraph,
  symbol        = "XAUUSD",
  timeframe     = "M15",
  currentGraph  = null,
  resultSummary = null,
}: {
  open:          boolean;
  onClose:       () => void;
  onLoadGraph:   (g: V2Graph, name: string) => void;
  symbol?:       string;
  timeframe?:    string;
  currentGraph?:  V2Graph | null;
  resultSummary?: string | null;
}) {
  const editing = !!(currentGraph?.nodes?.length);

  const [allChats,    setAllChats]    = useState<SavedChat[]>([]);
  const [activeId,    setActiveId]    = useState<string | null>(null);
  const [messages,    setMessages]    = useState<ChatMessage[]>([]);
  const [input,       setInput]       = useState("");
  const [busy,        setBusy]        = useState(false);
  const [graph,       setGraph]       = useState<V2Graph | null>(null);
  const [decisions,   setDecisions]   = useState<GraphDecision[]>([]);
  const [err,         setErr]         = useState<string | null>(null);
  const [hasKey,      setHasKey]      = useState(false);
  const [provider,    setProvider]    = useState("gemini");
  const [model,       setModel]       = useState("");
  const [image,       setImage]       = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(true);
  const [openQuestions, setOpenQuestions] = useState<string[]>([]);

  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  // ── Helpers ──────────────────────────────────────────────────────────────

  function greeting(): ChatMessage {
    return {
      role: "assistant",
      content: editing
        ? `I'm SOROS. I can see your current strategy${resultSummary ? ` (last backtest: ${resultSummary})` : ""}. Tell me what to change — e.g. "loosen it so it actually trades", "remove the AND condition", or "add a trend filter" — and I'll update it.`
        : "I'm SOROS, your AI strategy builder. Tell me your trading idea in plain English — no jargon needed. For example: \"Buy gold when it breaks above a recent high, sell when it drops back below.\" What's your idea?",
    };
  }

  function readImage(file: File | null | undefined) {
    if (!file || !file.type.startsWith("image/")) return;
    if (file.size > 5 * 1024 * 1024) { setErr("Reference image too large (max 5 MB)."); return; }
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result as string);
    reader.readAsDataURL(file);
  }

  function persistCurrent(
    msgs: ChatMessage[], g: V2Graph | null, dec: GraphDecision[],
    id: string | null, chats: SavedChat[]
  ): SavedChat[] {
    if (!id || msgs.length === 0) return chats;
    const updated = chats.map((c) =>
      c.id === id
        ? { ...c, messages: msgs, graph: g, decisions: dec, updatedAt: Date.now(), name: chatName(msgs) }
        : c
    );
    saveAllChats(updated);
    return updated;
  }

  // ── Init on open ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (!open) return;
    setHasKey(hasUserAIKey());
    setProvider(getAIProvider());
    setModel(getAIModel());

    const chats = loadAllChats();
    setAllChats(chats);

    // Only initialize conversation state on first open (state is preserved across close/reopen).
    if (messages.length === 0) {
      const savedId = loadActiveId();
      const active  = chats.find((c) => c.id === savedId) ?? chats[chats.length - 1] ?? null;

      if (active) {
        setActiveId(active.id);
        setMessages(active.messages);
        setGraph(active.graph);
        setDecisions(active.decisions);
      } else {
        const newId = genId();
        const nc: SavedChat = {
          id: newId, name: "New Chat",
          createdAt: Date.now(), updatedAt: Date.now(),
          messages: [greeting()], graph: null, decisions: [],
        };
        saveAllChats([nc]);
        saveActiveId(newId);
        setAllChats([nc]);
        setActiveId(newId);
        setMessages([greeting()]);
      }
    }

    setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Persist to localStorage whenever conversation changes.
  useEffect(() => {
    if (!open || messages.length === 0) return;
    setAllChats((prev) => persistCurrent(messages, graph, decisions, activeId, prev));
  }, [messages, graph, decisions]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (open && !busy) inputRef.current?.focus();
  }, [busy, open]);

  // ── Chat management ───────────────────────────────────────────────────────

  function newChat() {
    const saved = persistCurrent(messages, graph, decisions, activeId, allChats);
    const newId = genId();
    const nc: SavedChat = {
      id: newId, name: "New Chat",
      createdAt: Date.now(), updatedAt: Date.now(),
      messages: [greeting()], graph: null, decisions: [],
    };
    const next = [nc, ...saved];
    saveAllChats(next);
    saveActiveId(newId);
    setAllChats(next);
    setActiveId(newId);
    setMessages([greeting()]);
    setInput("");
    setGraph(null);
    setDecisions([]);
    setOpenQuestions([]);
    setErr(null);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function switchChat(id: string) {
    if (id === activeId) { setShowHistory(false); return; }
    const saved  = persistCurrent(messages, graph, decisions, activeId, allChats);
    const target = saved.find((c) => c.id === id);
    if (!target) return;
    saveActiveId(id);
    setAllChats(saved);
    setActiveId(id);
    setMessages(target.messages);
    setGraph(target.graph);
    setDecisions(target.decisions);
    setOpenQuestions([]);
    setErr(null);
    setInput("");
    setShowHistory(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  }

  function deleteChat(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    const remaining = allChats.filter((c) => c.id !== id);

    if (id === activeId) {
      if (remaining.length > 0) {
        const next = remaining[0];
        saveActiveId(next.id);
        setActiveId(next.id);
        setMessages(next.messages);
        setGraph(next.graph);
        setDecisions(next.decisions);
      } else {
        const newId = genId();
        const nc: SavedChat = {
          id: newId, name: "New Chat",
          createdAt: Date.now(), updatedAt: Date.now(),
          messages: [greeting()], graph: null, decisions: [],
        };
        remaining.push(nc);
        saveActiveId(newId);
        setActiveId(newId);
        setMessages([greeting()]);
        setGraph(null);
        setDecisions([]);
      }
    }

    saveAllChats(remaining);
    setAllChats(remaining);
    setOpenQuestions([]);
    setErr(null);
  }

  function close() { onClose(); }

  // ── Send ─────────────────────────────────────────────────────────────────

  async function send() {
    const text = input.trim();
    if ((!text && !image) || busy) return;
    setErr(null);
    setInput("");
    const img = image;
    setImage(null);

    const display = text || "🖼 Chart attached";
    const next: ChatMessage[] = [...messages, { role: "user", content: display }];
    setMessages(next);
    setBusy(true);

    try {
      const res = await v2Chat({
        messages: next, symbol, timeframe,
        current_graph:  editing ? currentGraph : null,
        result_summary: editing ? resultSummary : null,
        image: img ?? undefined,
      });
      if (res.type === "graph") {
        setGraph(res.graph);
        setDecisions(res.decisions ?? []);
        setOpenQuestions(res.open_questions ?? []);
        const assumed = (res.decisions ?? []).reduce((n, d) => n + d.settings.filter((s) => !s.user_specified).length, 0);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: `I've built your strategy: **${res.graph.name || "Custom strategy"}** (${res.graph.nodes.length} nodes).` +
              (assumed > 0
                ? ` I filled in **${assumed} value${assumed > 1 ? "s" : ""} you didn't mention** — check the amber ones below and edit them before loading.`
                : ` Review it below and click "Load onto canvas" when you're happy.`),
          },
        ]);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.content }]);
      }
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sendPrompt(text: string) {
    setInput("");
    setErr(null);
    const next: ChatMessage[] = [...messages, { role: "user", content: text }];
    setMessages(next);
    setBusy(true);
    try {
      const res = await v2Chat({
        messages: next, symbol, timeframe,
        current_graph:  editing ? currentGraph : null,
        result_summary: editing ? resultSummary : null,
      });
      if (res.type === "graph") {
        setGraph(res.graph);
        setDecisions(res.decisions ?? []);
        setOpenQuestions(res.open_questions ?? []);
        const assumed = (res.decisions ?? []).reduce((n, d) => n + d.settings.filter((s) => !s.user_specified).length, 0);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: `I've built your strategy: **${res.graph.name || "Custom strategy"}** (${res.graph.nodes.length} nodes).` +
              (assumed > 0
                ? ` I filled in **${assumed} value${assumed > 1 ? "s" : ""} you didn't mention** — check the amber ones below and edit them before loading.`
                : ` Review it below and click "Load onto canvas" when you're happy.`),
          },
        ]);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.content }]);
      }
    } catch (e: any) {
      setErr(e?.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  // ── Edit an AI-assumed value before loading — syncs decisions AND graph ──
  function updateDecision(nodeId: string, key: string, raw: string) {
    setDecisions((prev) => prev.map((d) => {
      if (d.node_id !== nodeId) return d;
      return {
        ...d,
        settings: d.settings.map((s) => {
          if (s.key !== key) return s;
          let v: any = raw;
          if (s.type === "int")   { const n = parseInt(raw, 10); if (isNaN(n)) return s; v = n; }
          if (s.type === "float") { const n = parseFloat(raw);   if (isNaN(n)) return s; v = n; }
          return { ...s, value: v, is_default: v === s.default, user_specified: true };
        }),
      };
    }));
    setGraph((g) => {
      if (!g) return g;
      return {
        ...g,
        nodes: g.nodes.map((n) => {
          if (n.id !== nodeId) return n;
          const setting = decisions.find((d) => d.node_id === nodeId)?.settings.find((s) => s.key === key);
          let v: any = raw;
          if (setting?.type === "int")   { const p = parseInt(raw, 10); if (isNaN(p)) return n; v = p; }
          if (setting?.type === "float") { const p = parseFloat(raw);   if (isNaN(p)) return n; v = p; }
          return { ...n, params: { ...(n.params ?? {}), [key]: v } };
        }),
      };
    });
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }

  function loadGraph() {
    if (!graph) return;
    onLoadGraph(graph, graph.name || "AI Strategy");
    close();
  }

  if (!open) return null;

  const sortedChats = [...allChats].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <div className="fixed inset-0 z-50 bg-paper/95 backdrop-blur-sm flex">

      {/* ── History Sidebar ─────────────────────────────────────────────── */}
      <div
        className={`flex-shrink-0 border-r border-border bg-paper flex flex-col transition-[width] duration-200 overflow-hidden ${
          showHistory ? "w-64" : "w-0"
        }`}
      >
        <div className="px-3 py-3 border-b border-border flex items-center justify-between shrink-0">
          <span className="text-[11px] uppercase tracking-widest text-muted font-semibold">Saved Chats</span>
          <button
            onClick={newChat}
            className="text-[11px] px-2 py-1 rounded border border-border text-muted hover:text-ink hover:bg-surface2 transition-colors whitespace-nowrap"
          >
            + New
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {sortedChats.length === 0 ? (
            <p className="text-[12px] text-muted px-3 py-4">No saved chats yet.</p>
          ) : (
            sortedChats.map((c) => (
              <div
                key={c.id}
                onClick={() => switchChat(c.id)}
                className={`group px-3 py-2.5 cursor-pointer border-b border-border/40 flex items-start gap-2 hover:bg-surface2 transition-colors ${
                  c.id === activeId ? "bg-surface2 border-l-2 border-l-money" : ""
                }`}
              >
                <div className="flex-1 min-w-0">
                  <div className={`text-[12.5px] truncate leading-snug ${c.id === activeId ? "text-ink font-medium" : "text-ink/80"}`}>
                    {c.name}
                  </div>
                  <div className="text-[10.5px] text-muted mt-0.5">
                    {formatDate(c.updatedAt)} · {c.messages.filter((m) => m.role === "user").length} msgs
                  </div>
                </div>
                <button
                  onClick={(e) => deleteChat(c.id, e)}
                  title="Delete chat"
                  className="opacity-0 group-hover:opacity-100 text-muted hover:text-down text-[14px] mt-0.5 shrink-0 transition-opacity leading-none"
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Main Chat Area ───────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface">

        {/* Header */}
        <div className="px-5 py-4 border-b border-border flex items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowHistory((v) => !v)}
              title={showHistory ? "Hide saved chats" : "Show saved chats"}
              className={`p-1.5 rounded-lg border transition-colors text-[15px] leading-none ${
                showHistory
                  ? "border-money/40 bg-money/10 text-money"
                  : "border-border text-muted hover:text-ink hover:bg-surface2"
              }`}
            >
              ☰
            </button>
            <div>
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-[10px] uppercase tracking-widest text-money font-semibold">SOROS</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-highlight text-highlightInk font-medium">AI</span>
              </div>
              <h2 className="text-[17px] font-semibold text-ink">
                {editing ? "Refine with SOROS" : "Build with SOROS"}
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <label className="flex items-center gap-1.5" title="Choose which AI model answers">
              <span className="text-[10px] uppercase tracking-wide text-muted">Model</span>
              <select
                value={model}
                onChange={(e) => { setModel(e.target.value); setAIModel(e.target.value); }}
                className="rounded-lg bg-paper border border-border px-2 py-1 text-[12px] text-ink
                           focus:outline-none focus:ring-1 focus:ring-money max-w-[150px]"
              >
                {(AI_MODEL_OPTIONS[provider] ?? AI_MODEL_OPTIONS.gemini).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
            <button
              onClick={newChat}
              title="Start a fresh conversation"
              className="text-[11px] px-2 py-1 rounded border border-border text-muted hover:text-ink hover:bg-surface2 transition-colors"
            >
              New chat
            </button>
            <button onClick={close} className="text-muted hover:text-ink text-2xl leading-none px-2">×</button>
          </div>
        </div>

        {/* Free built-in notice */}
        {!hasKey && (
          <div className="mx-5 mt-3 shrink-0 rounded-lg border border-sage/30 bg-sage/10 px-3 py-2 text-[12px] text-ink/80">
            SOROS is powered by <strong>Claude</strong> — free daily limit applies.{" "}
            <Link href="/resources" className="underline font-medium" onClick={close}>
              Add your own AI key
            </Link>{" "}
            for unlimited use.
          </div>
        )}

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              {m.role === "assistant" && (
                <div className="w-7 h-7 rounded-full bg-money/15 flex items-center justify-center text-money text-[13px] shrink-0 mt-0.5 mr-2">
                  S
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed ${
                  m.role === "user"
                    ? "bg-money text-white rounded-br-sm"
                    : "bg-surface2 text-ink rounded-bl-sm border border-border"
                }`}
              >
                {m.content.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
                  part.startsWith("**") && part.endsWith("**")
                    ? <strong key={j}>{part.slice(2, -2)}</strong>
                    : <span key={j}>{part}</span>
                )}
              </div>
            </div>
          ))}

          {/* Starter prompts — fresh chat only */}
          {!editing && messages.length === 1 && messages[0].role === "assistant" && !busy && (
            <div className="mt-1 ml-9">
              <p className="text-[11px] text-muted mb-2 uppercase tracking-wide font-medium">Try an example</p>
              <div className="flex flex-col gap-1.5">
                {STARTER_PROMPTS.map((p) => (
                  <button
                    key={p}
                    onClick={() => sendPrompt(p)}
                    className="text-left text-[12.5px] px-3 py-2 rounded-xl border border-border bg-paper hover:bg-surface2 hover:border-money/40 transition-colors text-ink/80 hover:text-ink"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}

          {busy && (
            <div className="flex justify-start">
              <div className="w-7 h-7 rounded-full bg-money/15 flex items-center justify-center text-money text-[13px] shrink-0 mt-0.5 mr-2">S</div>
              <div className="bg-surface2 border border-border rounded-2xl rounded-bl-sm px-4 py-3 text-[13.5px] text-muted">
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" style={{ animationDelay: "300ms" }} />
                </span>
              </div>
            </div>
          )}

          {err && (
            <div className="rounded-lg border border-down/40 bg-down/5 px-3 py-2.5 text-[12.5px] text-down">
              {err}
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Review panel — every variable, split into "yours" vs "AI-assumed" (editable) */}
        {graph && decisions.length > 0 && (
          <div className="mx-5 mb-2 shrink-0 rounded-xl border border-border bg-paper px-4 py-3 max-h-[240px] overflow-y-auto">
            <div className="text-[11px] font-semibold text-ink mb-2">
              Review before loading{" "}
              <span className="font-normal text-muted">
                — <span className="text-amber-700">⚠ amber</span> = I assumed this (you didn't say it). Edit any value right here.
              </span>
            </div>
            <div className="space-y-2">
              {decisions.map((d) => (
                <div key={d.node_id} className="text-[11.5px]">
                  <div className="font-medium text-ink mb-1">
                    {d.node_label} <span className="text-[9.5px] text-muted uppercase">{d.lane}</span>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {d.settings.map((s: GraphDecisionSetting) => (
                      <label
                        key={s.key}
                        title={s.user_specified ? "You specified this value" : "AI assumed this value — you never mentioned it"}
                        className={`flex items-center gap-1.5 rounded-lg border px-2 py-1 ${
                          s.user_specified
                            ? "border-up/40 bg-up/5"
                            : "border-amber-400/60 bg-amber-50"
                        }`}
                      >
                        <span className="text-[10px]">{s.user_specified ? "✓" : "⚠"}</span>
                        <span className="text-[10.5px] text-muted">{s.label}</span>
                        {s.options ? (
                          <select
                            value={String(s.value)}
                            onChange={(e) => updateDecision(d.node_id, s.key, e.target.value)}
                            className="text-[11px] bg-transparent border-b border-border focus:outline-none font-mono"
                          >
                            {s.options.map((o) => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (s.type === "int" || s.type === "float") ? (
                          <input
                            type="number"
                            value={s.value}
                            min={s.min ?? undefined}
                            max={s.max ?? undefined}
                            step={s.step ?? (s.type === "int" ? 1 : 0.1)}
                            onChange={(e) => updateDecision(d.node_id, s.key, e.target.value)}
                            className="w-16 text-[11px] bg-transparent border-b border-border focus:outline-none font-mono"
                          />
                        ) : (
                          <input
                            type="text"
                            value={String(s.value)}
                            onChange={(e) => updateDecision(d.node_id, s.key, e.target.value)}
                            className="w-20 text-[11px] bg-transparent border-b border-border focus:outline-none font-mono"
                          />
                        )}
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            {openQuestions.length > 0 && (
              <div className="mt-2.5 pt-2 border-t border-border/60">
                <div className="text-[10.5px] font-semibold text-amber-800 mb-1">Worth deciding yourself:</div>
                {openQuestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => { setInput(q.replace(/^I assumed /i, "About: ")); inputRef.current?.focus(); }}
                    className="block text-left text-[11px] text-ink/80 hover:text-ink underline decoration-dotted mb-0.5"
                  >
                    • {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Graph preview bar */}
        {graph && (
          <div className="mx-5 mb-3 shrink-0 rounded-xl border border-up/30 bg-up/5 px-4 py-3 flex items-center gap-3">
            <div className="flex-1">
              <div className="text-[12px] font-semibold text-ink">{graph.name || "Strategy"}</div>
              <div className="text-[11px] text-muted">{graph.nodes.length} nodes · {graph.edges.length} wires</div>
            </div>
            <button
              onClick={loadGraph}
              className="px-4 py-2 rounded-lg bg-money text-white text-[13px] font-medium hover:bg-moneyDark transition-colors shrink-0"
            >
              Load onto canvas →
            </button>
            <button
              onClick={() => { setGraph(null); setOpenQuestions([]); }}
              className="text-muted hover:text-ink text-sm px-1"
              title="Discard and keep refining"
            >
              ✕
            </button>
          </div>
        )}

        {/* Input */}
        <div className="px-5 pb-4 shrink-0 border-t border-border pt-3">
          {image && (
            <div className="mb-2 flex items-center gap-2">
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={image} alt="reference" className="h-14 w-auto rounded-lg border border-border object-cover" />
                <button
                  onClick={() => setImage(null)}
                  title="Remove image"
                  className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-ink text-white text-xs leading-none flex items-center justify-center shadow"
                >
                  ×
                </button>
              </div>
              <span className="text-[11px] text-muted">Chart attached — the AI will read it.</span>
            </div>
          )}
          <div className="flex gap-2 items-end">
            <label
              title="Attach a chart screenshot"
              className="shrink-0 h-[44px] w-[44px] flex items-center justify-center rounded-xl border border-border bg-paper hover:bg-surface2 cursor-pointer text-lg text-muted"
            >
              🖼
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                disabled={busy}
                onChange={(e) => { readImage(e.target.files?.[0]); e.currentTarget.value = ""; }}
              />
            </label>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              onPaste={(e) => {
                const item = Array.from(e.clipboardData.items).find((i) => i.type.startsWith("image/"));
                if (item) { const f = item.getAsFile(); if (f) readImage(f); }
              }}
              rows={2}
              placeholder="Type your answer… (Enter to send · paste or attach a chart 🖼)"
              disabled={busy}
              className="flex-1 rounded-xl bg-paper border border-border px-3 py-2.5 text-[13.5px] resize-none
                         focus:outline-none focus:ring-1 focus:ring-money disabled:opacity-50 leading-relaxed"
            />
            <button
              onClick={send}
              disabled={(!input.trim() && !image) || busy}
              className="px-4 py-2.5 rounded-xl bg-money text-white text-[13px] font-medium
                         hover:bg-moneyDark transition-colors disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
            >
              Send
            </button>
          </div>
          <p className="text-[10.5px] text-muted mt-1.5">
            Shift+Enter for new line · Enter to send · attach or paste a chart screenshot as reference
          </p>
        </div>
      </div>

      {/* ── Contextual Suggestions Sidebar ──────────────────────────────── */}
      <SuggestionsPanel
        messages={messages}
        onSuggest={(text) => { setInput(text); setTimeout(() => inputRef.current?.focus(), 30); }}
        label="Try asking"
      />
    </div>
  );
}
