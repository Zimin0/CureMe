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

// Сохранённые фотографии кодов: проходим путь «загрузить фото → распознать в браузере → форма лекарства»
// на настоящем Chromium с wasm-декодером. Картинки сделаны один раз (см. e2e/fixtures/README.md).
test('фото штрихкода EAN-13 распознаётся и открывает форму нового лекарства', async ({ page, request }) => {
  const acc = await registerApi(request)
  await loginAs(page, acc, '/scan')
  await page.locator('input[type=file]').first().setInputFiles('e2e/fixtures/ean13.png')
  const sheet = page.getByRole('dialog', { name: 'Новое лекарство' })
  await expect(sheet.getByText('Код 4601669002013')).toBeVisible({ timeout: 20_000 })
})

test('фото DataMatrix читает серию и подставляет срок годности', async ({ page, request }) => {
  const acc = await registerApi(request)
  await loginAs(page, acc, '/scan')
  await page.locator('input[type=file]').first().setInputFiles('e2e/fixtures/datamatrix.png')
  const sheet = page.getByRole('dialog', { name: 'Новое лекарство' })
  await expect(sheet).toBeVisible({ timeout: 20_000 })
  await expect(sheet.getByText('Код 4601669002013')).toBeVisible()
  await expect(sheet.getByText('Серия AB1234')).toBeVisible()
  await expect(sheet.getByText(/Взято из кода на упаковке: 31 мая 2027/)).toBeVisible()
})
