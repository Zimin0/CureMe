import { expect, test } from '@playwright/test'
import { uniqueEmail } from './helpers'

test('регистрация, выход и повторный вход', async ({ page }) => {
  const email = uniqueEmail('new')
  await page.goto('/')
  await expect(page).toHaveURL(/\/login/)

  await page.getByRole('link', { name: 'Зарегистрироваться' }).click()
  await page.getByLabel('Как вас зовут').fill('Никита')
  await page.getByLabel('Почта').fill(email)
  await page.getByLabel(/^Пароль/).fill('secret123')
  await page.getByRole('button', { name: 'Создать аккаунт' }).click()

  await expect(page.getByRole('heading', { level: 1 })).toContainText('Никита')
  await expect(page.getByText(/Аптечка пока пустая/)).toBeVisible()

  await page.goto('/family')
  await page.getByRole('button', { name: 'Выйти из аккаунта' }).click()
  await expect(page).toHaveURL(/\/login/)

  await page.getByLabel('Почта').fill(email.toUpperCase())
  await page.getByLabel('Пароль').fill('wrong-pass')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByText('Неверная почта или пароль')).toBeVisible()

  await page.getByLabel('Пароль').fill('secret123')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Никита')
})

test('после входа возвращает на страницу, куда шёл', async ({ page, request }) => {
  const email = uniqueEmail()
  await request.post('/api/auth/register', { data: { email, name: 'Мама', password: 'secret123' } })
  await page.goto('/find?q=кашель')
  await expect(page).toHaveURL(/\/login\?next=/)
  await page.getByLabel('Почта').fill(email)
  await page.getByLabel('Пароль').fill('secret123')
  await page.getByRole('button', { name: 'Войти' }).click()
  await expect(page.getByRole('heading', { name: 'Подобрать лекарство' })).toBeVisible()
  await expect(page).toHaveURL(/\/find\?q=/)
})
