import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the dev badge clear of the sidebar's "Bản in hôm nay" block.
  devIndicators: { position: "bottom-right" },
  // Proxy the API through the UI's own origin; the backend stays bound to localhost.
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
