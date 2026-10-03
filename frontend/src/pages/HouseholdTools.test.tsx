import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, expect, it, vi } from 'vitest'
import { planFixture, server } from '../test/server'
import { ME, medicine, renderApp } from '../test/utils'

const saved = vi.hoisted(() => ({ names: [] as string[] }))
vi.mock('../files', async orig => ({
  ...(await orig<typeof import('../files')>()),
  saveFile: (f: File) => { saved.names.push(f.name) },
}))

const TWO = {
  ...ME,
  families: [
    { id: 7, name: 'Семья Никита', role: 'owner' as const, status: 'active' as const },
    { id: 8, name: 'Дача', role: 'owner' as const, status: 'active' as const },
  ],
}
const meds = [medicine({ id: 1, name: 'Нурофен' }), medicine({ id: 2, name: 'Аспирин' })]

beforeEach(() => { saved.names = [] })

it('перенос: отмечаем лекарства, выбираем аптечку, выбор уходит на сервер (R17)', async () => {
  let body: Record<string, unknown> | undefined
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json(meds)),
    http.post('/api/families/7/medicines/move', async ({ request }) => {
      body = await request.json() as Record<string, unknown>
      return HttpResponse.json({ moved: 1, merged: 1, to_family_id: 8 })
    }),
  )
  const { user } = renderApp('/medicines', { me: TWO })
  await user.click(await screen.findByRole('button', { name: 'Выбрать' }))
  expect(screen.getByRole('button', { name: /Перенести/ })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: 'Выбрать Аспирин' }))
  await user.click(screen.getByRole('button', { name: /Перенести/ }))
  const sheet = await screen.findByRole('dialog', { name: 'Перенести в другую аптечку' })
  expect(within(sheet).getByRole('option', { name: 'Дача' })).toBeInTheDocument()
  expect(within(sheet).queryByRole('option', { name: 'Семья Никита' })).not.toBeInTheDocument()
  await user.click(within(sheet).getByRole('button', { name: 'Перенести' }))
  await waitFor(() => expect(body).toEqual({ to_family_id: 8, medicine_ids: [2] }))
  expect(await screen.findByText(/слито с такими же: 1/)).toBeInTheDocument()
  await waitFor(() => expect(screen.queryByRole('toolbar')).not.toBeInTheDocument())
})

it('замороженную аптечку в списке «куда перенести» не предлагаем', async () => {
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json(meds)),
  )
  const me = { ...TWO, families: [TWO.families[0], { ...TWO.families[1], status: 'frozen' as const }] }
  const { user } = renderApp('/medicines', { me })
  await user.click(await screen.findByRole('button', { name: 'Выбрать' }))
  await user.click(screen.getByRole('checkbox', { name: 'Выбрать Нурофен' }))
  await user.click(screen.getByRole('button', { name: /Перенести/ }))
  const sheet = await screen.findByRole('dialog', { name: 'Перенести в другую аптечку' })
  expect(within(sheet).getByRole('note')).toHaveTextContent('Других активных аптечек в семье нет')
  expect(within(sheet).getByRole('button', { name: 'Перенести' })).toBeDisabled()
})

it('разделение: выбранное уходит в новую аптечку с названием (R18)', async () => {
  let body: Record<string, unknown> | undefined
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json(meds)),
    http.post('/api/families/7/split', async ({ request }) => {
      body = await request.json() as Record<string, unknown>
      return HttpResponse.json({ moved: 2, merged: 0, to_family_id: 9 }, { status: 201 })
    }),
  )
  const { user } = renderApp('/medicines', { me: ME })
  await user.click(await screen.findByRole('button', { name: 'Выбрать' }))
  await user.click(screen.getByRole('button', { name: 'Выбрать все' }))
  // Одна аптечка: переносить некуда, остаётся разделение.
  expect(screen.queryByRole('button', { name: /^Перенести/ })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /В новую аптечку/ }))
  const sheet = await screen.findByRole('dialog', { name: 'Новая аптечка из выбранного' })
  await user.type(within(sheet).getByLabelText('Название новой аптечки'), 'Дача')
  await user.click(within(sheet).getByRole('button', { name: 'Создать и перенести' }))
  await waitFor(() => expect(body).toEqual({ name: 'Дача', medicine_ids: [1, 2] }))
  expect(await screen.findByText(/Новая аптечка «Дача»: 2 лекарства/)).toBeInTheDocument()
})

