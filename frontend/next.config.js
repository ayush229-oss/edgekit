/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8765";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      // Proxy all /api/* browser calls to the backend.
      // Browser always uses /api (relative); server-side code uses BACKEND_URL directly.
      { source: "/api/:path*", destination: `${BACKEND_URL}/:path*` },
    ];
  },
};
module.exports = nextConfig;
