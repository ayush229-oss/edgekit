/**
 * Auth middleware — gates routes behind Clerk signin.
 *
 * Public:    /, /strategies, /sign-in, /sign-up, /waitlist, /api/* (the v2 Python proxy)
 * Protected: everything inside (app) layout — /home, /builder, /forward, /resources,
 *            /analytics, /upload, /suggestions, /affiliate, /admin, /strategy/[id]
 *
 * Note on /api: it forwards to the Python backend, which has its own auth.
 * We don't gate the proxy itself so public pages (e.g. strategy previews) still work.
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const isProtected = createRouteMatcher([
  "/home(.*)",
  "/forward(.*)",
  "/resources(.*)",
  "/analytics(.*)",
  "/upload(.*)",
  "/dashboard(.*)",
  "/suggestions(.*)",
  "/affiliate(.*)",
  "/admin(.*)",
  "/strategy/(.*)",
  // /builder is excluded — it uses ssr:false (ReactFlow) and has its own
  // client-side auth check via useUser() that redirects to /sign-in.
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();    // redirects unauthenticated users to /sign-in
  }

  // Inject the shared API key on backend-proxy calls (/api/* → VPS rewrite).
  // EDGEKIT_API_KEY is a server-only env var (no NEXT_PUBLIC_ prefix) so the
  // browser never sees it. The VPS requires this header on every request.
  if (req.nextUrl.pathname.startsWith("/api/")) {
    const key = process.env.EDGEKIT_API_KEY;
    if (key) {
      const headers = new Headers(req.headers);
      headers.set("x-api-key", key);
      return NextResponse.next({ request: { headers } });
    }
  }
});

export const config = {
  matcher: [
    // Skip Next internals + all static files
    "/((?!_next|.*\\..*).*)",
    // Always run for API routes (but the matcher above lets them through;
    // they're explicitly NOT in `isProtected` so they remain public)
    "/api/(.*)",
  ],
};
