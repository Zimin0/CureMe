import { expect, test } from '@playwright/test'
import { loginAs, registerApi } from './helpers'

// Content Security Policy запрещает всё, чего не разрешили явно. Сканер (zxing-wasm) и распознавание
// срока (tesseract, воркер из blob: + wasm) — самое хрупкое, поэтому проверяем, что CSP им не мешает.
const PHOTO = '../docs/screenshots/d-detail.png'  // скриншот с текстом, кода на нём нет

test('CSP включена и не ломает сканер и распознавание срока', async ({ page, request }) => {
  const violations: string[] = []
  page.on('console', m => { if (/Content Security Policy|Refused to/i.test(m.text())) violations.push(m.text()) })

  const res = await request.get('/')
  expect(res.headers()['content-security-policy']).toContain("default-src 'self'")
  expect(res.headers()['x-frame-options']).toBe('DENY')

  const acc = await registerApi(request)
  await loginAs(page, acc, '/scan')
  await page.locator('input[type=file]').first().setInputFiles(PHOTO)
  await expect(page.getByText('На фото не нашлось кода')).toBeVisible({ timeout: 20_000 })  // значит, wasm-декодер запустился

  await page.goto('/medicines/new')
  await page.locator('input[type=file][capture]').nth(1).setInputFiles(PHOTO)
  await expect(page.getByText(/^Распознано:/)).toBeVisible({ timeout: 60_000 })
  await expect(page.getByText('Не удалось распознать фото')).toHaveCount(0)

  expect(violations).toEqual([])
})

// Открытый редирект: после входа ссылка вида /login?next=/\evil.example/ уводила на чужой сайт, потому что
// React Router принимает «/\» за начало чужого адреса и делает полный переход. Нужен настоящий Chromium.
test('после входа ?next= не уводит на чужой сайт', async ({ page, request }) => {
  const acc = await registerApi(request)
  const evil: string[] = []
  await page.route(/^https?:\/\/evil\.example/, route => { evil.push(route.request().url()); return route.fulfill({ body: 'evil' }) })

  await page.goto('/login?next=' + encodeURIComponent('/\\evil.example/phish'))
  await page.getByLabel('Почта').fill(acc.email)
  await page.getByLabel('Пароль').fill(acc.password)
  await page.getByRole('button', { name: 'Войти' }).click()

  await expect(page.getByRole('heading', { level: 1 })).toContainText(acc.name)  // вошли и остались на нашем сайте
  expect(new URL(page.url()).hostname).toBe('localhost')
  expect(evil).toEqual([])
})
