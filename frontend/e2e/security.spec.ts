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
