/**
 * Auth middleware — gates routes behind Clerk signin.
 *
 * Public:    /, /strategies, /sign-in, /sign-up, /api/* (the v2 Python proxy)
 * Protected: /builder, /resources, /analytics, /testimonials, /strategy/[id]
 *
 * Note on /api: it forwards to the Python backend, which has its own auth
 * (X-Gemini-Key header etc.). We don't gate the proxy itself — that would
 * break public templates page (which fetches /api/strategies for previews).
 */
import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";

const isProtected = createRouteMatcher([
  "/builder(.*)",
  "/resources(.*)",
  "/analytics(.*)",
  "/testimonials(.*)",
  "/strategy/(.*)",
  "/upload(.*)",
  "/dashboard(.*)",
  "/home(.*)",
  "/strategies(.*)",
  "/suggestions(.*)",
  "/affiliate(.*)",
  "/legal(.*)",
  "/admin(.*)",
]);

export default clerkMiddleware(async (auth, req) => {
  if (isProtected(req)) {
    await auth.protect();    // redirects unauthenticated users to /sign-in
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
