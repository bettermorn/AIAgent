import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发环境下将 /api 请求代理到 FastAPI 网关 (默认 http://localhost:8080)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
})
