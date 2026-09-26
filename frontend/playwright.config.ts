import { defineConfig, devices } from '@playwright/test'

// E2E: настоящий браузер + настоящий бэкенд (FastAPI отдаёт собранный фронтенд).
// Перед запуском: npm run build. Запуск: npm run test:e2e
const PORT = Number(process.env.E2E_PORT ?? 8765)
const executablePath = process.env.PW_CHROMIUM_PATH || undefined  // свой Chromium, если браузер Playwright не скачан

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: 'ru-RU',
    serviceWorkers: 'block',  // PWA-кеш мешает тестам видеть свежие ответы
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    launchOptions: { executablePath },
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], launchOptions: { executablePath } } },
    { name: 'mobile', use: { ...devices['Pixel 7'], launchOptions: { executablePath } } },
  ],
  webServer: {
    command: 'bash e2e/server.sh',
    url: `http://localhost:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    env: { E2E_PORT: String(PORT) },
    timeout: 60_000,
  },
})
