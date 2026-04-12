import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: process.cwd(),
  },
  /** Убирает значок Next.js внизу слева в режиме разработки */
  devIndicators: false,
};

export default nextConfig;
