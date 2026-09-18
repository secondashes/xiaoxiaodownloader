import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// Vite 配置：构建 Vue 渲染进程到 dist/
// 多入口：index.html=主窗口；sniffer.html=手动抓取（资源嗅探）独立窗口
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // naive-ui(全量)/hls.js 库本体即 >500KB，应用代码已分块完毕，阈值只对库块放宽
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        sniffer: resolve(__dirname, 'sniffer.html'),
      },
      // f5b 代码分割：第三方库归入单一 vendor 块——不能再按库细分（曾拆 vue/naive-ui 两块
      // 产生循环 import，渲染进程启动即 "Cannot access 'RefImpl' before initialization" TDZ 崩溃，
      // 库间循环回到同一 chunk 内部才安全）；各站视图已 defineAsyncComponent 自动分块
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) return 'vendor'
        },
      },
    },
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
  },
})
