import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, expect, it, vi } from 'vitest'
import type { Family } from '../api'
import { planFixture, server } from '../test/server'
import { renderApp } from '../test/utils'

const FAMILY: Family = {
  id: 7, name: 'Семья Никита', invite_code: 'X', role: 'owner', members: [
    { user_id: 1, name: 'Никита', email: 'nikita@example.com', role: 'owner', joined_at: '2026-09-01T00:00:00Z' },
    { user_id: 2, name: 'Мама', email: 'mom@example.com', role: 'member', joined_at: '2026-09-01T00:00:00Z' },
  ],
}

afterEach(() => vi.restoreAllMocks())

function setup() {
  const asked: URL[] = []
  server.use(
    http.get('/api/families/7', () => HttpResponse.json(FAMILY)),
    http.get('/api/families/7/export.txt', () => HttpResponse.text('Нурофен — 200 мг\n')),
    http.get('/api/families/7/intakes', () => HttpResponse.json([])),
    http.get('/api/families/7/intakes/older', () => HttpResponse.json({ history_since: null, hidden: 0 })),
    http.get('/api/families/7/report.pdf', ({ request }) => {
      asked.push(new URL(request.url))
      return new HttpResponse('%PDF-1.4', {
        headers: { 'Content-Type': 'application/pdf', 'Content-Disposition': 'attachment; filename="kapsulka-dlya-vracha-x.pdf"' },
      })
    }),
    http.get('/api/families/7/report.xlsx', () => HttpResponse.json({ detail: 'Экспорт для врача доступен в Капсулке Плюс' }, { status: 402, headers: { 'X-Plus-Feature': 'export_pdf' } })),
  )
  const clicks: string[] = []
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { clicks.push(this.download) })
  URL.createObjectURL = vi.fn(() => 'blob:x')
  URL.revokeObjectURL = vi.fn()
  return { asked, clicks }
}

async function openReport() {
  const r = renderApp('/history')
  await r.user.click(await screen.findByRole('button', { name: 'Для врача' }))
  return r
}

it('экспорт аптечки: только список, выписки для врача здесь нет', async () => {
  setup()
  renderApp('/export')
  expect(await screen.findByText('Экспорт аптечки')).toBeInTheDocument()
  expect(await screen.findByText('Нурофен — 200 мг')).toBeInTheDocument()
  expect(screen.queryByText('Для врача: PDF и Excel')).toBeNull()
})

it('выписка для врача на странице истории: чья история, период, аптечка — и скачивание PDF', async () => {
  const { asked, clicks } = setup()
  const { user } = await openReport()
  expect(await screen.findByText('Для врача: PDF и Excel')).toBeInTheDocument()

  await user.selectOptions(await screen.findByLabelText('Чья история'), '2')
  expect(screen.getByText(/Комментарии к приёму видит только их автор/)).toBeInTheDocument()
  await user.click(screen.getByRole('tab', { name: '90 дней' }))
  await user.click(screen.getByLabelText('Добавить, что сейчас есть в аптечке'))
  await user.click(screen.getByRole('button', { name: /^PDF$/ }))

  await waitFor(() => expect(clicks).toEqual(['kapsulka-dlya-vracha-x.pdf']))
  const q = asked[0].searchParams
  expect(q.get('member')).toBe('2')
  expect(q.get('cabinet')).toBe('true')
  expect(q.get('tz')).toBeTruthy()
  const days = (Date.parse(q.get('to')!) - Date.parse(q.get('from')!)) / 86_400_000
  expect(days).toBe(89)
})

it('свой период: кнопки выключены, пока начало позже конца', async () => {
  setup()
  const { user } = await openReport()
  await user.click(await screen.findByRole('tab', { name: 'Свой' }))
  const from = within(screen.getByText('Для врача: PDF и Excel').closest('section')!).getByLabelText('С')
  await user.clear(from)
  await user.type(from, '2099-01-01')
  expect(screen.getByRole('button', { name: /^PDF$/ })).toBeDisabled()
})

it('без Плюса: замочек у заголовка, 402 открывает шторку и ничего не скачивает', async () => {
  const { clicks } = setup()
  server.use(http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false, billing_enabled: true }))))
  const { user } = await openReport()
  expect(await screen.findByRole('button', { name: /Доступно в Плюсе/ })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /^Excel$/ }))
  expect(await screen.findByText('Доступно в Капсулке Плюс')).toBeInTheDocument()
  expect(clicks).toEqual([])
})
