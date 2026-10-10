import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, expect, it, vi } from 'vitest'
import type { Illness } from '../api'
import { dayKey } from '../illness'
import { planFixture, server } from '../test/server'
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
  const { user } = renderApp('/illness/new')
  await screen.findByRole('heading', { name: 'Записать болезнь' })

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
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/illness'))  // после сохранения — назад к списку
})

it('без выбранных дат запись не отправляется', async () => {
  server.use(http.get('/api/illnesses', () => HttpResponse.json([])))
  const { user } = renderApp('/illness/new')
  await screen.findByRole('heading', { name: 'Записать болезнь' })
  await user.click(screen.getByRole('button', { name: 'Сохранить запись' }))
  expect(await screen.findByText('Выберите день или период в календаре')).toBeInTheDocument()
})

it('список: записи и кнопка «Записать» сверху, удаление', async () => {
  let removed = 0
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([record()])),
    http.delete('/api/illnesses/1', () => { removed++; return new HttpResponse(null, { status: 204 }) }),
  )
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  const { user } = renderApp('/illness')
  const list = await screen.findByRole('region', { name: 'Записи' })
  expect(within(list).getByText('ОРВИ')).toBeInTheDocument()
  expect(within(list).getByText('температура')).toBeInTheDocument()
  expect(screen.queryByRole('grid')).toBeNull()  // календаря на списке нет
  expect(screen.getByRole('button', { name: /Записать/ })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Изменить запись' })).toHaveAttribute('href', '/illness/1/edit')
  await user.click(screen.getByRole('button', { name: 'Удалить запись' }))
  await waitFor(() => expect(removed).toBe(1))
})

it('пустой список зовёт нажать «Записать», кнопка открывает форму', async () => {
  server.use(http.get('/api/illnesses', () => HttpResponse.json([])))
  const { user } = renderApp('/illness')
  expect(await screen.findByText('Пока пусто')).toBeInTheDocument()
  await user.click(screen.getAllByRole('button', { name: /Записать/ })[0])
  expect(await screen.findByRole('heading', { name: 'Записать болезнь' })).toBeInTheDocument()
  expect(screen.getByTestId('location').textContent).toBe('/illness/new')
})

it('правка записи: форма заполнена, дни отмечены, после сохранения возврат к списку', async () => {
  const patched: unknown[] = []
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([record()])),
    http.patch('/api/illnesses/1', async ({ request }) => { patched.push(await request.json()); return HttpResponse.json(record({ comment: 'лучше' })) }),
  )
  const { user } = renderApp('/illness/1/edit')
  expect(await screen.findByRole('heading', { name: 'Изменить запись' })).toBeInTheDocument()
  await waitFor(() => expect(screen.getByLabelText('Название болезни')).toHaveValue('ОРВИ'))
  expect(screen.getByLabelText('Болезнь по дату')).toHaveValue(day(5))
  expect(cell(4).className).toContain('marked')
  expect(cell(8).className).not.toContain('marked')
  await user.clear(screen.getByLabelText('Комментарий к болезни'))
  await user.type(screen.getByLabelText('Комментарий к болезни'), 'лучше')
  await user.click(screen.getByRole('button', { name: 'Сохранить изменения' }))
  await waitFor(() => expect(patched).toEqual([{ title: 'ОРВИ', comment: 'лучше', date_from: day(3), date_to: day(5) }]))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/illness'))
})

it('правка несуществующей записи показывает сообщение', async () => {
  server.use(http.get('/api/illnesses', () => HttpResponse.json([])))
  renderApp('/illness/99/edit')
  expect(await screen.findByText(/Запись не найдена/)).toBeInTheDocument()
})

it('вместо фото зелёная плашка «Есть вложения (N)»; просмотр листается и грузит фото с токеном', async () => {
  const auth: (string | null)[] = []
  const photo = ({ request }: { request: Request }) => { auth.push(request.headers.get('Authorization')); return new HttpResponse(new Blob(['x'], { type: 'image/jpeg' }), { headers: { 'Content-Type': 'image/jpeg' } }) }
  server.use(
    http.get('/api/illnesses', () => HttpResponse.json([record({ documents: [{ id: 9, url: '/api/illnesses/1/documents/9' }, { id: 10, url: '/api/illnesses/1/documents/10' }] })])),
    http.get('/api/illnesses/1/documents/:doc', photo),
  )
  URL.createObjectURL = vi.fn(() => 'blob:doc')
  URL.revokeObjectURL = vi.fn()
  const { user } = renderApp('/illness')
  const badge = await screen.findByRole('button', { name: /Есть вложения \(2\)/ })
  expect(badge.className).toContain('ok')
  expect(screen.queryByAltText(/Фото документа/)).toBeNull()  // миниатюр в списке нет
  await user.click(badge)
  const dialog = await screen.findByRole('dialog', { name: 'Вложения (1 из 2)' })
  expect(within(dialog).getByRole('button', { name: 'Предыдущее фото' })).toBeDisabled()
  await user.click(within(dialog).getByRole('button', { name: 'Следующее фото' }))
  expect(await screen.findByRole('dialog', { name: 'Вложения (2 из 2)' })).toBeInTheDocument()
  await user.keyboard('{ArrowLeft}')
  expect(await screen.findByRole('dialog', { name: 'Вложения (1 из 2)' })).toBeInTheDocument()
  await waitFor(() => expect(auth[0]).toBe('Bearer test-token'))
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
  const { user } = renderApp('/illness/new')
  await screen.findByRole('heading', { name: 'Записать болезнь' })
  fireEvent.pointerDown(cell(10)); fireEvent.pointerUp(window)
  const input = screen.getByLabelText('Добавить фото документа') as HTMLInputElement
  await user.upload(input, new File(['a'], 'справка.png', { type: 'image/png' }))
  expect(await screen.findByAltText('Выбрано: справка.png')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Сохранить запись' }))
  expect(await screen.findByText('Запись сохранена')).toBeInTheDocument()
  expect(uploaded).toEqual(['document'])
})

it('без Плюса «Записать» открывает шторку Плюса, а прямая ссылка на форму закрыта плашкой; список остаётся', async () => {
  server.use(
    http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false }))),
    http.get('/api/illnesses', () => HttpResponse.json([record()])),
  )
  const { user } = renderApp('/illness')
  expect(await screen.findByText('температура')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Записать' }))
  expect(await screen.findByText('Доступно в Капсулке Плюс')).toBeInTheDocument()
})

it('без Плюса страница новой записи показывает плашку вместо формы', async () => {
  server.use(
    http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false }))),
    http.get('/api/illnesses', () => HttpResponse.json([])),
  )
  renderApp('/illness/new')
  expect(await screen.findByTestId('illness-locked')).toBeInTheDocument()
  expect(screen.queryByRole('grid')).not.toBeInTheDocument()
})
