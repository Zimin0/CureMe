import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import type { PlusEnding } from '../api'
import { server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const joined = ['2026-09-26T10:00:00Z', '2026-09-27T10:00:00Z', '2026-09-28T10:00:00Z', '2026-09-29T10:00:00Z']
const members = [
  { user_id: 1, name: 'Никита', email: 'nikita@example.com', role: 'owner', joined_at: joined[0] },
  { user_id: 2, name: 'Мама', email: 'mom@example.com', role: 'member', joined_at: joined[1] },
  { user_id: 3, name: 'Папа', email: 'dad@example.com', role: 'member', joined_at: joined[2] },
  { user_id: 4, name: 'Брат', email: 'bro@example.com', role: 'member', joined_at: joined[3] },
]
const ended = (over: Partial<PlusEnding> = {}): PlusEnding => ({ state: 'ended', date: '2026-10-20T12:00:00Z', is_owner: true, people_limit: 3, ...over })

function mockFamily() {
  server.use(
    http.get('/api/families/:id', () => HttpResponse.json({ id: 7, name: 'Семья Никита', invite_code: null, role: 'owner', members })),
    http.get('/api/families/:id/categories', () => HttpResponse.json([])),
    http.get('/api/families/:id/medicines', () => HttpResponse.json([])),
  )
}

it('баннер: владелец видит ссылку на выбор состава, участник только «Решает владелец семьи»', async () => {
  mockFamily()
  const owner = renderApp('/family', { me: { ...ME, plus_ending: ended() } })
  const banner = await screen.findByRole('status', { name: 'Плюс семьи заканчивается' })
  expect(banner).toHaveTextContent(/Плюс семьи закончился/)
  expect(banner).toHaveTextContent(/не больше 3 человек/)
  expect(within(banner).getByRole('link', { name: 'Выбрать состав' })).toBeInTheDocument()
  expect(within(banner).getByRole('link', { name: 'Продлить Плюс' })).toBeInTheDocument()
  owner.unmount()

  renderApp('/family', { me: { ...ME, families: [{ id: 7, name: 'Семья Никита', role: 'member' }], plus_ending: ended({ is_owner: false }) } })
  const note = await screen.findByRole('status', { name: 'Плюс семьи заканчивается' })
  expect(note).toHaveTextContent('Решает владелец семьи')
  expect(within(note).queryByRole('link')).not.toBeInTheDocument()
})

it('баннер за три дня до конца: Плюс заканчивается, но выбор пока не нужен', async () => {
  mockFamily()
  renderApp('/family', { me: { ...ME, plus_ending: ended({ state: 'ending' }) } })
  const banner = await screen.findByRole('status', { name: 'Плюс семьи заканчивается' })
  expect(banner).toHaveTextContent(/Плюс семьи заканчивается/)
  expect(within(banner).queryByRole('link', { name: 'Выбрать состав' })).not.toBeInTheDocument()
  expect(within(banner).getByRole('link', { name: 'Продлить Плюс' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Выбрать состав' })).not.toBeInTheDocument()
})

it('без окончания Плюса баннера и выбора состава нет', async () => {
  mockFamily()
  renderApp('/family')
  await screen.findByText('Участники')
  expect(screen.queryByRole('status', { name: 'Плюс семьи заканчивается' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Выбрать состав' })).not.toBeInTheDocument()
})

it('владелец выбирает состав: по умолчанию отмечены самые давние, выбор уходит на сервер (R13)', async () => {
  mockFamily()
  let body: Record<string, unknown> | undefined
  server.use(http.post('/api/families/7/compress', async ({ request }) => {
    body = await request.json() as Record<string, unknown>
    return HttpResponse.json({ id: 7, name: 'Семья Никита', invite_code: null, role: 'owner', members })
  }))
  const { user } = renderApp('/family', { me: { ...ME, plus_ending: ended() } })
  window.confirm = () => true
  await user.click(await screen.findByRole('button', { name: 'Выбрать состав' }))
  const sheet = await screen.findByRole('dialog', { name: 'Кто остаётся в семье' })
  expect(within(sheet).getByText('Люди: 3 из 3')).toBeInTheDocument()
  expect(within(sheet).getByRole('checkbox', { name: /Никита \(владелец\)/ })).toBeDisabled()
  expect(within(sheet).getByRole('checkbox', { name: 'Мама' })).toBeChecked()
  expect(within(sheet).getByRole('checkbox', { name: 'Папа' })).toBeChecked()
  expect(within(sheet).getByRole('checkbox', { name: 'Брат' })).not.toBeChecked()

  // Лишний человек не проходит: кнопка закрыта и сказано почему.
  await user.click(within(sheet).getByRole('checkbox', { name: 'Брат' }))
  expect(within(sheet).getByRole('alert')).toHaveTextContent('не больше 3 человек')
  expect(within(sheet).getByRole('button', { name: 'Сохранить выбор' })).toBeDisabled()

  // Вместо Папы остаётся Брат.
  await user.click(within(sheet).getByRole('checkbox', { name: 'Папа' }))
  await user.click(within(sheet).getByRole('button', { name: 'Сохранить выбор' }))
  await waitFor(() => expect(body).toEqual({ keep_user_ids: [2, 4], keep_cabinet_ids: [] }))
  await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Кто остаётся в семье' })).not.toBeInTheDocument())
})

it('аптечек в выборе не больше, чем остаётся людей', async () => {
  mockFamily()
  const me = {
    ...ME, plus_ending: ended({ people_limit: 2 }),
    families: [7, 8, 9].map(id => ({ id, name: `Аптечка ${id}`, role: 'owner' as const })),
  }
  const { user } = renderApp('/family', { me })
  await user.click(await screen.findByRole('button', { name: 'Выбрать состав' }))
  const sheet = await screen.findByRole('dialog', { name: 'Кто остаётся в семье' })
  expect(within(sheet).getByText('Активные аптечки: 0 из 2')).toBeInTheDocument()
  await user.click(within(sheet).getByRole('checkbox', { name: 'Аптечка 7' }))
  await user.click(within(sheet).getByRole('checkbox', { name: 'Аптечка 8' }))
  await user.click(within(sheet).getByRole('checkbox', { name: 'Аптечка 9' }))
  expect(within(sheet).getByRole('alert')).toHaveTextContent('не больше 2')
  expect(within(sheet).getByRole('button', { name: 'Сохранить выбор' })).toBeDisabled()
})

it('замороженная аптечка: предупреждение на странице, метка в списке и «Разморозить» у владельца (R14)', async () => {
  mockFamily()
  let me = { ...ME, families: [{ id: 7, name: 'Семья Никита', role: 'owner' as const, status: 'active' as const }, { id: 8, name: 'Дача', role: 'owner' as const, status: 'frozen' as const }] }
  let unfroze = false
  const { user } = renderApp('/family', { me })
  // После разморозки список перечитывают: отвечаем актуальным (обработчик после renderApp главнее его собственного).
  server.use(
    http.get('/api/auth/me', () => HttpResponse.json(me)),
    http.post('/api/families/8/unfreeze', () => {
      unfroze = true
      me = { ...me, families: me.families.map(f => ({ ...f, status: 'active' as const })) }
      return HttpResponse.json({ id: 8, name: 'Дача', invite_code: null, role: 'owner', members })
    }),
  )
  await screen.findByText('Мои аптечки')
  // Открыта активная аптечка: предупреждения нет, замороженная помечена.
  expect(screen.queryByRole('status', { name: 'Аптечка заморожена' })).not.toBeInTheDocument()
  expect(screen.getByText('заморожена')).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'Дача (заморожена)' })).toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: /Дача/ }))
  expect(await screen.findByRole('status', { name: 'Аптечка заморожена' })).toHaveTextContent(/можно смотреть и выгружать, но не менять/)

  await user.click(screen.getByRole('button', { name: 'Разморозить' }))
  await waitFor(() => expect(unfroze).toBe(true))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Разморозить' })).not.toBeInTheDocument())
  expect(screen.queryByRole('status', { name: 'Аптечка заморожена' })).not.toBeInTheDocument()
})

it('участнику «Разморозить» не показываем: размораживает владелец', async () => {
  mockFamily()
  const me = {
    ...ME, families: [{ id: 7, name: 'Семья Никита', role: 'owner' as const }, { id: 8, name: 'Дача', role: 'member' as const, status: 'frozen' as const }],
  }
  renderApp('/family', { me })
  await screen.findByText('Мои аптечки')
  expect(screen.getByText('заморожена')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Разморозить' })).not.toBeInTheDocument()
})
