import type { NextConfig } from "next";

const API = process.env.STUDYROUTE_API ?? "http://127.0.0.1:8000";
const isProduction = process.env.NODE_ENV === "production";

/**
 * Production is a static export served by nginx, which also proxies /api to the backend (no Node
 * server at run time, so the container stays read-only and small). In development the Next dev
 * server proxies /api to the FastAPI backend the same way.
 */
const config: NextConfig = {
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
  ...(isProduction
    ? { output: "export" as const }
    : {
        async rewrites() {
          return [
            { source: "/api/:path*", destination: `${API}/api/:path*` },
            { source: "/health", destination: `${API}/health` },
          ];
        },
      }),
};

export default config;
