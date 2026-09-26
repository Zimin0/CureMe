import react from '@vitejs/plugin-react'
import { copyFileSync, mkdirSync } from 'node:fs'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// Распознавание текста (срок годности на фото) работает в браузере через tesseract.js.
// Его воркер, wasm-ядро и языковую модель кладём к себе в public/ocr, чтобы не зависеть от CDN.
function ocrAssets(): Plugin {
  const files: [string, string][] = [
    ['tesseract.js/dist/worker.min.js', 'worker.min.js'],
    ['tesseract.js-core/tesseract-core-lstm.wasm.js', 'tesseract-core-lstm.wasm.js'],
    ['tesseract.js-core/tesseract-core-simd-lstm.wasm.js', 'tesseract-core-simd-lstm.wasm.js'],
    ['tesseract.js-core/tesseract-core-relaxedsimd-lstm.wasm.js', 'tesseract-core-relaxedsimd-lstm.wasm.js'],
    ['@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz', 'eng.traineddata.gz'],
  ]
  return {
    name: 'cureme-ocr-assets',
    buildStart() {
      mkdirSync('public/ocr', { recursive: true })
      for (const [from, to] of files) copyFileSync(`node_modules/${from}`, `public/ocr/${to}`)
    },
  }
}

export default defineConfig({
  plugins: [
    ocrAssets(),
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icon.svg', 'icon-192.png', 'icon-512.png'],
      manifest: {
        name: 'CureMe — домашняя аптечка',
        short_name: 'CureMe',
        description: 'Лекарства всей семьи, сроки годности и остатки',
        lang: 'ru',
        theme_color: '#0f9d8a',
        background_color: '#f4f7f6',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
          { src: '/icon.svg', sizes: 'any', type: 'image/svg+xml' },
        ],
      },
      workbox: {
        // wasm-модуль сканера больше лимита по умолчанию
        maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
        globPatterns: ['**/*.{js,css,html,svg,png,wasm,woff2}'],
        // OCR весит ~8 МБ: не качаем его всем заранее, а кешируем при первом использовании.
        globIgnores: ['ocr/**'],
        runtimeCaching: [{ urlPattern: /\/ocr\//, handler: 'CacheFirst', options: { cacheName: 'ocr' } }],
        navigateFallbackDenylist: [/^\/api/, /^\/docs/],
      },
    }),
  ],
  server: { proxy: { '/api': 'http://localhost:8000' } },
})
