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

it('владелец видит одноразовую ссылку со сроком и может выпустить новую (R04)', async () => {
  mockFamily(family())
  server.use(http.post('/api/families/7/invite', () => HttpResponse.json(family({ invite_code: 'NEWCODE9' }))))
  const { user } = renderApp('/family')
  expect(await screen.findByText(/\/join\/ABCD2345$/)).toBeInTheDocument()
  expect(screen.getByText(/Ссылка-приглашение · действует до/)).toBeInTheDocument()
  expect(screen.getByText(/сработает один раз и действует 24 часа/)).toBeInTheDocument()
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
