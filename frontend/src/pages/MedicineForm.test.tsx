import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, it } from 'vitest'
import type { MedicineDetail } from '../api'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

const pkg = (id: number, quantity: number) => ({
  id, quantity, expiry_date: '2027-05-31', opened_at: null, serial: null, batch: null, location: null,
  added_at: '2026-09-26T10:00:00Z', expired: false, days_left: 400,
})

// Было 20 таблеток в двух пачках, 13 уже приняли: осталось 7.
const detail = (over: Partial<MedicineDetail> = {}): MedicineDetail => ({
  ...medicine({ stock: { total: 7, expired_quantity: 0, package_count: 2, nearest_expiry: '2027-05-31', days_left: 400, status: 'ok' } }),
  packages: [pkg(1, 2), pkg(2, 5)],
  ...over,
})

beforeEach(() => {
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/indication-hints', () => HttpResponse.json(['головная боль'])),
    http.get('/api/families/7/intakes', () => HttpResponse.json([])),
  )
})

it('в форме редактирования видно, сколько лекарства осталось на самом деле', async () => {
  server.use(http.get('/api/families/7/medicines/1', () => HttpResponse.json(detail())))
  renderApp('/medicines/1/edit')
  const stock = await screen.findByTestId('current-stock')
  expect(stock).toHaveTextContent('7таб')
  expect(screen.getByText('Годного, во всех упаковках (2)')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Изменить в упаковках' })).toHaveAttribute('href', '/medicines/1')
})

it('«Добавить» в пустом «От чего помогает» сразу ставит курсор в поле', async () => {
  server.use(http.get('/api/families/7/medicines/1', () => HttpResponse.json(detail({ indications: '' }))))
  const { user } = renderApp('/medicines/1')
  await user.click(await screen.findByRole('link', { name: 'Добавить' }))
  const field = await screen.findByRole('textbox', { name: 'От чего помогает' })
  expect(screen.getByTestId('location').textContent).toBe('/medicines/1/edit?focus=indications')
  expect(field).toHaveFocus()
})

it('обычное редактирование не уводит фокус в поле показаний', async () => {
  server.use(http.get('/api/families/7/medicines/1', () => HttpResponse.json(detail())))
  renderApp('/medicines/1/edit')
  expect(await screen.findByRole('textbox', { name: 'От чего помогает' })).not.toHaveFocus()
})

// --- «Такая же упаковка?» при добавлении ---
const fillNew = async (user: ReturnType<typeof renderApp>['user'], name: string, dosage: string) => {
  await user.type(await screen.findByPlaceholderText('Например, Нурофен'), name)
  await user.type(screen.getByPlaceholderText('200 мг'), dosage)
  await user.click(screen.getByRole('button', { name: 'Добавить в аптечку' }))
}

it('то же название и дозировка: спрашиваем про упаковку и добавляем пачку в старую карточку', async () => {
  let added: unknown = null
  server.use(
    http.get('/api/families/7/medicines', () => HttpResponse.json([medicine({ id: 5, name: 'МИГ 400', dosage: '400 мг' })])),
    http.post('/api/families/7/medicines/5/packages', async ({ request }) => {
      added = await request.json()
      return HttpResponse.json(detail({ id: 5, name: 'МИГ 400' }), { status: 201 })
    }),
    http.get('/api/families/7/medicines/5', () => HttpResponse.json(detail({ id: 5, name: 'МИГ 400' }))),
  )
  const { user } = renderApp('/medicines/new')
  await fillNew(user, 'миг 400', '400мг')
  await user.click(await screen.findByRole('button', { name: /Такая же упаковка: добавить пачку/ }))
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/medicines/5'))
  expect(added).toMatchObject({ quantity: 1 })
})

it('«Нет, другая упаковка» заводит отдельную карточку', async () => {
  let created: unknown = null
  server.use(
    http.get('/api/families/7/medicines', () => HttpResponse.json([medicine({ id: 5, name: 'МИГ 400', dosage: '400 мг' })])),
    http.post('/api/families/7/medicines', async ({ request }) => {
      created = await request.json()
      return HttpResponse.json(detail({ id: 9, name: 'МИГ 400' }), { status: 201 })
    }),
    http.get('/api/families/7/medicines/9', () => HttpResponse.json(detail({ id: 9, name: 'МИГ 400' }))),
  )
  const { user } = renderApp('/medicines/new')
  await fillNew(user, 'МИГ 400', '400 мг')
  await user.click(await screen.findByRole('button', { name: /Нет, другая упаковка/ }))
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/medicines/9'))
  expect(created).toMatchObject({ name: 'МИГ 400' })
})

it('другая дозировка: вопроса нет, сразу новая карточка', async () => {
  server.use(
    http.get('/api/families/7/medicines', () => HttpResponse.json([medicine({ id: 5, name: 'МИГ 400', dosage: '400 мг' })])),
    http.post('/api/families/7/medicines', () => HttpResponse.json(detail({ id: 9, name: 'МИГ 200' }), { status: 201 })),
    http.get('/api/families/7/medicines/9', () => HttpResponse.json(detail({ id: 9, name: 'МИГ 200' }))),
  )
  const { user } = renderApp('/medicines/new')
  await fillNew(user, 'МИГ 400', '200 мг')
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/medicines/9'))
  expect(screen.queryByText('Такая упаковка уже есть?')).not.toBeInTheDocument()
})