it('поиск по всем аптечкам: в бесплатной семье открывает шторку Плюса, запрос не уходит', async () => {
  let asked = 0
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', ({ request }) => {
      if (new URL(request.url).searchParams.get('scope') === 'all') asked++
      return HttpResponse.json(meds)
    }),
    http.get('/api/families/:id/plan', () => HttpResponse.json(planFixture({
      has_plus: false, plus_active: false, billing_enabled: true,
      features: planFixture().features.map(f => ({ ...f, available: false })),
    }))),
  )
  const { user } = renderApp('/medicines', { me: TWO })
  await screen.findByText('Нурофен')
  await user.click(await screen.findByRole('button', { name: 'Все аптечки' }))
  expect(await screen.findByRole('dialog', { name: 'Доступно в Капсулке Плюс' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Все аптечки' })).toHaveAttribute('aria-pressed', 'false')
  expect(asked).toBe(0)
})

it('поиск по всем аптечкам с Плюсом: запрос scope=all, на карточке название аптечки, по клику открывается она', async () => {
  const scopes: (string | null)[] = []
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', ({ request }) => {
      const scope = new URL(request.url).searchParams.get('scope')
      scopes.push(scope)
      return HttpResponse.json(scope === 'all'
        ? [medicine({ id: 5, name: 'Цитрамон', family_id: 8, family_name: 'Дача' })]
        : meds)
    }),
    http.get('/api/families/8/medicines/5', () => HttpResponse.json({ ...medicine({ id: 5, name: 'Цитрамон' }), packages: [], schedule: [], members_helped: [] })),
    http.get('/api/families/8/categories', () => HttpResponse.json([])),
    http.get('/api/families/8/intakes', () => HttpResponse.json([])),
  )
  const { user } = renderApp('/medicines', { me: TWO })
  await screen.findByText('Нурофен')
  await user.click(screen.getByRole('button', { name: 'Все аптечки' }))
  expect(await screen.findByText('Цитрамон')).toBeInTheDocument()
  expect(scopes).toContain('all')
  expect(screen.getByText('Дача', { selector: '.badge' })).toBeInTheDocument()
  // В режиме «все аптечки» перенос и разделение скрыты: у карточек разные аптечки.
  expect(screen.queryByRole('button', { name: 'Выбрать' })).not.toBeInTheDocument()
  await user.click(screen.getByText('Цитрамон'))
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/medicines/5'))
})

it('выгрузка: .csv и .json скачиваются файлом с сервера (R25)', async () => {
  const urls: string[] = []
  server.use(
    http.get('/api/families/7/export.txt', () => new HttpResponse('Нурофен\n', { headers: { 'Content-Type': 'text/plain' } })),
    http.get('/api/families/7/export.:fmt', ({ request, params }) => {
      urls.push(new URL(request.url).pathname)
      return new HttpResponse('x', {
        headers: { 'Content-Type': 'text/plain', 'Content-Disposition': `attachment; filename="kapsulka-aptechka-2026-10-04.${params.fmt}"` },
      })
    }),
  )
  const { user } = renderApp('/export')
  await user.click(await screen.findByRole('button', { name: /Таблица \.csv/ }))
  await waitFor(() => expect(saved.names).toEqual(['kapsulka-aptechka-2026-10-04.csv']))
  await user.click(screen.getByRole('button', { name: /Все данные \.json/ }))
  await waitFor(() => expect(saved.names).toHaveLength(2))
  expect(urls).toEqual(['/api/families/7/export.csv', '/api/families/7/export.json'])
})

