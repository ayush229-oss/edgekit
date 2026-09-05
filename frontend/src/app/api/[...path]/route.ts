import { NextRequest, NextResponse } from "next/server";
import { sanitizeBaseUrl, sanitizeHeaderValue } from "@/lib/sanitize-url";

// Vercel env values arrive decorated — BOM prefixes, shell quotes, Markdown
// link wrappers, trailing slashes — and `new URL()` inside fetch() then rejects
// them, 502-ing every proxied call. sanitizeBaseUrl strips all of that and
// falls back to the default when the value can't be salvaged.
const BACKEND_URL = sanitizeBaseUrl(
  process.env.NEXT_PUBLIC_API_URL,
  process.env.VERCEL ? "https://edgekit-v2.onrender.com" : "http://127.0.0.1:8765",
);

// Only forward headers that the backend actually needs.
// NB: accept-encoding is deliberately NOT forwarded. If the backend gzips the
// response, fetch() auto-decompresses it when we call .text(), but the upstream
// content-encoding/content-length headers then describe the compressed bytes —
// passing them through corrupts the response (empty body downstream). Letting
// the backend reply uncompressed sidesteps the whole mismatch.
// NB: the x-ai-* headers carry a user's own AI provider key for bring-your-own-key
// generation. They were missing from this list, so the browser set them, the proxy
// dropped them, and the backend silently fell back to the server key -- BYOK could
// never work from the browser at all.
const FORWARD_HEADERS = [
  "content-type", "authorization", "accept", "accept-language",
  "x-ai-key", "x-ai-provider", "x-gemini-key",
];

// Response headers that no longer describe the decoded body we forward.
const STRIP_RESPONSE_HEADERS = new Set([
  "transfer-encoding", "content-encoding", "content-length",
]);

// Backend paths the public proxy must never expose. The proxy injects the
// shared x-api-key, so without this gate any anonymous visitor could reach
// the VPS deploy webhooks (git pull + service restart) through /api/internal/*.
const BLOCKED_PREFIXES = ["/internal/"];

// Vercel kills a function at 10s by default, but the backend runs on Render's
// free tier, which suspends after ~15 min idle and takes ~23s to wake. The
// default therefore guarantees an error for the first visitor after any quiet
// spell. 60s is the Hobby-plan ceiling; raise it if the plan changes.
export const maxDuration = 60;

// Abort just under maxDuration so a hung backend produces a JSON 504 we control
// rather than Vercel's opaque function-timeout page.
const UPSTREAM_TIMEOUT_MS = 55_000;

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
    const apiKey = sanitizeHeaderValue(process.env.EDGEKIT_API_KEY);
    if (apiKey) reqHeaders["x-api-key"] = apiKey;

    const hasBody = !["GET", "HEAD"].includes(req.method);
    const upstream = await fetch(url, {
      method: req.method,
      headers: reqHeaders,
      body: hasBody ? await req.text() : undefined,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
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
    // AbortSignal.timeout rejects with a TimeoutError. Report it as 504 with a
    // message the UI can show verbatim, rather than a generic 502.
    if (e instanceof Error && e.name === "TimeoutError") {
      return NextResponse.json(
        { error: "backend timeout", detail: "The backend did not respond in time. It may be waking from idle — try again in a moment." },
        { status: 504 },
      );
    }
    return NextResponse.json({ error: "proxy error", detail: String(e) }, { status: 502 });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
