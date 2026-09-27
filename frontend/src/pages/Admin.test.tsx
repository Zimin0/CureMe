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
