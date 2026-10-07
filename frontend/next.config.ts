import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Keep the dev badge clear of the sidebar's "Bản in hôm nay" block.
  devIndicators: { position: "bottom-right" },
};

export default nextConfig;
