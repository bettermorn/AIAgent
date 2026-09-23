import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发环境下将 /api 代理到 FastAPI 后端（默认 8000 端口）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
