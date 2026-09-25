import type { NextConfig } from "next";

const apiUrl = process.env.MOGUL_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  // The browser only talks to this origin; Next proxies /api/* to FastAPI.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
