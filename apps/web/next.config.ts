import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  transpilePackages: ["@insurance/contracts"],
};

export default nextConfig;
