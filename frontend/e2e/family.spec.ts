import { expect, test } from '@playwright/test'
import { addMedicineApi, loginAs, registerApi, uniqueEmail } from './helpers'

test('приглашение по ссылке: второй человек видит общую аптечку, отметки у каждого свои', async ({ page, request, browser }) => {
  const owner = await registerApi(request, 'Никита')
  const med = await addMedicineApi(request, owner, { name: 'Ибупрофен', indications: 'головная боль', packages: [{ quantity: 10 }] })

  await loginAs(page, owner, '/family')
  const code = (await page.locator('.invite-code').textContent())!.trim()
  expect(code).toMatch(/^[A-Z2-9]{8}$/)

  // второй человек в отдельном браузере (свои cookies и localStorage)
  const ctx = await browser.newContext({ serviceWorkers: 'block' })
  const mom = await ctx.newPage()
  await mom.goto(`/join/${code}`)
  await expect(mom.getByRole('heading', { name: /Приглашение в «Семья Никита»/ })).toBeVisible()
  await mom.getByRole('link', { name: 'Создать аккаунт и вступить' }).click()
  await expect(mom.getByRole('heading', { name: 'Вступить в «Семья Никита»' })).toBeVisible()
  await mom.getByLabel('Как вас зовут').fill('Мама')
  await mom.getByLabel('Почта').fill(uniqueEmail('mom'))
  await mom.getByLabel(/^Пароль/).fill('secret123')
  await mom.getByRole('checkbox', { name: /согласие на обработку/ }).check()
  await mom.getByRole('checkbox', { name: /пользовательское соглашение/ }).check()
  await mom.getByRole('button', { name: 'Создать аккаунт' }).click()
  await expect(mom.getByRole('heading', { level: 1 })).toContainText('Мама')

  await mom.goto(`/medicines/${med.id}`)
  await expect(mom.getByRole('heading', { name: 'Ибупрофен' })).toBeVisible()
  await mom.getByRole('button', { name: 'Отметить: помогает мне' }).click()
  await expect(mom.getByRole('button', { name: 'Помогает мне' })).toBeVisible()

  // у владельца своя отметка не появилась, но видно, что помогает Маме
  await page.goto(`/medicines/${med.id}`)
  await expect(page.getByRole('button', { name: 'Отметить: помогает мне' })).toBeVisible()
  await expect(page.getByText('Также помогает: Мама')).toBeVisible()

  await page.goto('/family')
  await expect(page.getByTitle('Убрать из семьи')).toHaveCount(1)  // владелец может убрать Маму
  await ctx.close()
})

test('участник не видит кнопок владельца', async ({ page, request }) => {
  const owner = await registerApi(request, 'Никита')
  const info = await (await request.get(`/api/families/${owner.familyId}`, { headers: { Authorization: `Bearer ${owner.token}` } })).json()
  const member = await registerApi(request, 'Мама', info.invite_code)
  await loginAs(page, member, '/family')
  await expect(page.getByRole('heading', { name: 'Семья Никита' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Переименовать' })).toHaveCount(0)
  await expect(page.getByTitle('Сменить код')).toHaveCount(0)
})
