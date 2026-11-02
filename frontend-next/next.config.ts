import type { NextConfig } from "next";

// 服务端代理目标：浏览器只访问同源的 /backend/*，由 Next.js 转发到 FastAPI，
// 这样无需在浏览器侧处理 CORS，也不会把后端地址写死在前端代码里。
const backendBaseUrl = (
  process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      {
        source: "/backend/:path*",
        destination: `${backendBaseUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
