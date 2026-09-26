import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import type { Overview } from './api'
import { server } from './test/server'
import { ME, medicine, renderApp } from './test/utils'

const EMPTY_OVERVIEW: Overview = {
  total_medicines: 0, total_packages: 0, expired: [], expiring: [], low: [], favorites: [], helps_me: [], expiring_soon_days: 30,
}

const location = () => screen.getByTestId('location').textContent

describe('маршрутизация и доступ', () => {
  it('гостя отправляет на вход и запоминает, куда он шёл', async () => {
    renderApp('/medicines?filter=low', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'С возвращением' })).toBeInTheDocument()
    expect(location()).toBe('/login?next=%2Fmedicines%3Ffilter%3Dlow')
  })

  it('вошедшего не пускает на страницу входа', async () => {
    server.use(http.get('/api/families/7/overview', () => HttpResponse.json(EMPTY_OVERVIEW)))
    renderApp('/login')
    await waitFor(() => expect(location()).toBe('/'))
  })

  it('неизвестный адрес ведёт на главную', async () => {
    server.use(http.get('/api/families/7/overview', () => HttpResponse.json(EMPTY_OVERVIEW)))
    renderApp('/no/such/page')
    await waitFor(() => expect(location()).toBe('/'))
  })

  it('протухший токен разлогинивает', async () => {
    localStorage.setItem('cureme.token', 'old')
    server.use(http.get('/api/auth/me', () => HttpResponse.json({ detail: 'Нужно войти в аккаунт' }, { status: 401 })))
    renderApp('/', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'С возвращением' })).toBeInTheDocument()
    expect(localStorage.getItem('cureme.token')).toBeNull()
  })

  it('человек без семьи видит экран «Вы пока не в семье»', async () => {
    renderApp('/', { me: { ...ME, families: [] } })
    expect(await screen.findByRole('heading', { name: 'Вы пока не в семье' })).toBeInTheDocument()
  })
})

describe('главная', () => {
  it('пустая аптечка', async () => {
    server.use(http.get('/api/families/7/overview', () => HttpResponse.json(EMPTY_OVERVIEW)))
    renderApp('/')
    expect(await screen.findByText(/Аптечка пока пустая/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Никита')
    expect(screen.getByText('Всё в порядке')).toBeInTheDocument()
  })

  it('показывает, что требует внимания', async () => {
    const expired = medicine({ id: 1, name: 'Смекта', unit: 'пак', stock: { total: 0, expired_quantity: 3, package_count: 1, nearest_expiry: null, days_left: null, status: 'expired' } })
    const expiring = medicine({ id: 2, name: 'Називин', stock: { total: 1, expired_quantity: 0, package_count: 1, nearest_expiry: null, days_left: 5, status: 'expiring' } })
    const low = medicine({ id: 3, name: 'Бинт', unit: 'шт', stock: { total: 0, expired_quantity: 0, package_count: 0, nearest_expiry: null, days_left: null, status: 'out' } })
    const mine = medicine({ id: 4, name: 'Ибупрофен', helps_me: true })
    server.use(http.get('/api/families/7/overview', () => HttpResponse.json({
      ...EMPTY_OVERVIEW, total_medicines: 4, total_packages: 3, expired: [expired], expiring: [expiring], low: [low], helps_me: [mine], favorites: [mine],
    })))
    renderApp('/')
    expect(await screen.findByText('Требуют внимания: 3. Проверьте список ниже.')).toBeInTheDocument()
    expect(screen.getByText('Просрочено: 3 пак')).toBeInTheDocument()
    expect(screen.getByText('ещё 5 дней')).toBeInTheDocument()
    expect(screen.getByText('Закончилось')).toBeInTheDocument()
    // лекарство в «помогает» и «избранном» одновременно показываем один раз
    expect(screen.getAllByText('Ибупрофен')).toHaveLength(1)
  })
})
