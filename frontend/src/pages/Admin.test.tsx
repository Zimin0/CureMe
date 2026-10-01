import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { Category } from '../api'
import { server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const ADMIN = { ...ME, is_admin: true }
const CATS: Category[] = [
  { id: 1, name: 'Обезболивающие', icon: '🩹', color: '#e5484d', medicine_count: 3 },
  { id: 2, name: 'Жаропонижающие', icon: '🌡️', color: '#f76b15', medicine_count: 0 },
  { id: 3, name: 'Витамины', icon: '🍊', color: '#f5a623', medicine_count: 1 },
]
const stats = http.get('/api/admin/stats', () => HttpResponse.json({ users: 5, admins: 1, families: 3, medicines: 40, categories: 3 }))
const overview = http.get('/api/families/7/overview', () => HttpResponse.json({
  total_medicines: 0, total_packages: 0, expired: [], expiring: [], low: [], favorites: [], helps_me: [], expiring_soon_days: 30,
}))

describe('админка', () => {
  it('обычного пользователя не пускает и ссылку не показывает', async () => {
    server.use(overview)
    renderApp('/admin')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/'))
    expect(screen.queryByRole('link', { name: 'Админка' })).not.toBeInTheDocument()
  })

  it('администратор видит статистику и список людей', async () => {
    server.use(stats, http.get('/api/admin/users', () => HttpResponse.json([
      { id: 1, email: 'nikita@example.com', name: 'Никита', is_admin: true, created_at: '2026-09-26T10:00:00Z', families: [] },
      { id: 2, email: 'mom@example.com', name: 'Мама', is_admin: false, created_at: '2026-09-26T11:00:00Z', families: [] },
    ])))
    const { user } = renderApp('/admin', { me: ADMIN })
    expect(await screen.findByRole('heading', { name: 'Администрирование' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Админка' })).toHaveAttribute('href', '/admin')
    expect(await screen.findByText('Мама')).toBeInTheDocument()
    const people = screen.getByText('Людей').closest('.stat') as HTMLElement
    expect(within(people).getByText('5')).toBeInTheDocument()
    // поиск по людям работает на клиенте
    await user.type(screen.getByPlaceholderText('Имя или почта'), 'mom@')
    expect(screen.queryByText('Никита', { selector: '.admin-row *' })).not.toBeInTheDocument()
    expect(screen.getByText('Мама')).toBeInTheDocument()
  })

  it('категории: порядок меняется стрелками, новая сохраняется', async () => {
    let order: unknown
    let created: unknown
    server.use(
      stats,
      http.get('/api/admin/categories', () => HttpResponse.json(CATS)),
      http.put('/api/admin/categories/order', async ({ request }) => {
        order = await request.json()
        return HttpResponse.json(CATS)
      }),
      http.post('/api/admin/categories', async ({ request }) => {
        created = await request.json()
        return HttpResponse.json({ id: 4, medicine_count: 0, ...(created as object) }, { status: 201 })
      }),
    )
    const { user } = renderApp('/admin?tab=categories', { me: ADMIN })
    expect(await screen.findByText('Жаропонижающие')).toBeInTheDocument()
    const [firstDown] = screen.getAllByTitle('Ниже')
    expect(screen.getAllByTitle('Выше')[0]).toBeDisabled()
    await user.click(firstDown)
    await waitFor(() => expect(order).toEqual({ ids: [2, 1, 3] }))

    await user.click(screen.getByRole('button', { name: 'Новая' }))
    const dialog = screen.getByRole('dialog', { name: 'Новая категория' })
    await user.type(within(dialog).getByPlaceholderText('Название'), 'Глаза')
    await user.click(within(dialog).getByRole('radio', { name: '👁️' }))
    await user.click(within(dialog).getByRole('radio', { name: '#6e56cf' }))
    expect(within(dialog).getByRole('radio', { name: '👁️' })).toHaveAttribute('aria-checked', 'true')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(created).toMatchObject({ name: 'Глаза', icon: '👁️', color: '#6e56cf' }))
  })

  it('подсказки «От чего помогает»: добавить, поднять, убрать и сохранить', async () => {
    let saved: unknown
    server.use(
      stats,
      http.get('/api/admin/indication-hints', () => HttpResponse.json(['головная боль', 'температура', 'кашель'])),
      http.put('/api/admin/indication-hints', async ({ request }) => {
        saved = await request.json()
        return HttpResponse.json((saved as { hints: string[] }).hints)
      }),
    )
    const { user } = renderApp('/admin?tab=hints', { me: ADMIN })
    expect(await screen.findByText('температура')).toBeInTheDocument()
    const save = screen.getByRole('button', { name: 'Сохранить' })
    expect(save).toBeDisabled()  // пока ничего не меняли

    await user.type(screen.getByPlaceholderText('Например, зубная боль'), '  зубная   боль ')
    await user.click(screen.getByRole('button', { name: 'Добавить' }))
    await user.type(screen.getByPlaceholderText('Например, зубная боль'), 'Кашель')
    await user.click(screen.getByRole('button', { name: 'Добавить' }))  // повтор без учёта регистра не добавится
    expect(await screen.findByText('Такая подсказка уже есть')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Убрать «температура»' }))
    const rows = () => [...document.querySelectorAll('.list-row .grow')].map(e => e.textContent)
    expect(rows()).toEqual(['головная боль', 'кашель', 'зубная боль'])
    const [, , up] = screen.getAllByTitle('Выше')
    await user.click(up)
    expect(rows()).toEqual(['головная боль', 'зубная боль', 'кашель'])

    await user.click(save)
    await waitFor(() => expect(saved).toEqual({ hints: ['головная боль', 'зубная боль', 'кашель'] }))
    expect(await screen.findByText('Подсказки сохранены')).toBeInTheDocument()
  })
})

describe('админка: закрытый режим', () => {
  it('включает режим и открывает доступ отмеченному человеку', async () => {
    let body: unknown
    server.use(
      stats,
      http.get('/api/admin/users', () => HttpResponse.json([
        { id: 1, email: 'nikita@example.com', name: 'Никита', is_admin: true, created_at: '2026-09-26T10:00:00Z', families: [] },
        { id: 2, email: 'mom@example.com', name: 'Мама', is_admin: false, created_at: '2026-09-26T11:00:00Z', families: [] },
      ])),
      http.get('/api/admin/access', () => HttpResponse.json({ closed: false, user_ids: [] })),
      http.put('/api/admin/access', async ({ request }) => { const b = await request.json() as { closed: boolean; user_ids: number[] }; body = b; return HttpResponse.json(b) }),
    )
    const { user } = renderApp('/admin?tab=access', { me: ADMIN })
    await user.click(await screen.findByRole('checkbox', { name: /Сайт в разработке/ }))
    expect(screen.getByRole('checkbox', { name: 'Доступ: Никита' })).toBeDisabled()
    await user.click(screen.getByRole('checkbox', { name: 'Доступ: Мама' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(body).toEqual({ closed: true, user_ids: [2] }))
  })

  it('тарифы: включение платной версии и Плюс аккаунту со сроком', async () => {
    const person = {
      id: 1, name: 'Никита', email: 'nikita@example.com', is_admin: true, email_verified: true, created_at: '2026-09-26T10:00:00Z',
      families: [{ id: 7, name: 'Семья Никиты', role: 'owner' }, { id: 8, name: 'С собой', role: 'owner' }],
      plan: 'free', plus_until: null, plus_active: false,
    }
    let billing: Record<string, unknown> | undefined
    let plan: { plan: string; plus_until: string | null } | undefined
    server.use(
      stats,
      http.get('/api/admin/billing', () => HttpResponse.json({ enabled: false, price_month: null, price_year: 990, trial_days: 5 })),
      http.put('/api/admin/billing', async ({ request }) => { billing = await request.json() as Record<string, unknown>; return HttpResponse.json(billing) }),
      http.get('/api/admin/users', () => HttpResponse.json([person])),
      http.put('/api/admin/users/1/plan', async ({ request }) => {
        plan = await request.json() as typeof plan
        return HttpResponse.json({ ...person, ...plan, plus_active: true })
      }),
    )
    const { user } = renderApp('/admin?tab=plans', { me: ADMIN })
    window.confirm = () => true
    await user.click(await screen.findByRole('checkbox', { name: /Платная версия включена/ }))
    await waitFor(() => expect(billing).toEqual({ enabled: true, price_month: null, price_year: 990, trial_days: 5 }))  // цена не стирается

    // стоимость подписки
    expect(screen.getByLabelText('В год, ₽')).toHaveValue(990)
    await user.type(screen.getByLabelText('В месяц, ₽'), '149')
    await user.click(screen.getByRole('button', { name: 'Сохранить стоимость' }))
    await waitFor(() => expect(billing).toEqual({ enabled: true, price_month: 149, price_year: 990, trial_days: 5 }))

    // пробный срок для новых аккаунтов
    const trialInput = screen.getByLabelText('Дней пробного периода')
    expect(trialInput).toHaveValue(5)
    await user.clear(trialInput)
    await user.type(trialInput, '14')
    await user.click(screen.getByRole('button', { name: 'Сохранить срок' }))
    await waitFor(() => expect(billing).toEqual({ enabled: true, price_month: 149, price_year: 990, trial_days: 14 }))

    expect(screen.getByText('Семья Никиты, С собой')).toBeInTheDocument()  // аптечки, на которые действует Плюс человека
    await user.click(screen.getByText('Семья Никиты, С собой'))
    const sheet = await screen.findByRole('dialog', { name: 'Тариф: Никита' })
    await user.click(within(sheet).getByRole('radio', { name: 'Плюс' }))
    await user.click(within(sheet).getByRole('button', { name: '+1 месяц' }))
    await user.click(within(sheet).getByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(plan?.plan).toBe('plus'))
    const days = (new Date(plan!.plus_until!).getTime() - Date.now()) / 86_400_000
    expect(days).toBeGreaterThan(27)
    expect(days).toBeLessThan(33)
  })
})

describe('режим отладки', () => {
  it('админ включает его, и версия появляется вверху страницы', async () => {
    let enabled = false
    server.use(
      stats, overview,
      http.get('/api/auth/access', () => HttpResponse.json({ closed: false, debug: enabled })),
      http.get('/api/admin/debug', () => HttpResponse.json({ enabled })),
      http.put('/api/admin/debug', async ({ request }) => {
        enabled = ((await request.json()) as { enabled: boolean }).enabled
        return HttpResponse.json({ enabled })
      }),
    )
    const { user } = renderApp('/admin?tab=debug', { me: ADMIN })
    expect(screen.queryByTestId('debug-bar')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-note')).not.toBeInTheDocument()
    await user.click(await screen.findByRole('checkbox', { name: /Режим отладки/ }))
    await waitFor(() => expect(screen.getByTestId('debug-bar').textContent).toMatch(/^Версия /))
    expect(screen.getByTestId('debug-note').textContent).toMatch(/12 часов/)
  })
})

describe('Telegram', () => {
  it('админ включает и выключает Telegram', async () => {
    let enabled = false
    const puts: boolean[] = []
    server.use(
      stats, overview,
      http.get('/api/admin/telegram', () => HttpResponse.json({ enabled, configured: false })),
      http.put('/api/admin/telegram', async ({ request }) => {
        enabled = ((await request.json()) as { enabled: boolean }).enabled
        puts.push(enabled)
        return HttpResponse.json({ enabled, configured: false })
      }),
    )
    const { user } = renderApp('/admin?tab=telegram', { me: ADMIN })
    const box = await screen.findByRole('checkbox', { name: /Telegram включён/ })
    expect(box).not.toBeChecked()
    expect(screen.getByTestId('telegram-not-configured')).toBeInTheDocument()
    await user.click(box)
    await waitFor(() => expect(box).toBeChecked())
    await user.click(box)
    await waitFor(() => expect(box).not.toBeChecked())
    expect(puts).toEqual([true, false])
  })
})
