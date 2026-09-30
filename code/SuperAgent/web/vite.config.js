import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 后端 FastAPI 默认运行在 8000 端口，开发时代理 API 请求
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
