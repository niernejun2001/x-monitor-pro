import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
  },
  build: {
    outDir: path.resolve(__dirname, '../static/app'),
    emptyOutDir: true,
    cssCodeSplit: false,
    assetsInlineLimit: 0,
    rollupOptions: {
      input: path.resolve(__dirname, 'src/main.ts'),
      output: {
        inlineDynamicImports: true,
        entryFileNames: 'app.js',
        chunkFileNames: 'chunks/[name].js',
        assetFileNames: (assetInfo) => {
          if ((assetInfo.name || '').endsWith('.css')) return 'app.css'
          return 'assets/[name][extname]'
        }
      }
    }
  }
})
