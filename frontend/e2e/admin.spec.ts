import { expect, test } from '@playwright/test'
import { adminApi, loginAs, registerApi } from './helpers'

test('администратор добавляет категорию, и её сразу видят все семьи', async ({ page, request, browser }) => {
  const admin = await adminApi(request)
  const name = `Глаза ${Date.now() % 100000}`

  await loginAs(page, admin, '/admin?tab=categories')
  await expect(page.getByRole('heading', { name: 'Администрирование' })).toBeVisible()
  await page.getByRole('button', { name: 'Новая' }).click()
  const dialog = page.getByRole('dialog', { name: 'Новая категория' })
  await dialog.getByPlaceholder('Название').fill(name)
  await dialog.getByRole('radio', { name: '👁️' }).click()
  await dialog.getByRole('radio', { name: '#6e56cf' }).click()
  await dialog.getByRole('button', { name: 'Сохранить' }).click()
  await expect(page.getByText(name)).toBeVisible()

  // обычный человек из другой семьи видит новую категорию в форме лекарства
  const user = await registerApi(request, 'Маша')
  const ctx = await browser.newContext({ serviceWorkers: 'block' })
  const other = await ctx.newPage()
  await loginAs(other, user, '/medicines/new')
  await expect(other.getByRole('group', { name: 'Категории' }).getByRole('button', { name: new RegExp(name) })).toHaveCount(1)
  // а в админку его не пускает
  await other.goto('/admin')
  await expect(other).toHaveURL(/\/$/)
  await ctx.close()
})

test('ни одна страница не шире экрана: вкладки админки и меню помещаются на телефоне', async ({ page, request }) => {
  const admin = await adminApi(request)
  await page.setViewportSize({ width: 360, height: 780 })  // узкий телефон: самые частые Android
  await loginAs(page, admin, '/')
  for (const path of ['/', '/medicines', '/find', '/family', '/history', '/export', '/admin']) {
    await page.goto(path)
    await page.locator('main h1').first().waitFor()
    const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth])
    expect(scroll, `${path}: страница шире экрана`).toBeLessThanOrEqual(width)
  }
  await expect(page.getByRole('tab', { name: 'Доступ' })).toBeInViewport()
})
