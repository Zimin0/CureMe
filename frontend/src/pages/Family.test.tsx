import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const members = [
  { user_id: 1, name: 'Никита', email: 'nikita@example.com', role: 'owner', is_owner: true, joined_at: '2026-09-26T10:00:00Z' },
  { user_id: 2, name: 'Мама', email: 'mom@example.com', role: 'member', is_owner: false, joined_at: '2026-09-27T10:00:00Z' },
]
const family = (over: Record<string, unknown> = {}) => ({
  id: 7, name: 'Семья Никита', invite_code: 'ABCD2345', invite_expires_at: '2026-10-04T12:30:00Z', role: 'owner', members, ...over,
})

function mockFamily(body: ReturnType<typeof family>) {
  server.use(
    http.get('/api/families/:id', () => HttpResponse.json(body)),
    http.get('/api/families/:id/categories', () => HttpResponse.json([])),
    http.get('/api/families/:id/medicines', () => HttpResponse.json([])),
  )
}

it('владелец видит одноразовую ссылку без подписи и может выпустить новую (R04)', async () => {
  mockFamily(family())
  server.use(http.post('/api/families/7/invite', () => HttpResponse.json(family({ invite_code: 'NEWCODE9' }))))
  const { user } = renderApp('/family')
  expect(await screen.findByText(/\/join\/ABCD2345$/)).toBeInTheDocument()
  expect(screen.queryByText(/Ссылка-приглашение/)).not.toBeInTheDocument()
  expect(screen.getByText(/Она одноразовая и будет действовать 24 часа/)).toBeInTheDocument()
  window.confirm = () => true
  await user.click(screen.getByTitle('Создать новую ссылку'))
  expect(await screen.findByText(/\/join\/NEWCODE9$/)).toBeInTheDocument()
})

it('если действующей ссылки нет, владелец создаёт приглашение кнопкой', async () => {
  mockFamily(family({ invite_code: null, invite_expires_at: null }))
  server.use(http.post('/api/families/7/invite', () => HttpResponse.json(family({ invite_code: 'FRESH234' }))))
  const { user } = renderApp('/family')
  await user.click(await screen.findByRole('button', { name: 'Создать приглашение' }))
  expect(await screen.findByText(/\/join\/FRESH234$/)).toBeInTheDocument()
})

it('участник не видит ссылку и кнопок приглашения: приглашает владелец', async () => {
  mockFamily(family({ role: 'member', invite_code: null, invite_expires_at: null }))
  renderApp('/family', { me: { ...ME, families: [{ id: 7, name: 'Семья Никита', role: 'member' }] } })
  expect(await screen.findByText(/Приглашает владелец семьи \(Никита\)/)).toBeInTheDocument()
  expect(screen.queryByText(/\/join\//)).not.toBeInTheDocument()
  expect(screen.queryByTitle('Создать новую ссылку')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Создать приглашение' })).not.toBeInTheDocument()
})

// --- передача владения с согласием (R23) ---
const offerOf = (over: Record<string, unknown> = {}) => ({
  kind: 'offer', from_user_id: 1, from_name: 'Никита', to_user_id: 2, to_name: 'Мама',
  expires_at: '2026-10-05T12:30:00Z', can_answer: false, can_withdraw: false, ...over,
})
const asMember = { me: { ...ME, id: 2, name: 'Мама', families: [{ id: 7, name: 'Семья Никита', role: 'member' as const }] } }

it('владелец предлагает владение: кнопка шлёт предложение, а не меняет роль сразу', async () => {
  mockFamily(family())
  let body: unknown = null
  server.use(http.post('/api/families/7/owner-transfer', async ({ request }) => {
    body = await request.json()
    return HttpResponse.json(family({ owner_transfer: offerOf({ can_withdraw: true }) }), { status: 201 })
  }))
  window.confirm = () => true
  const { user } = renderApp('/family')
  await user.click(await screen.findByTitle('Предложить владение'))
  expect(await screen.findByText(/Вы предложили Мама стать владельцем семьи/)).toBeInTheDocument()
  expect(body).toEqual({ user_id: 2 })
  expect(screen.getByRole('button', { name: 'Отменить предложение' })).toBeInTheDocument()
  expect(screen.getByTitle('Уже есть неотвеченное предложение')).toBeDisabled()
})

it('кому предложили, тот видит предложение и может принять или отказаться', async () => {
  mockFamily(family({ role: 'member', invite_code: null, owner_transfer: offerOf({ can_answer: true }) }))
  let accepted = false
  server.use(http.post('/api/families/7/owner-transfer/accept', () => {
    accepted = true
    return HttpResponse.json(family({ role: 'owner', owner_transfer: null }))
  }))
  const { user } = renderApp('/family', asMember)
  expect(await screen.findByText(/Никита предлагает вам стать владельцем семьи/)).toBeInTheDocument()
  expect(screen.getByText(/Ответить можно до/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Отказаться' })).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Принять' }))
  await screen.findByText('Готово, владелец семьи сменился')
  expect(accepted).toBe(true)
})

it('участник просит «Хочу оплачивать», владелец подтверждает или отклоняет', async () => {
  mockFamily(family({ role: 'member', invite_code: null }))
  server.use(http.post('/api/families/7/owner-request', () => HttpResponse.json(family({
    role: 'member', invite_code: null, owner_transfer: offerOf({ kind: 'request', from_user_id: 2, from_name: 'Мама', to_user_id: 1, to_name: 'Никита', can_withdraw: true }),
  }), { status: 201 })))
  window.confirm = () => true
  const { user } = renderApp('/family', asMember)
  await user.click(await screen.findByRole('button', { name: 'Хочу оплачивать' }))
  expect(await screen.findByText(/Вы попросили владельца \(Никита\)/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Забрать просьбу' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Хочу оплачивать' })).not.toBeInTheDocument()
})

it('владелец видит просьбу участника с кнопками «Подтвердить» и «Отклонить»', async () => {
  mockFamily(family({ owner_transfer: offerOf({ kind: 'request', from_user_id: 2, from_name: 'Мама', to_user_id: 1, to_name: 'Никита', can_answer: true }) }))
  renderApp('/family')
  expect(await screen.findByText(/Мама хочет стать владельцем семьи и оплачивать Плюс/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Отклонить' })).toBeInTheDocument()
})

it('после недавней передачи кнопки передачи выключены до конца недели', async () => {
  const soon = new Date(Date.now() + 3 * 86400_000).toISOString()
  mockFamily(family({ next_transfer_at: soon }))
  renderApp('/family')
  expect(await screen.findByTitle(/Владение менялось недавно: передать можно с/)).toBeDisabled()
})

it('владелец не видит кнопку «Хочу оплачивать»', async () => {
  mockFamily(family())
  renderApp('/family')
  await screen.findByText('Участники')
  expect(screen.queryByRole('button', { name: 'Хочу оплачивать' })).not.toBeInTheDocument()
})

it('в шапке приложения висит напоминание, если человеку нужно ответить по владению', async () => {
  mockFamily(family({ role: 'member', invite_code: null, owner_transfer: offerOf({ can_answer: true }) }))
  renderApp('/family', { me: { ...asMember.me, owner_transfer_waiting: true } })
  expect(await screen.findByText(/Вам нужно ответить на предложение о владении семьёй/)).toBeInTheDocument()
})
