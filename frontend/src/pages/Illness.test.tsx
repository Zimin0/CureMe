import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, expect, it, vi } from 'vitest'
import type { Illness } from '../api'
import { dayKey } from '../illness'
import { server } from '../test/server'
import { renderApp } from '../test/utils'

const now = new Date()
const day = (n: number) => dayKey(new Date(now.getFullYear(), now.getMonth(), n))
const cell = (n: number) => screen.getByRole('gridcell', { name: new Date(now.getFullYear(), now.getMonth(), n).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }) })

function record(over: Partial<Illness> = {}): Illness {
  return { id: 1, title: 'ОРВИ', date_from: day(3), date_to: day(5), comment: 'температура', documents: [], created_at: '', updated_at: '', ...over }
}

afterEach(() => vi.restoreAllMocks())

it('клик по дню выбирает один день, протяжка — период; запись сохраняется с комментарием', async () => {
  const posted: unknown[] = []
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([])),
    http.post('/api/illnesses', async ({ request }) => { posted.push(await request.json()); return HttpResponse.json(record(), { status: 201 }) }),
  )
  const { user } = renderApp('/illness')
  expect(await screen.findByText('Пока пусто')).toBeInTheDocument()

  fireEvent.pointerDown(cell(10))
  fireEvent.pointerUp(window)
  expect(screen.getByTestId('period').textContent).toMatch(/^10 /)
  expect(cell(10)).toHaveAttribute('aria-selected', 'true')

  // протяжка с 12-го на 15-е: касание ищет клетку под пальцем по координатам
  document.elementFromPoint = vi.fn(() => cell(15))
  fireEvent.pointerDown(cell(12))
  fireEvent.pointerMove(screen.getByRole('grid'), { clientX: 5, clientY: 5 })
  fireEvent.pointerUp(window)
  expect(screen.getByTestId('period').textContent).toContain('4 дн.')
  expect(cell(13)).toHaveAttribute('aria-selected', 'true')
  expect(cell(11)).toHaveAttribute('aria-selected', 'false')

  // обратно: тянем назад, период всё равно «с меньшей даты»
  document.elementFromPoint = vi.fn(() => cell(8))
  fireEvent.pointerDown(cell(12))
  fireEvent.pointerMove(screen.getByRole('grid'), { clientX: 1, clientY: 1 })
  fireEvent.pointerUp(window)
  expect(screen.getByLabelText('Болезнь с даты')).toHaveValue(day(8))
  expect(screen.getByLabelText('Болезнь по дату')).toHaveValue(day(12))

  await user.type(screen.getByLabelText('Название болезни'), 'Грипп')
  await user.type(screen.getByLabelText('Комментарий к болезни'), 'лежали дома')
  await user.click(screen.getByRole('button', { name: 'Сохранить запись' }))
  expect(await screen.findByText('Запись сохранена')).toBeInTheDocument()
  expect(posted).toEqual([{ title: 'Грипп', comment: 'лежали дома', date_from: day(8), date_to: day(12) }])
})

it('без выбранных дат запись не отправляется', async () => {
  server.use(http.get('/api/illnesses', () => HttpResponse.json([])))
  const { user } = renderApp('/illness')
  await screen.findByText('Пока пусто')
  await user.click(screen.getByRole('button', { name: 'Сохранить запись' }))
  expect(await screen.findByText('Выберите день или период в календаре')).toBeInTheDocument()
})

it('записи видны, дни отмечены; правка и удаление', async () => {
  const patched: unknown[] = []
  let removed = 0
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([record()])),
    http.patch('/api/illnesses/1', async ({ request }) => { patched.push(await request.json()); return HttpResponse.json(record({ comment: 'лучше' })) }),
    http.delete('/api/illnesses/1', () => { removed++; return new HttpResponse(null, { status: 204 }) }),
  )
  window.scrollTo = vi.fn()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const { user } = renderApp('/illness')
  const list = await screen.findByRole('region', { name: 'Записи' })
  expect(within(list).getByText('ОРВИ')).toBeInTheDocument()
  expect(within(list).getByText('температура')).toBeInTheDocument()
  expect(cell(4).className).toContain('marked')
  expect(cell(8).className).not.toContain('marked')

  await user.click(screen.getByRole('button', { name: 'Изменить запись' }))
  expect(screen.getByLabelText('Название болезни')).toHaveValue('ОРВИ')
  expect(screen.getByLabelText('Болезнь по дату')).toHaveValue(day(5))
  await user.clear(screen.getByLabelText('Комментарий к болезни'))
  await user.type(screen.getByLabelText('Комментарий к болезни'), 'лучше')
  await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }))
  await waitFor(() => expect(patched).toEqual([{ title: 'ОРВИ', comment: 'лучше', date_from: day(3), date_to: day(5) }]))

  await user.click(screen.getByRole('button', { name: 'Удалить запись' }))
  await waitFor(() => expect(removed).toBe(1))
})

it('фото документа грузится с токеном и открывается крупно', async () => {
  const auth: (string | null)[] = []
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([record({ documents: [{ id: 9, url: '/api/illnesses/1/documents/9' }] })])),
    http.get('/api/illnesses/1/documents/9', ({ request }) => { auth.push(request.headers.get('Authorization')); return new HttpResponse(new Blob(['x'], { type: 'image/jpeg' }), { headers: { 'Content-Type': 'image/jpeg' } }) }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:doc')
  URL.revokeObjectURL = vi.fn()
  const { user } = renderApp('/illness')
  await user.click(await screen.findByRole('button', { name: 'Открыть фото' }))
  expect(await screen.findByRole('dialog')).toBeInTheDocument()
  expect(auth[0]).toBe('Bearer test-token')
})

it('на странице есть вкладки приёма', async () => {
  server.use(http.get('/api/illnesses', () => HttpResponse.json([])))
  renderApp('/illness')
  await screen.findByText('Пока пусто')
  expect(screen.getByRole('link', { name: 'Болезни' })).toHaveAttribute('href', '/illness')
})

it('выбранные фото отправляются вместе с записью', async () => {
  const uploaded: string[] = []
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([])),
    http.post('/api/illnesses', () => HttpResponse.json(record(), { status: 201 })),
    http.post('/api/illnesses/1/documents', () => { uploaded.push('document'); return HttpResponse.json(record(), { status: 201 }) }),
  )
  URL.createObjectURL = vi.fn(() => 'blob:x')
  globalThis.createImageBitmap = vi.fn(async () => ({ width: 10, height: 10, close() {} })) as never
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage() {} })) as never
  HTMLCanvasElement.prototype.toBlob = function (cb: BlobCallback) { cb(new Blob(['x'], { type: 'image/jpeg' })) }
  const { user } = renderApp('/illness')
  await screen.findByText('Пока пусто')
  fireEvent.pointerDown(cell(10)); fireEvent.pointerUp(window)
  const input = screen.getByLabelText('Добавить фото документа') as HTMLInputElement
  await user.upload(input, new File(['a'], 'справка.png', { type: 'image/png' }))
  expect(await screen.findByAltText('Выбрано: справка.png')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Сохранить запись' }))
  expect(await screen.findByText('Запись сохранена')).toBeInTheDocument()
  expect(uploaded).toEqual(['document'])
})
