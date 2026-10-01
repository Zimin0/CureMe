import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import type { Occurrence, Schedule as ScheduleT } from '../api'
import { planFixture, server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

// Фиксируем «сейчас» — среда 7 октября 2026, 12:00 по Москве, чтобы статусы приёмов не зависели от времени запуска.
beforeAll(() => { vi.useFakeTimers({ toFake: ['Date'] }); vi.setSystemTime(new Date('2026-10-07T09:00:00Z')) })
afterAll(() => vi.useRealTimers())
const today = '2026-10-07'
const slots = (days: number[], times: number[]) => days.flatMap((weekday, i) => times.map((minute, j) => ({ id: i * 10 + j + 1, weekday, minute })))
const schedule = (over: Partial<ScheduleT> = {}): ScheduleT => ({
  id: 5, medicine_id: 1, medicine_name: 'Амепрозол', unit: 'таб', amount: 1, start_date: '2026-10-05', end_date: null, every_weeks: 1,
  slots: slots([1, 2], [480, 960]), ...over,
})
const occurrence = (over: Partial<Occurrence> = {}): Occurrence => ({
  schedule_id: 5, slot_id: 1, medicine_id: 1, medicine_name: 'Амепрозол', unit: 'таб', amount: 1, date: today, minute: 0,
  taken: false, taken_at: null, ...over,
})

it('пустое расписание зовёт добавить лекарство', async () => {
  server.use(
    http.get('/api/families/7/schedule', () => HttpResponse.json([])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([])),
  )
  renderApp('/schedule')
  expect(await screen.findByText('Расписание пока пустое')).toBeInTheDocument()
})

it('показывает приёмы дня и отмечает «Принял(а)» через обычное списание', async () => {
  const consumed: unknown[] = []
  server.use(
    http.get('/api/families/7/schedule', () => HttpResponse.json([schedule()])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([
      occurrence({ slot_id: 1, minute: 0 }),                       // давно прошло: пропущено
      occurrence({ slot_id: 2, minute: 23 * 60 + 59, amount: 2 }), // впереди
    ])),
    http.post('/api/families/7/medicines/1/consume', async ({ request }) => { consumed.push(await request.json()); return HttpResponse.json({}) }),
  )
  const { user } = renderApp('/schedule')
  const doses = await screen.findAllByTestId('dose')
  expect(doses).toHaveLength(2)
  expect(within(doses[0]).getByText('Пропущено')).toBeInTheDocument()
  expect(within(doses[0]).getByText('00:00')).toBeInTheDocument()
  await user.click(within(doses[0]).getByRole('button', { name: /Принял/ }))
  await waitFor(() => expect(consumed).toEqual([{ amount: 1 }]))
  expect(within(doses[1]).getByText('Впереди')).toBeInTheDocument()
  expect(within(doses[1]).queryByRole('button', { name: /Принял/ })).toBeNull()  // до приёма далеко: отметить пока нельзя
})

it('убирает серию: «больше не пью по вторникам в 16:00»', async () => {
  const removed: unknown[] = []
  server.use(
    http.get('/api/families/7/schedule', () => HttpResponse.json([schedule()])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([])),
    http.post('/api/families/7/schedule/5/remove', async ({ request }) => { removed.push(await request.json()); return HttpResponse.json(schedule()) }),
  )
  const { user } = renderApp('/schedule')
  await user.click(await screen.findByRole('button', { name: 'Убрать приёмы' }))
  const sheet = await screen.findByRole('dialog')
  const remove = within(sheet).getByRole('button', { name: 'Убрать эти приёмы' })
  expect(remove).toBeDisabled()  // пока ничего не выбрано
  await user.click(within(sheet).getByRole('button', { name: 'Вт' }))
  await user.click(within(sheet).getByRole('button', { name: '16:00' }))
  expect(within(sheet).getByText(/Амепрозол: Вт, 16:00/)).toBeInTheDocument()
  await user.click(remove)
  await waitFor(() => expect(removed).toEqual([{ days: [1], times: [960] }]))
})

it('добавляет назначение: лекарство, дни-пресет, время-пресет', async () => {
  const created: unknown[] = []
  server.use(
    http.get('/api/families/7/schedule', () => HttpResponse.json([])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json([medicine({ id: 1, name: 'Амепрозол', unit: 'таб' })])),
    http.post('/api/families/7/schedule', async ({ request }) => { created.push(await request.json()); return HttpResponse.json(schedule(), { status: 201 }) }),
  )
  const { user } = renderApp('/schedule')
  await user.click((await screen.findAllByRole('button', { name: /Добавить/ }))[0])
  const sheet = await screen.findByRole('dialog')
  const add = within(sheet).getByRole('button', { name: 'Добавить в расписание' })
  expect(add).toBeDisabled()
  await user.click(await within(sheet).findByRole('radio', { name: 'Амепрозол' }))
  await user.click(within(sheet).getByRole('button', { name: 'Будни' }))
  await user.click(within(sheet).getByRole('button', { name: /Утро/ }))
  await user.click(within(sheet).getByRole('button', { name: /На ночь/ }))
  await user.click(add)
  await waitFor(() => expect(created).toEqual([{
    medicine_id: 1, amount: 1, days: [0, 1, 2, 3, 4], times: [480, 1320], every_weeks: 1, end_date: null,
  }]))
})

it('неделя: нажатие на плашку открывает перенос приёма', async () => {
  const moved: unknown[] = []
  server.use(
    http.get('/api/families/7/schedule', () => HttpResponse.json([schedule()])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([])),
    http.patch('/api/families/7/schedule/5/slots/12', async ({ request }) => { moved.push(await request.json()); return HttpResponse.json(schedule()) }),
  )
  const { user } = renderApp('/schedule')
  await user.click(await screen.findByRole('button', { name: 'Амепрозол 16:00, Ср' }))
  const sheet = await screen.findByRole('dialog')
  await user.click(within(sheet).getByRole('radio', { name: 'Чт' }))
  await user.click(within(sheet).getByRole('button', { name: 'Перенести' }))
  await waitFor(() => expect(moved).toEqual([{ weekday: 3, minute: 960 }]))
})

it('без Плюса форма «Добавить в расписание» закрыта плашкой и недоступна', async () => {
  server.use(
    http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false }))),
    http.get('/api/families/7/schedule', () => HttpResponse.json([])),
    http.get('/api/families/7/schedule/occurrences', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json([medicine({ id: 1, name: 'Амепрозол' })])),
  )
  const { user } = renderApp('/schedule')
  await user.click((await screen.findAllByRole('button', { name: /Добавить/ }))[0])
  expect(await screen.findByTestId('plus-banner')).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Добавить в расписание' }).at(-1)).toBeDisabled()
  expect(screen.getByRole('group', { name: 'Повтор' }).closest('fieldset')).toBeDisabled()
})
