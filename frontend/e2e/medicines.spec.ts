import { expect, test } from '@playwright/test'
import { addMedicineApi, inDays, loginAs, registerApi } from './helpers'

test('лекарство: добавить вручную → принять → подобрать → выгрузить → удалить', async ({ page, request }) => {
  const acc = await registerApi(request)
  await loginAs(page, acc, '/medicines/new')

  await page.getByLabel('Название *').fill('Нурофен')
  const cats = page.getByRole('group', { name: 'Категории' })
  await cats.getByRole('button', { name: /Обезболивающие/ }).click()
  await cats.getByRole('button', { name: /Жаропонижающие/ }).click()
  await page.getByLabel('Дозировка').fill('200 мг')
  await page.getByRole('button', { name: '+ головная боль' }).click()
  await page.getByLabel('Единица учёта').fill('таб')
  await page.getByRole('tab', { name: 'Поштучно (таб)' }).click()
  await page.getByRole('spinbutton', { name: 'Осталось, таб' }).fill('12')
  await page.getByRole('button', { name: 'Ввести текстом' }).click()
  await page.getByPlaceholder(/Как на упаковке/).fill('EXP 05/35')
  await expect(page.getByText(/Годен до 31 мая 2035/)).toBeVisible()
  await page.getByRole('button', { name: 'Добавить в аптечку' }).click()

  // карточка лекарства
  await expect(page.getByRole('heading', { name: 'Нурофен', level: 1 })).toBeVisible()
  await expect(page.getByText('«Нурофен» в аптечке')).toBeVisible()
  await expect(page.locator('.qty').first()).toHaveText('12таб')
  await expect(page.locator('.cat-badge')).toHaveText(['🩹 Обезболивающие', '🌡️ Жаропонижающие'])

  await page.getByRole('button', { name: /Принял\(а\) 1 таб/ }).click()
  await expect(page.locator('.qty').first()).toHaveText('11таб')
  // второе нажатие в ту же минуту складывается с первым; комментарий — по отдельной кнопке
  await page.getByRole('button', { name: 'Принять с комментарием' }).click()
  await page.getByLabel('Комментарий', { exact: true }).fill('болела голова')
  await page.getByRole('button', { name: 'Принял(а) и сохранить' }).click()
  await expect(page.locator('.qty').first()).toHaveText('10таб')
  await expect(page.locator('.intake')).toHaveCount(1)
  await expect(page.locator('.intake')).toContainText('2 таб')
  await expect(page.locator('.intake')).toContainText('болела голова')

  await page.getByRole('button', { name: 'Отметить: помогает мне' }).click()
  await expect(page.getByRole('button', { name: 'Помогает мне' })).toBeVisible()

  // подбор под болезнь находит его по синониму и ставит первым
  await page.goto('/find')
  await page.getByPlaceholder('Например: болит голова').fill('болит голова')
  await page.getByRole('button', { name: 'Найти', exact: true }).click()
  const first = page.locator('.condition-result').first()
  await expect(first).toContainText('Нурофен')
  await expect(first).toContainText('Вам помогает')

  // экспорт
  await page.goto('/export')
  await expect(page.locator('.export-preview')).toHaveText('Нурофен — 200 мг')

  // удаление
  await page.goto('/medicines')
  await page.getByRole('link', { name: /Нурофен/ }).click()
  page.once('dialog', d => d.accept())
  await page.getByRole('button', { name: 'Удалить лекарство' }).click()
  await expect(page.getByText('Лекарство удалено')).toBeVisible()
  await page.goto('/medicines')
  await expect(page.getByText('Аптечка пустая')).toBeVisible()
})

test('главная и фильтры показывают просрочку и то, что заканчивается', async ({ page, request }) => {
  const acc = await registerApi(request)
  await addMedicineApi(request, acc, { name: 'Смекта', packages: [{ quantity: 3, expiry_date: inDays(-3) }] })
  await addMedicineApi(request, acc, { name: 'Називин', packages: [{ quantity: 1, expiry_date: inDays(5) }] })
  await addMedicineApi(request, acc, { name: 'Лоратадин', min_quantity: 5, packages: [{ quantity: 2, expiry_date: inDays(300) }] })
  await addMedicineApi(request, acc, { name: 'Ибупрофен', packages: [{ quantity: 20, expiry_date: inDays(300) }] })

  await loginAs(page, acc)
  await expect(page.getByText('Требуют внимания: 3. Проверьте список ниже.')).toBeVisible()
  await expect(page.locator('.stat.danger .value')).toHaveText('1')
  await expect(page.locator('.stat.warning .value')).toHaveText('1')

  await page.goto('/medicines')
  await page.getByRole('button', { name: 'Просроченные' }).click()
  await expect(page.locator('.med-card')).toHaveCount(1)
  await expect(page.locator('.med-card')).toContainText('Смекта')
  await page.getByRole('button', { name: 'Требуют внимания' }).click()
  await expect(page.locator('.med-card')).toHaveCount(3)

  await page.getByRole('button', { name: 'Все', exact: true }).click()
  await page.getByRole('searchbox').fill('ибу')
  await expect(page.locator('.med-card')).toHaveCount(1)
  await expect(page).toHaveURL(/q=%D0%B8%D0%B1%D1%83|q=ибу/)
})
