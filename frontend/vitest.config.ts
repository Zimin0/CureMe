import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'
import { buildDefines } from './buildInfo'

// Отдельный конфиг для тестов: без PWA и копирования OCR-файлов из vite.config.ts.
export default defineConfig({
  define: buildDefines(),
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    css: false,
    coverage: { include: ['src/**/*.{ts,tsx}'], exclude: ['src/test/**', 'src/**/*.test.*', 'src/main.tsx'] },
  },
})
