import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// 后端默认端口见 scripts/run_dashboard.py / dashboard_server；开发代理到此地址。
const API_PROXY_TARGET = process.env.BINGGO_API_PROXY || "http://127.0.0.1:8787";

export default defineConfig({
  root: rootDir,
  base: "/",
  resolve: {
    alias: {
      "@": path.resolve(rootDir, "src"),
    },
  },
  build: {
    outDir: path.resolve(rootDir, "../static/dist"),
    emptyOutDir: true,
    assetsDir: "assets",
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: API_PROXY_TARGET,
        changeOrigin: true,
        // SSE（/api/events）长连接：禁止代理超时掐断
        timeout: 0,
        proxyTimeout: 0,
      },
    },
  },
});