const carryMessage = 'У вашей семьи оплачен Плюс до 20 ноября. Вступить можно, только перенеся оставшиеся оплаченные дни в эту семью.'

it('вступление с оплаченным Плюсом: сервер просит решение, «Перенести дни» повторяет запрос с carry_plus (R08)', async () => {
  const bodies: Record<string, unknown>[] = []
  server.use(
    http.get('/api/families/7/overview', () => HttpResponse.json({ total_medicines: 0, total_packages: 0, expired: [], expiring: [], low: [], favorites: [], helps_me: [], expiring_soon_days: 30 })),
    http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', owner_name: 'Анна', full: false })),
    http.post('/api/families/join', async ({ request }) => {
      const b = await request.json() as Record<string, unknown>
      bodies.push(b)
      return b.carry_plus
        ? HttpResponse.json({ id: 9, name: 'Зимины', invite_code: null, role: 'member', members: [] })
        : HttpResponse.json({ detail: carryMessage }, { status: 409 })
    }),
  )
  const { user } = renderApp('/join/ABCD2345')
  await user.click(await screen.findByRole('button', { name: /Вступить как/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('У вашей семьи оплачен Плюс')
  await user.click(screen.getByRole('button', { name: 'Перенести дни и вступить' }))
  await waitFor(() => expect(bodies).toEqual([{ code: 'ABCD2345' }, { code: 'ABCD2345', carry_plus: true }]))
})

it('другая ошибка вступления: кнопки переноса дней нет', async () => {
  server.use(
    http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', owner_name: 'Анна', full: false })),
    http.post('/api/families/join', () => HttpResponse.json({ detail: 'В семье уже 3 человека.' }, { status: 409 })),
  )
  const { user } = renderApp('/join/ABCD2345')
  await user.click(await screen.findByRole('button', { name: /Вступить как/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('В семье уже 3 человека.')
  expect(screen.queryByRole('button', { name: 'Перенести дни и вступить' })).not.toBeInTheDocument()
})

it('кулдаун смены семьи: дату видно заранее, а после срока заметки нет (R11)', async () => {
  const future = new Date(Date.now() + 10 * 86400_000).toISOString()
  server.use(http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', owner_name: 'Анна', full: false })))
  const first = renderApp('/join/ABCD2345', { me: { ...ME, next_change_at: future } })
  expect(await screen.findByRole('note')).toHaveTextContent(/Сменить семью можно раз в 30 дней: следующий раз с .* \(по московскому времени\)\. Если нужно срочно, напишите нам\./)
  first.unmount()

  renderApp('/join/ABCD2345', { me: { ...ME, next_change_at: new Date(Date.now() - 86400_000).toISOString() } })
  await screen.findByRole('button', { name: /Вступить как/ })
  expect(screen.queryByRole('note')).not.toBeInTheDocument()
})

it('админ снимает кулдаун смены семьи у человека', async () => {
  let called = false
  server.use(
    http.get('/api/admin/stats', () => HttpResponse.json({ users: 2, admins: 1, families: 1, medicines: 0, categories: 0 })),
    http.get('/api/admin/users', () => HttpResponse.json([
      { id: 2, email: 'mom@example.com', name: 'Мама', is_admin: false, email_verified: true, created_at: '2026-09-26T10:00:00Z', families: [], plan: 'free', plus_until: null, plus_active: false },
    ])),
    http.post('/api/admin/users/2/reset-cooldown', () => { called = true; return new HttpResponse(null, { status: 204 }) }),
  )
  window.confirm = () => true
  const { user } = renderApp('/admin?tab=users', { me: { ...ME, is_admin: true } })
  await user.click(await screen.findByRole('button', { name: /Мама/ }))
  await user.click(await screen.findByRole('button', { name: 'Снять кулдаун смены семьи' }))
  await waitFor(() => expect(called).toBe(true))
  expect(await screen.findByText('Мама может сменить семью сразу')).toBeInTheDocument()
})

