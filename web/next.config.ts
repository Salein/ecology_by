import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /** Образ Docker: минимальный runtime (`node server.js`) */
  output: "standalone",
  turbopack: {
    root: process.cwd(),
  },
  /** Убирает значок Next.js внизу слева в режиме разработки */
  devIndicators: false,
};

export default nextConfig;
