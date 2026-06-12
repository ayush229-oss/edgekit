import { NextRequest, NextResponse } from "next/server";

// Vercel env values can carry a BOM/zero-width prefix — strip non-printables
// or `new URL()` inside fetch() rejects the URL (502 on every proxied call).
const BACKEND_URL = (
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.VERCEL ? "http://165.232.178.128:8765" : "http://127.0.0.1:8765")
).replace(/[^\x20-\x7E]/g, "").trim();

// Only forward headers that the VPS backend actually needs.
// NB: accept-encoding is deliberately NOT forwarded. If the backend gzips the
// response, fetch() auto-decompresses it when we call .text(), but the upstream
// content-encoding/content-length headers then describe the compressed bytes —
// passing them through corrupts the response (empty body downstream). Letting
// the backend reply uncompressed sidesteps the whole mismatch.
const FORWARD_HEADERS = ["content-type", "authorization", "accept", "accept-language"];

// Response headers that no longer describe the decoded body we forward.
const STRIP_RESPONSE_HEADERS = new Set([
  "transfer-encoding", "content-encoding", "content-length",
]);

// Backend paths the public proxy must never expose. The proxy injects the
// shared x-api-key, so without this gate any anonymous visitor could reach
// the VPS deploy webhooks (git pull + service restart) through /api/internal/*.
const BLOCKED_PREFIXES = ["/internal/"];

async function proxy(req: NextRequest, { params }: { params: { path: string[] } }) {
  try {
    const path = "/" + params.path.join("/");
    if (BLOCKED_PREFIXES.some((p) => path.startsWith(p))) {
      return NextResponse.json({ error: "not found" }, { status: 404 });
    }
    const url = `${BACKEND_URL}${path}${req.nextUrl.search}`;

    const reqHeaders: Record<string, string> = {};
    for (const key of FORWARD_HEADERS) {
      const val = req.headers.get(key);
      if (val) reqHeaders[key] = val;
    }
    const apiKey = process.env.EDGEKIT_API_KEY?.replace(/[^\x20-\x7E]/g, "");
    if (apiKey) reqHeaders["x-api-key"] = apiKey;

    const hasBody = !["GET", "HEAD"].includes(req.method);
    const upstream = await fetch(url, {
      method: req.method,
      headers: reqHeaders,
      body: hasBody ? await req.text() : undefined,
    });

    const resHeaders: Record<string, string> = {};
    upstream.headers.forEach((value, key) => {
      if (!STRIP_RESPONSE_HEADERS.has(key)) resHeaders[key] = value.replace(/[^\x20-\x7E]/g, "");
    });

    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: resHeaders,
    });
  } catch (e) {
    console.error("[proxy]", e);
    return NextResponse.json({ error: "proxy error", detail: String(e) }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
