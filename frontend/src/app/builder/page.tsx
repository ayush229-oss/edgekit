"use client";

/**
 * Edgekit visual strategy builder — v2.
 *
 * Layout (top → bottom):
 *   Top bar:    name · timeframe · bars · complexity · auto-run · guidance · templates · describe · Run
 *   Mid row:    [palette]  [canvas + floating selected-node toolbar]  [property panel + trade-mgmt]
 *   Bottom row: [metrics panel · equity chart] — full width, plenty of room
 *
 * Guidance system: an "amber 💡" hint sits next to every UI area. Toggle in the
 * top bar hides them all once the user is comfortable.
 *
 * NL describer: "Describe strategy" button opens a modal where users type
 * plain English; we match keywords to a template and explain each node.
 *
 * Selected node: visible floating toolbar above the canvas + Delete/Backspace
 * keyboard shortcut + Duplicate action. No more hidden delete.
 *
 * Backtest semantics: every change is a fresh full backtest (no caching). The
 * Run button glows sage when results are stale.
 */
import { useCallback, useEffect, useMemo, useRef, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import ReactFlow, {
  Background, Controls, MiniMap,
  applyNodeChanges, applyEdgeChanges, addEdge,
  ReactFlowProvider,
  type Node, type Edge, type NodeChange, type EdgeChange, type Connection,
} from "reactflow";
import "reactflow/dist/style.css";

import {
  v2ListNodes, v2ListTemplates, v2GetTemplate, v2RunBacktest, v2Complexity,
  v2ListSymbols, forwardStart,
  type V2NodeSpec, type V2Graph, type V2Complexity as V2C,
  type TemplateSummary, type BacktestResponse, type SymbolInfo,
} from "@/lib/api";
import { NodeCardV2 }            from "@/components/builder_v2/NodeCardV2";
import { PaletteV2 }             from "@/components/builder_v2/PaletteV2";
import { PropertyPanelV2 }       from "@/components/builder_v2/PropertyPanelV2";
import { ComplexityMeter }       from "@/components/builder_v2/ComplexityMeter";
import { SelectedNodeToolbar }   from "@/components/builder_v2/SelectedNodeToolbar";
import { GuidanceHint }          from "@/components/builder_v2/GuidanceHint";
import { StrategyLogicBox }      from "@/components/builder_v2/StrategyLogicBox";
import { NextStepsPanel }        from "@/components/builder_v2/NextStepsPanel";
import { MetricsPanel }          from "@/components/MetricsPanel";
import { TradeManagement, type TradeMgmt } from "@/components/TradeManagement";
import { PropFirmPanel }         from "@/components/PropFirmPanel";
import type { ChallengeParams }  from "@/lib/api";

// Lazy-load heavy/modal-only components so they don't block initial paint.
const EquityChart = dynamic(
  () => import("@/components/EquityChart").then((m) => ({ default: m.EquityChart })),
  { ssr: false }
);
const ChartPreview = dynamic(
  () => import("@/components/builder_v2/ChartPreview").then((m) => ({ default: m.ChartPreview })),
  { ssr: false }
);
const StrategyChat = dynamic(
  () => import("@/components/builder_v2/StrategyChat").then((m) => ({ default: m.StrategyChat })),
  { ssr: false }
);
const PineExportModal = dynamic(
  () => import("@/components/builder_v2/PineExportModal").then((m) => ({ default: m.PineExportModal })),
  { ssr: false }
);
const CustomNodeBuilder = dynamic(
  () => import("@/components/builder_v2/CustomNodeBuilder").then((m) => ({ default: m.CustomNodeBuilder })),
  { ssr: false }
);

import type { CustomNode } from "@/lib/customNodes";


const nodeTypes = { v2Node: NodeCardV2 };


// ── Graph ↔ React Flow conversion ──────────────────────────────────────────
function graphToRF(graph: V2Graph, library: V2NodeSpec[]): { nodes: Node[]; edges: Edge[] } {
  const specByType = Object.fromEntries(library.map((s) => [s.type, s]));
  return {
    nodes: graph.nodes.map((n, idx) => ({
      id:       n.id,
      type:     "v2Node",
      position: n.position ?? { x: 80 + idx * 240, y: 120 },
      data:     { spec: specByType[n.type], params: n.params, selected: false },
    })),
    edges: graph.edges.map((e, i) => ({
      id:           `e${i}`,
      source:       e.from,
      target:       e.to,
      sourceHandle: e.from_port,
      targetHandle: e.to_port,
      animated:     true,
      style:        { strokeWidth: 2 },
    })),
  };
}

function rfToGraph(nodes: Node[], edges: Edge[], name: string): V2Graph {
  return {
    name,
    nodes: nodes.map((n) => ({
      id:       n.id,
      type:     (n.data as any).spec.type,
      params:   (n.data as any).params,
      position: n.position,
    })),
    edges: edges.map((e) => ({
      from:      e.source!,
      to:        e.target!,
      from_port: e.sourceHandle ?? "",
      to_port:   e.targetHandle ?? "",
    })),
  };
}


// Local autosave of the work-in-progress canvas, so a refresh doesn't lose it.
// This is separate from "💾 Save", which stores to the account library.
const DRAFT_KEY = "edgekit.builderDraft.v1";

function BuilderInner() {
  const searchParams  = useSearchParams();
  const templateParam = searchParams.get("template");
  const savedParam    = searchParams.get("saved");   // load from Supabase: ?saved=<uuid>

  const [library,    setLibrary]    = useState<V2NodeSpec[]>([]);
  const [templates,  setTemplates]  = useState<TemplateSummary[]>([]);
  // Skip the auto-popping picker if user came in with a template/saved graph selected.
  const [showPicker, setShowPicker] = useState(!templateParam && !savedParam);
  const [autoLoaded, setAutoLoaded] = useState(false);
  const [descOpen,   setDescOpen]   = useState(false);
  const [pineOpen,   setPineOpen]   = useState(false);
  const [chartOpen,  setChartOpen]  = useState(false);
  const [customNodeOpen, setCustomNodeOpen] = useState(false);
  const [paletteMin, setPaletteMin] = useState(false);
  const [navOpen,    setNavOpen]    = useState(false);   // builder page-nav menu
  const [varsOpen,   setVarsOpen]   = useState(false);   // variables (nodes) dropdown
  const [stashedNodes, setStashedNodes] = useState<{ node: Node; edges: Edge[] }[]>([]);  // disabled variables
  const [fwdMsg,     setFwdMsg]     = useState<string | null>(null);   // forward-test feedback
  const [logicHidden, setLogicHidden] = useState(true);
  const [resultsMin, setResultsMin] = useState(true);

  // ── Save state ─────────────────────────────────────────────────────────
  const [saveResultOpen,   setSaveResultOpen]   = useState(false);
  const [saveResultName,   setSaveResultName]   = useState("");
  const [saveResultStatus, setSaveResultStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");

  const [saveStratOpen,   setSaveStratOpen]   = useState(false);
  const [saveStratName,   setSaveStratName]   = useState("");
  const [saveStratStatus, setSaveStratStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [savedStratId,    setSavedStratId]    = useState<string | null>(null); // uuid once saved

  const [name,  setName]  = useState("Untitled strategy");
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const bootstrappedRef = useRef(false);   // gates autosave until initial load/restore done

  const [tf,     setTf]     = useState("M15");
  const [symbol, setSymbol] = useState("XAUUSD");
  const [bars,   setBars]   = useState(5000);
  const [symbols,    setSymbols]    = useState<SymbolInfo[]>([]);
  const [symbolSource, setSymbolSource] = useState<"mt5" | "static">("static");
  const [busy, setBusy] = useState(false);
  const [err,  setErr]  = useState<string | null>(null);
  const [result,  setResult]  = useState<BacktestResponse | null>(null);
  const [complex, setComplex] = useState<V2C | null>(null);
  const [stale,   setStale]   = useState(false);
  const [guideOn, setGuideOn] = useState(true);   // inline phrases — visible by default

  const [mgmt, setMgmt] = useState<TradeMgmt>({
    target_r:         3.0,
    target_close_pct: 0.5,
    trail_mode:       "candle",
    trail_start:      "after_target",
    trail_params:     { buf_pips: 1 },
  });

  const [challengeEnabled, setChallengeEnabled] = useState(false);
  const [challengeParams, setChallengeParams] = useState<ChallengeParams>({
    account_size:         10000,
    daily_loss_limit_pct: 5,
    max_drawdown_pct:     10,
    profit_target_pct:    10,
    min_trading_days:     4,
  });

  // ── Bootstrap: library + templates + symbols ──────────────────────────
  useEffect(() => {
    v2ListNodes().then(setLibrary).catch((e) => setErr(String(e)));
    v2ListTemplates().then(setTemplates).catch(() => {});
    v2ListSymbols().then((r) => {
      setSymbols(r.symbols);
      setSymbolSource(r.source);
    }).catch(() => {});
  }, []);

  // ── URL-driven template auto-load + autosaved-draft restore ────────────
  useEffect(() => {
    if (autoLoaded || library.length === 0) return;
    bootstrappedRef.current = true;   // safe to start autosaving after this pass

    if (savedParam) {
      // Load a user-saved strategy from Supabase
      setAutoLoaded(true);
      fetch(`/api/saved-strategies/${savedParam}`)
        .then((r) => r.ok ? r.json() : Promise.reject(`${r.status}`))
        .then((data) => {
          const rf = graphToRF(data.graph as V2Graph, library);
          setName(data.name);
          setNodes(rf.nodes); setEdges(rf.edges); setSelectedId(null);
          setShowPicker(false);
          setSavedStratId(data.id);
          if (data.symbol)    setSymbol(data.symbol);
          if (data.timeframe) setTf(data.timeframe);
        })
        .catch((e) => setErr(`Could not load saved strategy: ${e}`));
      return;
    }

    if (templateParam) {
      setAutoLoaded(true);
      void loadTemplate(templateParam);
      return;
    }

    // No URL params — restore the autosaved draft from the last session, if any.
    try {
      const raw = window.localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const d = JSON.parse(raw);
        if (d?.graph?.nodes?.length) {
          setAutoLoaded(true);
          const rf = graphToRF(d.graph as V2Graph, library);
          setName(d.name || d.graph.name || "Untitled strategy");
          setNodes(rf.nodes); setEdges(rf.edges); setSelectedId(null);
          setShowPicker(false);
          if (d.symbol) setSymbol(d.symbol);
          if (d.tf)     setTf(d.tf);
        }
      }
    } catch { /* ignore corrupt draft */ }
  }, [savedParam, templateParam, library, autoLoaded]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Autosave the canvas to localStorage (debounced) ────────────────────
  useEffect(() => {
    if (!bootstrappedRef.current) return;   // don't autosave before initial load/restore
    const t = setTimeout(() => {
      try {
        if (nodes.length === 0) { window.localStorage.removeItem(DRAFT_KEY); return; }
        const draft = { name, symbol, tf, graph: rfToGraph(nodes, edges, name) };
        window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
      } catch { /* quota or serialization issue — ignore */ }
    }, 600);
    return () => clearTimeout(t);
  }, [nodes, edges, name, symbol, tf]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ── Recompute complexity whenever the graph changes ────────────────────
  useEffect(() => {
    if (nodes.length === 0) { setComplex(null); return; }
    const g = rfToGraph(nodes, edges, name);
    v2Complexity(g).then(setComplex).catch(() => setComplex(null));
  }, [nodes, edges]);     // eslint-disable-line react-hooks/exhaustive-deps

  // ── Mark stale on any change that affects results ──────────────────────
  useEffect(() => { setStale(true); }, [nodes, edges, tf, bars, symbol, mgmt]);   // eslint-disable-line react-hooks/exhaustive-deps

  // Port-type lookup for the connection validator
  const portTypeMap = useMemo(() => {
    const m: Record<string, Record<string, string>> = {};
    for (const n of nodes) {
      const spec = (n.data as any).spec as V2NodeSpec;
      const slot: Record<string, string> = {};
      for (const p of spec.inputs)  slot["in:"  + p.name] = p.type;
      for (const p of spec.outputs) slot["out:" + p.name] = p.type;
      m[n.id] = slot;
    }
    return m;
  }, [nodes]);

  function isValidConnection(c: Connection): boolean {
    if (!c.source || !c.target || !c.sourceHandle || !c.targetHandle) return false;
    if (c.source === c.target) return false;
    const srcType = portTypeMap[c.source]?.["out:" + c.sourceHandle];
    const tgtType = portTypeMap[c.target]?.["in:"  + c.targetHandle];
    return srcType !== undefined && srcType === tgtType;
  }


  // ── Templates ──────────────────────────────────────────────────────────
  async function loadTemplate(id: string) {
    if (id === "blank") {
      setName("Untitled strategy");
      setNodes([]); setEdges([]); setSelectedId(null); setShowPicker(false);
      return;
    }
    try {
      const g  = await v2GetTemplate(id);
      const rf = graphToRF(g, library);
      setName(g.name); setNodes(rf.nodes); setEdges(rf.edges);
      setSelectedId(null); setShowPicker(false);
      // Sync top-bar symbol + timeframe from the template's universe node
      const univ = g.nodes.find((n) => n.type === "universe.single_asset");
      if (univ) {
        if (univ.params?.ticker)    setSymbol(univ.params.ticker);
        if (univ.params?.timeframe) setTf(univ.params.timeframe);
      }
    } catch (e: any) { setErr(e.message ?? String(e)); }
  }

  function loadGraphFromDescriber(g: V2Graph, n: string) {
    const rf = graphToRF(g, library);
    setName(n); setNodes(rf.nodes); setEdges(rf.edges);
    setSelectedId(null);
  }


  // ── Canvas handlers ────────────────────────────────────────────────────
  const onNodesChange = useCallback((c: NodeChange[]) => setNodes((ns) => applyNodeChanges(c, ns)), []);
  const onEdgesChange = useCallback((c: EdgeChange[]) => setEdges((es) => applyEdgeChanges(c, es)), []);
  const onConnect     = useCallback((c: Connection) => {
    setEdges((es) => addEdge({ ...c, animated: true, style: { strokeWidth: 2 } }, es));
  }, []);

  function addNodeFromPalette(spec: V2NodeSpec) {
    const id = `${spec.type.split(".")[1] || spec.type}_${Math.random().toString(36).slice(2, 7)}`;
    const defaults = Object.fromEntries(spec.params.map((p) => [p.key, p.default]));
    setNodes((ns) => [
      ...ns,
      {
        id,
        type: "v2Node",
        position: { x: 220 + Math.random() * 280, y: 140 + Math.random() * 280 },
        data: { spec, params: defaults, selected: false },
      },
    ]);
    setSelectedId(id);
  }

  // ── Add a saved custom node — inlines its sub-graph onto the canvas ──
  // The internal node IDs are rewritten with a fresh suffix to avoid colliding
  // with existing canvas nodes; edges are rerouted to match. Positions are
  // shifted by a base offset so the new sub-graph doesn't stack on top of
  // whatever's already there.
  function addCustomNode(cn: CustomNode) {
    if (library.length === 0) {
      setErr("Node library is still loading — please try again in a moment.");
      return;
    }

    const suffix     = Math.random().toString(36).slice(2, 7);
    const remap: Record<string, string> = {};
    for (const n of cn.graph.nodes) {
      remap[n.id] = `${n.id}_${suffix}`;
    }

    const existingXs = nodes.map((n) => n.position.x);
    const baseX      = existingXs.length > 0 ? Math.max(...existingXs) + 320 : 200;
    const baseY      = 100;

    const subXs = cn.graph.nodes.map((n) => n.position?.x ?? 0);
    const subYs = cn.graph.nodes.map((n) => n.position?.y ?? 0);
    const minX  = subXs.length > 0 ? Math.min(...subXs) : 0;
    const minY  = subYs.length > 0 ? Math.min(...subYs) : 0;

    const specByType = Object.fromEntries(library.map((s) => [s.type, s]));

    const missing: string[] = [];
    const newNodes: Node[] = cn.graph.nodes.map((n) => {
      const spec = specByType[n.type];
      if (!spec) { missing.push(n.type); return null as any; }
      return {
        id:       remap[n.id],
        type:     "v2Node",
        position: {
          x: baseX + ((n.position?.x ?? 0) - minX),
          y: baseY + ((n.position?.y ?? 0) - minY),
        },
        data: { spec, params: { ...n.params }, selected: false },
      };
    }).filter(Boolean);

    if (missing.length > 0) {
      setErr(`Custom node uses unknown types: ${missing.join(", ")}. It may have been created with an older version.`);
      return;
    }

    const newEdges: Edge[] = cn.graph.edges.map((e, i) => ({
      id:           `e_${suffix}_${i}`,
      source:       remap[e.from] || e.from,
      target:       remap[e.to]   || e.to,
      sourceHandle: e.from_port,
      targetHandle: e.to_port,
      animated:     true,
      style:        { strokeWidth: 2 },
    }));

    setNodes((ns) => [...ns, ...newNodes]);
    setEdges((es) => [...es, ...newEdges]);
    if (newNodes.length > 0) setSelectedId(newNodes[0].id);
  }

  function updateNodeParam(k: string, v: any) {
    if (!selectedId) return;
    setNodes((ns) => ns.map((n) =>
      n.id === selectedId
        ? { ...n, data: { ...n.data, params: { ...(n.data as any).params, [k]: v } } }
        : n
    ));
  }

  function deleteSelected() {
    if (!selectedId) return;
    setNodes((ns) => ns.filter((n) => n.id !== selectedId));
    setEdges((es) => es.filter((e) => e.source !== selectedId && e.target !== selectedId));
    setSelectedId(null);
  }

  // ── Variables (nodes) enable/disable — toggle a variable off and on ──────
  // Disabling stashes the node + its wires so the strategy can be put back
  // exactly; the graph realigns (edges drop) and the backtest reflects it.
  function disableVar(id: string) {
    const node = nodes.find((n) => n.id === id);
    if (!node) return;
    const nodeEdges = edges.filter((e) => e.source === id || e.target === id);
    setStashedNodes((prev) => [...prev, { node, edges: nodeEdges }]);
    setNodes((ns) => ns.filter((n) => n.id !== id));
    setEdges((es) => es.filter((e) => e.source !== id && e.target !== id));
    if (selectedId === id) setSelectedId(null);
  }

  function enableVar(id: string) {
    const stash = stashedNodes.find((d) => d.node.id === id);
    if (!stash) return;
    setStashedNodes((prev) => prev.filter((d) => d.node.id !== id));
    setNodes((ns) => [...ns, stash.node]);
    // Only restore wires whose other endpoint still exists on the canvas.
    setEdges((es) => {
      const present = new Set([...nodes.map((n) => n.id), id]);
      const restore = stash.edges.filter((e) => present.has(e.source) && present.has(e.target));
      const have = new Set(es.map((e) => e.id));
      return [...es, ...restore.filter((e) => !have.has(e.id))];
    });
  }

  function duplicateSelected() {
    if (!selectedId) return;
    const orig = nodes.find((n) => n.id === selectedId);
    if (!orig) return;
    const spec = (orig.data as any).spec as V2NodeSpec;
    const id   = `${spec.type.split(".")[1] || spec.type}_${Math.random().toString(36).slice(2, 7)}`;
    setNodes((ns) => [
      ...ns,
      {
        ...orig,
        id,
        position: { x: orig.position.x + 40, y: orig.position.y + 40 },
        data: { ...orig.data, params: { ...(orig.data as any).params }, selected: false },
      },
    ]);
    setSelectedId(id);
  }

  // ── Undo / redo memory ─────────────────────────────────────────────────
  // Snapshots of the canvas are recorded shortly after the graph settles, so a
  // drag or a multi-step edit collapses into a single undo step. Refs hold the
  // stacks (no re-render on push); histVer bumps only to refresh button state.
  const historyRef  = useRef<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const futureRef   = useRef<{ nodes: Node[]; edges: Edge[] }[]>([]);
  const lastSnapRef = useRef<{ nodes: Node[]; edges: Edge[] }>({ nodes: [], edges: [] });
  const applyingRef = useRef(false);   // true while undo/redo is applying (skip recording)
  const initedRef   = useRef(false);
  const [, setHistVer] = useState(0);   // bump only to refresh undo/redo button state

  useEffect(() => {
    if (!initedRef.current) {
      initedRef.current = true;
      lastSnapRef.current = { nodes, edges };
      return;
    }
    if (applyingRef.current) {
      applyingRef.current = false;
      lastSnapRef.current = { nodes, edges };
      return;
    }
    const t = setTimeout(() => {
      historyRef.current.push(lastSnapRef.current);
      if (historyRef.current.length > 60) historyRef.current.shift();
      futureRef.current = [];
      lastSnapRef.current = { nodes, edges };
      setHistVer((v) => v + 1);
    }, 350);
    return () => clearTimeout(t);
  }, [nodes, edges]);   // eslint-disable-line react-hooks/exhaustive-deps

  function undo() {
    if (historyRef.current.length === 0) return;
    const prev = historyRef.current.pop()!;
    futureRef.current.push(lastSnapRef.current);
    applyingRef.current = true;
    lastSnapRef.current = prev;
    setNodes(prev.nodes); setEdges(prev.edges); setSelectedId(null);
    setHistVer((v) => v + 1);
  }

  function redo() {
    if (futureRef.current.length === 0) return;
    const nxt = futureRef.current.pop()!;
    historyRef.current.push(lastSnapRef.current);
    applyingRef.current = true;
    lastSnapRef.current = nxt;
    setNodes(nxt.nodes); setEdges(nxt.edges); setSelectedId(null);
    setHistVer((v) => v + 1);
  }

  // Keyboard: Delete / Backspace to remove selected node — ignored while typing in inputs.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
        e.preventDefault(); deleteSelected();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "d" && selectedId) {
        e.preventDefault(); duplicateSelected();
      }
      const k = e.key.toLowerCase();
      if ((e.ctrlKey || e.metaKey) && k === "z" && !e.shiftKey) {
        e.preventDefault(); undo();
      } else if ((e.ctrlKey || e.metaKey) && (k === "y" || (k === "z" && e.shiftKey))) {
        e.preventDefault(); redo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, nodes]);    // eslint-disable-line react-hooks/exhaustive-deps

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedId), [nodes, selectedId]);
  const selectedSpec = (selectedNode?.data as any)?.spec as V2NodeSpec | null ?? null;


  // ── Save result ────────────────────────────────────────────────────────
  async function saveResult() {
    if (!result) return;
    setSaveResultStatus("saving");
    try {
      const res = await fetch("/api/saved-results", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name:          saveResultName.trim() || name,
          strategy_name: name,
          symbol,
          timeframe:     tf,
          bars,
          metrics:       result.metrics,
          equity_curve:  result.equity_curve,
          graph:         rfToGraph(nodes, edges, name),
        }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      setSaveResultStatus("saved");
      setTimeout(() => { setSaveResultOpen(false); setSaveResultStatus("idle"); setSaveResultName(""); }, 1500);
    } catch {
      setSaveResultStatus("error");
    }
  }

  // ── Save strategy ──────────────────────────────────────────────────────
  async function saveStrategy() {
    if (nodes.length === 0) return;
    setSaveStratStatus("saving");
    try {
      const stratName = saveStratName.trim() || name;
      const url    = savedStratId ? `/api/saved-strategies/${savedStratId}` : "/api/saved-strategies";
      const method = savedStratId ? "PUT" : "POST";
      const res    = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: stratName, graph: rfToGraph(nodes, edges, stratName), symbol, timeframe: tf }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      setSavedStratId(data.id);
      setName(stratName);
      setSaveStratStatus("saved");
      setTimeout(() => { setSaveStratOpen(false); setSaveStratStatus("idle"); setSaveStratName(""); }, 1500);
    } catch {
      setSaveStratStatus("error");
    }
  }

  // ── Start a forward (paper) test from the current strategy ───────────────
  async function startForwardTest(mode: "sim" | "live_demo" = "sim") {
    if (nodes.length === 0) return;
    setFwdMsg(mode === "live_demo" ? "Starting live demo test…" : "Starting…");
    try {
      await forwardStart({
        graph: rfToGraph(nodes, edges, name),
        name, symbol, timeframe: tf, mode,
        mgmt: {
          target_r:         mgmt.target_r,
          target_close_pct: mgmt.target_close_pct,
          trail_mode:       mgmt.trail_mode,
          trail_start:      mgmt.trail_start,
          trail_params:     mgmt.trail_params,
        },
        baseline: result ? result.metrics : {},
      });
      setFwdMsg("Forward test started ✓ — track it on the Forward Tests page");
      setTimeout(() => setFwdMsg(null), 5000);
    } catch (e: any) {
      setFwdMsg("Couldn't start: " + (e?.message ?? String(e)).slice(0, 80));
      setTimeout(() => setFwdMsg(null), 6000);
    }
  }

  // ── Run backtest ───────────────────────────────────────────────────────
  async function run() {
    setBusy(true); setErr(null);
    try {
      const graph = rfToGraph(nodes, edges, name);
      const res = await v2RunBacktest({
        graph,
        data_source:      "mt5",
        symbol:           symbol,
        timeframe:        tf,
        n_bars:           bars,
        target_r:         mgmt.target_r,
        target_close_pct: mgmt.target_close_pct,
        trail_mode:       mgmt.trail_mode,
        trail_start:      mgmt.trail_start,
        trail_params:     mgmt.trail_params,
        challenge:        challengeEnabled ? challengeParams : undefined,
      });
      setResult(res);
      setStale(false);
      // Auto-expand results panel the first time we have something to show
      if (!result) setResultsMin(false);
      // Fire-and-forget: record this backtest run for stats
      fetch("/api/backtests", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          graph_snapshot: graph,
          symbol,
          timeframe: tf,
          n_bars:    bars,
          metrics:   res.metrics,
          duration_ms: (res as any).duration_ms ?? null,
        }),
      }).catch(() => {});
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }


  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="fixed left-0 right-0 bottom-0 top-0 flex flex-col bg-cream">

      {/* ── Save result modal ─────────────────────────────────────── */}
      {saveResultOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-cream2 border border-border rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <h3 className="font-semibold text-[15px] mb-1">Save this result</h3>
            <p className="text-xs text-muted mb-4">Give it a name so you can find it in Analytics.</p>
            <input
              autoFocus
              value={saveResultName}
              onChange={(e) => setSaveResultName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void saveResult(); if (e.key === "Escape") { setSaveResultOpen(false); setSaveResultStatus("idle"); } }}
              placeholder={name}
              className="w-full rounded-lg border border-border bg-cream px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-sage mb-4"
            />
            <div className="flex gap-2">
              <button onClick={() => { setSaveResultOpen(false); setSaveResultStatus("idle"); }}
                className="flex-1 py-2 rounded-lg border border-border text-sm hover:bg-cream transition-colors">
                Cancel
              </button>
              <button onClick={() => void saveResult()} disabled={saveResultStatus === "saving"}
                className="flex-1 py-2 rounded-lg bg-sage text-cream2 text-sm font-medium hover:bg-sageMid transition-colors disabled:opacity-60">
                {saveResultStatus === "saving" ? "Saving…" : saveResultStatus === "saved" ? "✓ Saved!" : saveResultStatus === "error" ? "Error — retry" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Save strategy modal ────────────────────────────────────── */}
      {saveStratOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4">
          <div className="bg-cream2 border border-border rounded-2xl p-6 w-full max-w-sm shadow-xl">
            <h3 className="font-semibold text-[15px] mb-1">{savedStratId ? "Update strategy" : "Save strategy"}</h3>
            <p className="text-xs text-muted mb-4">Saved strategies appear in Strategies → My strategies.</p>
            <input
              autoFocus
              value={saveStratName}
              onChange={(e) => setSaveStratName(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") void saveStrategy(); if (e.key === "Escape") { setSaveStratOpen(false); setSaveStratStatus("idle"); } }}
              placeholder={name}
              className="w-full rounded-lg border border-border bg-cream px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-sage mb-4"
            />
            <div className="flex gap-2">
              <button onClick={() => { setSaveStratOpen(false); setSaveStratStatus("idle"); }}
                className="flex-1 py-2 rounded-lg border border-border text-sm hover:bg-cream transition-colors">
                Cancel
              </button>
              <button onClick={() => void saveStrategy()} disabled={saveStratStatus === "saving"}
                className="flex-1 py-2 rounded-lg bg-sage text-cream2 text-sm font-medium hover:bg-sageMid transition-colors disabled:opacity-60">
                {saveStratStatus === "saving" ? "Saving…" : saveStratStatus === "saved" ? "✓ Saved!" : saveStratStatus === "error" ? "Error — retry" : savedStratId ? "Update" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Template picker modal ──────────────────────────────────── */}
      {showPicker && (
        <div className="fixed inset-0 z-50 bg-cream/95 backdrop-blur-sm flex items-center justify-center p-8">
          <div className="bg-cream2 border border-border rounded-2xl p-8 max-w-3xl w-full shadow-xl">
            <h2 className="text-2xl font-semibold mb-1">Start your strategy</h2>
            <p className="text-sm text-muted mb-2">Pick a starter, or build from scratch.</p>
            <GuidanceHint show={guideOn} tone="tip">
              New here? Try <strong>Describe your strategy</strong> in the toolbar instead — write your idea in
              plain English and we'll build the graph for you.
            </GuidanceHint>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
              <button onClick={() => loadTemplate("blank")}
                className="text-left rounded-xl border border-border bg-cream p-4 hover:border-sage hover:shadow-sm transition-all">
                <div className="font-medium text-sm">Blank canvas</div>
                <div className="text-xs text-muted mt-1 leading-snug">Empty canvas — drop nodes from the palette.</div>
              </button>
              {templates.map((t) => (
                <button key={t.id} onClick={() => loadTemplate(t.id)}
                  className="text-left rounded-xl border border-border bg-cream p-4 hover:border-sage hover:shadow-sm transition-all">
                  <div className="font-medium text-sm">{t.name}</div>
                  <div className="text-xs text-muted mt-1 leading-snug">{t.description}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── AI strategy chat modal ─────────────────────────────────── */}
      <StrategyChat
        open={descOpen}
        onClose={() => setDescOpen(false)}
        onLoadGraph={loadGraphFromDescriber}
        symbol={symbol}
        timeframe={tf}
        currentGraph={nodes.length > 0 ? rfToGraph(nodes, edges, name) : null}
        resultSummary={result
          ? `${result.metrics.trades} trades, ${result.metrics.wr.toFixed(0)}% win rate, ${result.metrics.total_r >= 0 ? "+" : ""}${result.metrics.total_r.toFixed(1)}R`
          : null}
      />

      {/* ── AI custom-node builder modal ───────────────────────────── */}
      <CustomNodeBuilder
        open={customNodeOpen}
        onClose={() => setCustomNodeOpen(false)}
        symbol={symbol}
        timeframe={tf}
      />

      {/* ── Pine Script export modal ───────────────────────────────── */}
      <PineExportModal
        open={pineOpen}
        onClose={() => setPineOpen(false)}
        graph={nodes.length > 0 ? rfToGraph(nodes, edges, name) : null}
        mgmt={mgmt}
        strategyName={name}
      />

      {/* ── Chart preview modal ────────────────────────────────────── */}
      <ChartPreview
        open={chartOpen}
        onClose={() => setChartOpen(false)}
        graph={nodes.length > 0 ? rfToGraph(nodes, edges, name) : null}
        mgmt={mgmt}
        symbol={symbol}
        timeframe={tf}
        defaultBars={bars}
      />

      {/* ── Top bar ────────────────────────────────────────────────── */}
      <div className="bg-cream2 border-b border-border px-4 py-2.5 flex items-center gap-3 shrink-0">
        {/* Page navigation (builder is outside the (app) sidebar layout) */}
        <div className="relative shrink-0">
          <button
            onClick={() => setNavOpen((v) => !v)}
            onBlur={() => setTimeout(() => setNavOpen(false), 150)}
            title="Menu"
            className="flex items-center gap-1.5 pl-1 pr-2 py-1 rounded-lg hover:bg-cream transition-colors">
            <span className="w-6 h-6 rounded-md bg-ink text-cream2 flex items-center justify-center font-bold text-[12px]">E</span>
            <span className="text-muted text-xs">▾</span>
          </button>
          {navOpen && (
            <div className="absolute left-0 top-full mt-1 z-50 w-44 bg-cream2 border border-border rounded-lg shadow-lg py-1">
              {[
                { href: "/home",       label: "🏠 Home" },
                { href: "/strategies", label: "📊 Strategies" },
                { href: "/builder",    label: "🧩 Builder" },
                { href: "/forward",    label: "🧪 Forward Tests" },
                { href: "/resources",  label: "🔧 Resources" },
                { href: "/analytics",  label: "📈 Analytics" },
              ].map((it) => (
                <Link key={it.href} href={it.href}
                  className="block px-3 py-1.5 text-xs text-ink hover:bg-cream transition-colors">
                  {it.label}
                </Link>
              ))}
            </div>
          )}
        </div>
        <div className="w-px h-5 bg-border shrink-0" />

        <input value={name} onChange={(e) => setName(e.target.value)}
          className="bg-transparent text-sm font-medium px-2 py-1 rounded hover:bg-cream focus:bg-cream focus:outline-none focus:ring-1 focus:ring-sage flex-1 max-w-sm" />

        {/* Symbol — datalist gives autocomplete from the broker / common list,
            but free-text override is always allowed for broker-specific suffixes
            like ".cash", ".m", etc. */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] uppercase tracking-widest text-muted">Symbol</span>
          <input
            list="symbol-list"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase().trim())}
            placeholder="XAUUSD"
            title={symbolSource === "mt5"
              ? `${symbols.length} symbols available from your MT5 broker`
              : `Showing ${symbols.length} common symbols. Connect MT5 to see broker-specific list. Free-text any symbol.`}
            className="text-xs rounded bg-cream border border-border px-2 py-1 w-24 font-mono uppercase
                       focus:outline-none focus:ring-1 focus:ring-sage" />
          <datalist id="symbol-list">
            {symbols.map((s) => (
              <option key={s.symbol} value={s.symbol}>{s.description}{s.category ? ` — ${s.category}` : ""}</option>
            ))}
          </datalist>
        </div>

        <select value={tf} onChange={(e) => setTf(e.target.value)}
          className="text-xs rounded bg-cream border border-border px-2 py-1">
          {["M1","M5","M15","M30","H1","H4","D1"].map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <input type="number" value={bars} min={500} max={20000} step={500}
          onChange={(e) => setBars(parseInt(e.target.value || "5000"))}
          className="text-xs rounded bg-cream border border-border px-2 py-1 w-20" />
        <ComplexityMeter c={complex} />

        {/* Undo / redo */}
        <div className="flex items-center gap-1">
          <button onClick={undo} disabled={historyRef.current.length === 0}
            title="Undo (Ctrl+Z)"
            className="text-xs px-2.5 py-1.5 rounded border border-border hover:bg-cream transition-colors disabled:opacity-40">
            ↶ Undo
          </button>
          <button onClick={redo} disabled={futureRef.current.length === 0}
            title="Redo (Ctrl+Shift+Z)"
            className="text-xs px-2.5 py-1.5 rounded border border-border hover:bg-cream transition-colors disabled:opacity-40">
            ↷ Redo
          </button>
        </div>

        {/* Save strategy button */}
        <button
          onClick={() => { setSaveStratName(name); setSaveStratOpen(true); }}
          disabled={nodes.length === 0}
          title={nodes.length === 0 ? "Add nodes first" : savedStratId ? "Update saved strategy" : "Save strategy to your library"}
          className="text-xs px-3 py-1.5 rounded border border-border hover:bg-cream transition-colors disabled:opacity-40 flex items-center gap-1.5">
          {savedStratId ? "💾 Update" : "💾 Save"}
        </button>

        <button onClick={() => setDescOpen(true)}
          className="text-xs px-3 py-1.5 rounded bg-amber/30 border border-amber/40 text-amber-900 hover:bg-amber/40 transition-colors font-medium">
          ✨ Describe strategy
        </button>
        <button onClick={() => setChartOpen(true)}
          disabled={nodes.length === 0}
          title={nodes.length === 0
            ? "Build a strategy first, then preview it on the chart."
            : "Preview the strategy on real bars with entry/exit markers."}
          className="text-xs px-3 py-1.5 rounded bg-sky-100 border border-sky-200 text-sky-900 hover:bg-sky-200 transition-colors font-medium disabled:opacity-50">
          📈 Preview chart
        </button>
        {/* Variables dropdown — toggle any node on/off; graph realigns */}
        <div className="relative shrink-0">
          <button onClick={() => setVarsOpen((v) => !v)}
            disabled={nodes.length === 0 && stashedNodes.length === 0}
            title="Turn the strategy's variables on or off"
            className="text-xs px-3 py-1.5 rounded border border-border hover:bg-cream transition-colors disabled:opacity-40 flex items-center gap-1">
            Variables{stashedNodes.length > 0 ? ` (${stashedNodes.length} off)` : ""} ▾
          </button>
          {varsOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setVarsOpen(false)} />
              <div className="absolute right-0 top-full mt-1 z-50 w-72 bg-cream2 border border-border rounded-lg shadow-lg py-1 max-h-96 overflow-y-auto">
                <div className="px-3 py-1 text-[10px] uppercase tracking-wide text-muted">Variables in this strategy</div>
                {nodes.map((n) => {
                  const spec = (n.data as any).spec as V2NodeSpec;
                  return (
                    <label key={n.id} className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cream cursor-pointer">
                      <input type="checkbox" checked onChange={() => disableVar(n.id)} className="accent-sage" />
                      <span className="flex-1 truncate">{spec?.label ?? n.id}</span>
                      <span className="text-[10px] text-muted">{spec?.lane}</span>
                    </label>
                  );
                })}
                {stashedNodes.map((d) => {
                  const spec = (d.node.data as any).spec as V2NodeSpec;
                  return (
                    <label key={d.node.id} className="flex items-center gap-2 px-3 py-1.5 text-xs hover:bg-cream cursor-pointer opacity-70">
                      <input type="checkbox" checked={false} onChange={() => enableVar(d.node.id)} className="accent-sage" />
                      <span className="flex-1 truncate line-through">{spec?.label ?? d.node.id}</span>
                      <span className="text-[10px] text-muted">off</span>
                    </label>
                  );
                })}
                {nodes.length === 0 && stashedNodes.length === 0 && (
                  <div className="px-3 py-2 text-[11px] text-muted italic">No variables yet.</div>
                )}
                <div className="px-3 py-1.5 mt-1 text-[10px] text-muted border-t border-border">
                  Add new variables from the palette on the left.
                </div>
              </div>
            </>
          )}
        </div>

        <button onClick={() => setShowPicker(true)}
          className="text-xs px-3 py-1.5 rounded border border-border hover:bg-cream transition-colors">
          Templates
        </button>
        <button onClick={() => { setStale(true); void run(); }}
          disabled={busy || nodes.length === 0}
          className={`text-sm px-4 py-1.5 rounded-md font-medium transition-colors disabled:opacity-50
            ${stale && !busy ? "bg-sage text-cream2 hover:bg-sageMid"
                            : "bg-cream2 text-muted border border-border hover:bg-cream"}`}>
          {busy ? "Running…" : stale ? "Run backtest" : "Up to date ✓"}
        </button>
      </div>

      {/* ── Middle row: palette + canvas + right rail ───────────────── */}
      <div className="flex-1 flex min-h-0">
        <PaletteV2
          library={library}
          onAdd={addNodeFromPalette}
          onAddCustomNode={addCustomNode}
          onOpenCustomNodeBuilder={() => setCustomNodeOpen(true)}
          minimized={paletteMin}
          onToggleMinimized={() => setPaletteMin((v) => !v)}
        />

        {/* Canvas */}
        <div className="flex-1 relative min-w-0">
          {/* Floating emoji buttons — top-left corner of canvas */}
          <div className="absolute top-3 left-3 z-20 flex flex-col gap-2">
            <button onClick={() => setPineOpen(true)}
              disabled={nodes.length === 0}
              title={nodes.length === 0
                ? "Build a strategy first, then export it for TradingView."
                : "Deploy to TradingView — copy generated Pine Script v6 to take this live. For iteration, use 📈 Preview chart instead."}
              className="w-9 h-9 rounded-full bg-cream2 border border-border shadow-sm hover:bg-cream hover:border-sage flex items-center justify-center text-lg disabled:opacity-40">
              📊
            </button>
            <button onClick={() => setGuideOn((v) => !v)}
              title={guideOn ? "Hide inline guidance hints" : "Show inline guidance hints"}
              className={`w-9 h-9 rounded-full border shadow-sm flex items-center justify-center text-lg transition-colors
                ${guideOn ? "bg-amber/30 border-amber/50" : "bg-cream2 border-border hover:bg-cream"}`}>
              💡
            </button>
          </div>

          {guideOn && (
            <div className="absolute top-3 left-16 z-10 max-w-sm">
              <GuidanceHint show={guideOn} tone="info">
                <strong>Click a node</strong> to select it (its actions appear above).
                <strong> Drag from a colored dot</strong> to wire it to another node — only matching colors connect.
                <strong> Press Delete</strong> or use the toolbar to remove a node.
              </GuidanceHint>
            </div>
          )}

          <SelectedNodeToolbar
            spec={selectedSpec}
            onDelete={deleteSelected}
            onDuplicate={duplicateSelected}
            onDeselect={() => setSelectedId(null)}
          />

          <ReactFlow
            nodes={nodes.map((n) => ({ ...n, data: { ...n.data, selected: n.id === selectedId }}))}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            isValidConnection={isValidConnection}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView fitViewOptions={{ padding: 0.15 }}
            className="!bg-cream" proOptions={{ hideAttribution: true }}
            defaultEdgeOptions={{ animated: true, style: { strokeWidth: 2 } }}
          >
            <Background gap={20} size={1} color="#d4ccba" />
            <Controls className="!bg-cream2 !border !border-border" />
            <MiniMap className="!bg-cream2 !border !border-border" nodeColor="#6B9B7A" />
          </ReactFlow>

          {nodes.length === 0 && !showPicker && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center text-muted max-w-md">
                <p className="text-base font-medium">Empty canvas</p>
                <p className="text-sm mt-2">Click a node in the palette on the left to add it.</p>
                <p className="text-xs mt-3 italic">
                  A working strategy needs at minimum: <span className="font-semibold">1 Alpha → 1 Sizing → 1 Risk → 1 Execution</span>.
                </p>
                <p className="text-xs mt-3 italic">
                  Or click <strong className="text-amber-900">✨ Describe strategy</strong> above to generate one from a sentence.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Right rail — narrower now that results moved below */}
        <div className="w-80 shrink-0 bg-cream2 border-l border-border h-full overflow-y-auto">
          {guideOn && (
            <div className="p-3 border-b border-border">
              <GuidanceHint show={guideOn} tone="tip">
                {selectedSpec
                  ? "Adjust this node's parameters here. Every change marks the strategy as needing a fresh backtest."
                  : "Click any node on the canvas to edit it here. Below this panel, set how trades are managed (target R, trailing)."}
              </GuidanceHint>
            </div>
          )}
          <PropertyPanelV2
            spec={selectedSpec}
            params={(selectedNode?.data as any)?.params ?? {}}
            onChange={updateNodeParam}
            onDelete={deleteSelected}
          />
          <div className="border-t border-border p-3">
            <TradeManagement mgmt={mgmt} onChange={setMgmt} />
          </div>
          <PropFirmPanel
            enabled={challengeEnabled}
            params={challengeParams}
            result={result?.challenge ?? undefined}
            onToggle={() => { setChallengeEnabled((v) => !v); setStale(true); }}
            onChange={(p) => { setChallengeParams(p); setStale(true); }}
          />
          {err && <div className="px-5 pb-3 text-xs text-terra">{err}</div>}
        </div>
      </div>

      {/* ── Bottom row: strategy logic + results ───────────────────── */}
      {resultsMin ? (
        // Minimized: thin strip with summary + expand button
        <div className="border-t border-border bg-cream2 shrink-0 px-4 py-1.5 flex items-center gap-3">
          <button onClick={() => setResultsMin(false)}
            title="Expand results panel"
            className="text-xs px-2 py-0.5 rounded hover:bg-cream text-muted hover:text-ink flex items-center gap-1">
            ▴ Show results panel
          </button>
          <span className="text-muted text-xs">·</span>
          {result ? (
            <div className="flex items-center gap-3 text-xs">
              <span className="font-mono"><strong className="text-ink">{result.metrics.trades}</strong> <span className="text-muted">trades</span></span>
              <span className="font-mono"><strong className="text-ink">{result.metrics.wr.toFixed(1)}%</strong> <span className="text-muted">WR</span></span>
              <span className={`font-mono font-semibold ${result.metrics.total_r >= 0 ? "text-sage" : "text-terra"}`}>
                {result.metrics.total_r >= 0 ? "+" : ""}{result.metrics.total_r.toFixed(1)}R
              </span>
              <span className="font-mono text-muted">
                PF {(result.metrics.profit_factor === 99.0 ? "∞" : result.metrics.profit_factor.toFixed(2))}
              </span>
              <span className="font-mono text-muted">
                DD {result.metrics.max_dd.toFixed(1)}R
              </span>
              {result.data_source?.label && (
                <span
                  title="Data source used for this backtest"
                  className={`text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${
                    result.data_source.provider === "mt5"
                      ? "bg-sage/15 border-sage/40 text-sage"
                      : "bg-amber/25 border-amber/50 text-amber-900"
                  }`}>
                  {result.data_source.provider === "mt5" ? "● " : "⚠ "}{result.data_source.label}
                </span>
              )}
            </div>
          ) : (
            <span className="text-xs italic text-muted">No results yet — click Run backtest</span>
          )}
          {fwdMsg && <span className="text-[11px] text-sage ml-auto shrink-0">{fwdMsg}</span>}
          {nodes.length > 0 && (
            <>
              <button
                onClick={() => startForwardTest("sim")}
                title="Paper forward test — recomputes on fresh bars (no real execution)"
                className={`${fwdMsg ? "" : "ml-auto"} text-xs px-2.5 py-0.5 rounded bg-sky-100 text-sky-900 hover:bg-sky-200 transition-colors font-medium shrink-0`}>
                🧪 Paper
              </button>
              <button
                onClick={() => startForwardTest("live_demo")}
                title="Live demo forward test — places real orders on your MT5 demo account to measure true spread, slippage & commission"
                className="text-xs px-2.5 py-0.5 rounded bg-emerald-100 text-emerald-900 hover:bg-emerald-200 transition-colors font-medium shrink-0">
                🔴 Live (demo)
              </button>
            </>
          )}
          {result && (
            <button
              onClick={() => { setSaveResultName(name); setSaveResultOpen(true); }}
              className="text-xs px-2.5 py-0.5 rounded bg-money/15 text-money hover:bg-money/25 transition-colors font-medium shrink-0">
              Save result
            </button>
          )}
        </div>
      ) : (
        // Expanded: full panel
        <div className="border-t border-border bg-cream2 shrink-0 max-h-[42%] overflow-y-auto relative">
          {/* Collapse button — top-right corner */}
          <button onClick={() => setResultsMin(true)}
            title="Minimize results panel"
            className="absolute top-3 right-3 z-10 text-xs px-2 py-1 rounded bg-cream hover:bg-cream3 border border-border text-muted hover:text-ink flex items-center gap-1">
            ▾ Hide
          </button>

          {/* Strategy logic box — describes what the graph does in English */}
          <div className="p-3 pr-20">
            <StrategyLogicBox
              nodes={nodes.map((n) => ({
                id:       n.id,
                type:     (n.data as any).spec.type,
                params:   (n.data as any).params,
                position: n.position,
              }))}
              edges={edges.map((e) => ({
                from:      e.source!,
                to:        e.target!,
                from_port: e.sourceHandle ?? "",
                to_port:   e.targetHandle ?? "",
              }))}
              library={library}
              collapsed={logicHidden}
              onToggle={() => setLogicHidden((v) => !v)}
            />
          </div>
          {guideOn && !result && (
            <div className="p-3 max-w-3xl mx-auto">
              <GuidanceHint show={guideOn} tone="info">
                Once you click <strong>Run backtest</strong>, your strategy's metrics and equity curve will appear here.
                <span className="italic"> Every change re-runs the entire backtest from scratch — no caching.</span>
              </GuidanceHint>
            </div>
          )}
          {result && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4 p-4">
                <div>
                  <MetricsPanel m={result.metrics} bars={result.bars} pip={result.pip} />
                </div>
                <div>
                  <EquityChart curve={result.equity_curve} />
                </div>
              </div>
              <div className="p-4 pt-0 flex items-start gap-3">
                <div className="flex-1">
                  <NextStepsPanel
                    result={result}
                    nodes={nodes.map((n) => ({
                      id:       n.id,
                      type:     (n.data as any).spec.type,
                      params:   (n.data as any).params,
                      position: n.position,
                    }))}
                  />
                </div>
                <button
                  onClick={() => { setSaveResultName(name); setSaveResultOpen(true); }}
                  className="shrink-0 text-xs px-3 py-1.5 rounded-md bg-money text-white hover:bg-moneyDark transition-colors font-medium">
                  💾 Save result
                </button>
              </div>
            </>
          )}
          {!result && !guideOn && (
            <div className="p-6 text-center text-muted text-sm italic">
              No results yet — click <strong>Run backtest</strong>.
            </div>
          )}
        </div>
      )}
    </div>
  );
}


export default function BuilderPage() {
  return (
    <Suspense fallback={<div className="p-8 text-muted text-sm">Loading builder…</div>}>
      <ReactFlowProvider>
        <BuilderInner />
      </ReactFlowProvider>
    </Suspense>
  );
}
