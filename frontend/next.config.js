/** @type {import('next').NextConfig} */
// On Vercel: VERCEL=1 is set automatically, so default to the VPS.
// Locally: default to the local backend. Override both with NEXT_PUBLIC_API_URL.
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL ||
  (process.env.VERCEL ? "http://165.232.178.128:8765" : "http://127.0.0.1:8765");

const nextConfig = {
  reactStrictMode: true,
  // Expose EDGEKIT_API_KEY to the Edge runtime (middleware) so it can inject
  // the x-api-key header on /api/* proxy requests. Without this, Next.js Edge
  // bundles don't include non-NEXT_PUBLIC_ vars.
  env: {
    EDGEKIT_API_KEY: process.env.EDGEKIT_API_KEY || "",
  },
  async rewrites() {
    return [
      // Proxy all /api/* browser calls to the backend.
      // Browser always uses /api (relative); server-side code uses BACKEND_URL directly.
      { source: "/api/:path*", destination: `${BACKEND_URL}/:path*` },
    ];
  },
};
module.exports = nextConfig;
