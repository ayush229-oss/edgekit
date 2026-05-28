/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    // Default to relative /api so the frontend proxies through Next.js
    // (works for local dev AND public tunnels with a single exposed port).
    // Override with an absolute URL only if you're hosting backend separately.
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "/api",
  },
  async rewrites() {
    return [
      // Proxy all /api/* calls from the browser to the local backend.
      // The browser only ever talks to port 3000 — no CORS, no second tunnel.
      { source: "/api/:path*", destination: `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765"}/:path*` },
    ];
  },
};
module.exports = nextConfig;
