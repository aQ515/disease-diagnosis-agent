// 疾病辅助诊断智能体 · 前端构建配置
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',   // 允许局域网访问
    port: 5174,        // 与参考项目(5173)错开，两个项目可同时跑
    // 前端只发 /api/**，由 Vite 代理到 Django，开发期零跨域
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',   // 后端也错开端口
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.spec.js'],
  },
})
