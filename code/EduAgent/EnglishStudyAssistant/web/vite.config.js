import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发模式下将 /api 请求代理到 FastAPI 后端 (http://localhost:8000)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
