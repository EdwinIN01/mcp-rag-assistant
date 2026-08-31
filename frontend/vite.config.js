import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发代理：前端 5173 → 后端 8000，规避跨域并统一走 API（鉴权/日志/缓存全链路生效）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
