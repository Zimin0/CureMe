import { screen } from '@testing-library/react'
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
