import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import type { Intake, MedicineDetail } from '../api'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

const location = () => screen.getByTestId('location').textContent

function intake(over: Partial<Intake> = {}): Intake {
  const now = new Date().toISOString()
  return {
    id: 1, medicine_id: 1, medicine_name: 'Нурофен', unit: 'таб', user_id: 1, user_name: 'Никита', mine: true,
    amount: 1, comment: '', taken_at: now, last_at: now, ...over,
  }
}

function detail(): MedicineDetail {
  return { ...medicine(), packages: [] }
}

it('общая история: по дням, фильтры и дописать комментарий к своей записи', async () => {
  const yesterday = new Date(Date.now() - 86_400_000).toISOString()
  const asked: string[] = []
  const patched: unknown[] = []
  server.use(
    http.get('/api/families/7/intakes', ({ request }) => {
      asked.push(new URL(request.url).search)
      return HttpResponse.json([
        intake({ id: 3, amount: 3, comment: 'болела голова' }),
        intake({ id: 2, user_id: 2, user_name: 'Мама', mine: false, medicine_id: null, medicine_name: 'Смекта', unit: 'пак', taken_at: yesterday }),
      ])
    }),
    http.patch('/api/families/7/intakes/2', () => HttpResponse.json({}, { status: 403 })),
    http.patch('/api/families/7/intakes/3', async ({ request }) => {
      patched.push(await request.json())
      return HttpResponse.json(intake({ id: 3, amount: 3, comment: 'ещё раз' }))
    }),
  )
  const { user } = renderApp('/history')
  expect(await screen.findByText('Сегодня')).toBeInTheDocument()
  expect(screen.getByText('Вчера')).toBeInTheDocument()
  expect(screen.getByText('3 таб')).toBeInTheDocument()
  expect(screen.getByText('болела голова')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Нурофен' })).toHaveAttribute('href', '/medicines/1')
  expect(screen.queryByRole('link', { name: 'Смекта' })).toBeNull()  // удалённое лекарство — без ссылки
  expect(screen.getByText('Мама')).toBeInTheDocument()
  // у чужой записи нет кнопки комментария, у своей — одна
  expect(screen.getAllByRole('button', { name: /комментарий/ })).toHaveLength(1)

  await user.click(screen.getByRole('button', { name: 'Изменить комментарий' }))
  const dialog = screen.getByRole('dialog')
  await user.clear(within(dialog).getByRole('textbox'))
  await user.type(within(dialog).getByRole('textbox'), 'ещё раз')
  await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
  expect(await screen.findByText('Комментарий сохранён')).toBeInTheDocument()
  expect(patched).toEqual([{ comment: 'ещё раз' }])

  await user.click(screen.getByRole('button', { name: 'Только мои' }))
  expect(location()).toBe('/history?mine=1')
  expect(asked.at(-1)).toContain('mine=true')
})

it('на странице лекарства «Принял» — одно нажатие, комментарий — по отдельной кнопке', async () => {
  const bodies: unknown[] = []
  server.use(
    http.get('/api/families/7/medicines/1', () => HttpResponse.json(detail())),
    http.get('/api/families/7/intakes', () => HttpResponse.json([])),
    http.post('/api/families/7/medicines/1/consume', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json(detail())
    }),
  )
  const { user } = renderApp('/medicines/1')
  expect(await screen.findByText('Здесь появится, кто и когда принимал это лекарство.')).toBeInTheDocument()
  expect(screen.queryByText('Напомнить при')).toBeNull()

  await user.click(screen.getByRole('button', { name: 'Принял(а) 1 таб' }))
  expect(await screen.findByText(/Списано 1 таб/)).toBeInTheDocument()
  expect(screen.queryByRole('dialog')).toBeNull()  // без вопросов про комментарий

  await user.click(screen.getByRole('button', { name: 'Принять с комментарием' }))
  await user.type(within(screen.getByRole('dialog')).getByRole('textbox'), '  после тренировки ')
  await user.click(screen.getByRole('button', { name: 'Принял(а) и сохранить' }))
  await screen.findByText(/Списано 1 таб/)
  expect(bodies).toEqual([{ amount: 1, comment: '' }, { amount: 1, comment: 'после тренировки' }])
  expect(screen.queryByRole('dialog')).toBeNull()
})

it('в меню «История приёма» вместо «Экспорт», а экспорт — кнопкой в аптечке', async () => {
  server.use(
    http.get('/api/families/7/intakes', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json([])),
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
  )
  const { user } = renderApp('/medicines')
  const nav = await screen.findByRole('navigation', { name: 'Навигация' })
  expect(within(nav).getByRole('link', { name: 'История приёма' })).toHaveAttribute('href', '/history')
  expect(within(nav).getByText('История')).toBeInTheDocument()  // на телефоне короткая подпись
  expect(within(nav).queryByRole('link', { name: 'Экспорт' })).toBeNull()
  await user.click(await screen.findByRole('link', { name: 'Экспорт' }))
  expect(location()).toBe('/export')
})
