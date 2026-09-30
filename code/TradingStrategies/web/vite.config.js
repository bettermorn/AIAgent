import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式下将 /api 请求代理到本地 Flask 后端 (server.py)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
});
