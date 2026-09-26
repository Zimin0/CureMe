import { expect, test } from '@playwright/test'
import { loginAs, randomEan13, registerApi } from './helpers'

// Камеры в CI нет, поэтому код вводим вручную — дальше путь тот же, что после сканирования.
test('новый штрихкод → сохранить → повторный скан узнаёт лекарство', async ({ page, request }) => {
  const acc = await registerApi(request)
  const ean = randomEan13()  // справочник общий для всех, поэтому код у теста свой
  await loginAs(page, acc, '/scan')

  const findByCode = async () => {
    await page.getByPlaceholder(/Цифры под штрихкодом/).fill(ean)
    await page.getByRole('button', { name: 'Найти', exact: true }).click()
  }

  await findByCode()
  const sheet = page.getByRole('dialog', { name: 'Новое лекарство' })
  await expect(sheet.getByText(`Код ${ean}`)).toBeVisible()
  await sheet.getByLabel('Название').fill('Ларингобакт')
  await sheet.getByRole('button', { name: 'Сохранить в аптечку' }).click()
  await expect(page.getByRole('heading', { name: 'Ларингобакт', level: 1 })).toBeVisible()

  await page.goto('/scan')
  await findByCode()
  const known = page.getByRole('dialog', { name: 'Уже есть в аптечке' })
  await expect(known.getByText('Ларингобакт')).toBeVisible()
  await known.getByRole('button', { name: 'Добавить упаковку' }).click()
  await expect(page.getByText(/Упаковка добавлена/)).toBeVisible()
})

test('неверный код показывает ошибку', async ({ page, request }) => {
  const acc = await registerApi(request)
  await loginAs(page, acc, '/scan')
  await page.getByPlaceholder(/Цифры под штрихкодом/).fill('12345')
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  await expect(page.getByText(/Не получилось распознать код/)).toBeVisible()
})
