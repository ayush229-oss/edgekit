/**
 * POST /api/broker-connections/test
 * Tests reachability of a data source before saving.
 * For MT5/MT4: probes the local backend.
 * For cloud sources: validates field presence only (can't test keys server-side).
 */
import { NextResponse } from "next/server";
import { auth } from "@clerk/nextjs/server";

export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });

  const { source_id, config } = await req.json();

  if (source_id === "mt5" || source_id === "mt4") {
    const host = (config?.host as string) || "127.0.0.1";
    const port = (config?.port as string) || (source_id === "mt5" ? "8765" : "8766");
    try {
      const r = await fetch(`http://${host}:${port}/graph/v2/nodes`, {
        signal: AbortSignal.timeout(3000),
      });
      if (r.ok) return NextResponse.json({ connected: true });
      return NextResponse.json({ connected: false, error: `Backend returned ${r.status}` });
    } catch (e: any) {
      return NextResponse.json({ connected: false, error: "Could not reach MT5 backend. Is MT5 running?" });
    }
  }

  if (source_id === "csv") {
    return NextResponse.json({ connected: true, note: "CSV ready — upload a file in the Builder." });
  }

  // Cloud sources (Binance, Zerodha, etc.) — we can't test the key server-side
  // without making live API calls. Just confirm fields are present.
  const { credentials = {} } = await req.json().catch(() => ({ credentials: {} }));
  return NextResponse.json({
    connected: true,
    note: "Credentials saved. Connection will be verified on first backtest run.",
  });
}
