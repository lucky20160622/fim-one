import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Use separate output dir for production builds so `next build`
  // doesn't nuke the dev server's .next/ directory mid-HMR.
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
};

export default nextConfig;
