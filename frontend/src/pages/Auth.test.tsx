import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const location = () => screen.getByTestId('location').textContent
const overview = http.get('/api/families/:id/overview', () => HttpResponse.json({
  total_medicines: 0, total_packages: 0, expired: [], expiring: [], low: [], favorites: [], helps_me: [], expiring_soon_days: 30,
}))

describe('вход', () => {
  it('успешный вход сохраняет токен и возвращает туда, куда шли', async () => {
    let body: unknown
    server.use(
      http.post('/api/auth/login', async ({ request }) => { body = await request.json(); return HttpResponse.json({ access_token: 'jwt-1', user: ME }) }),
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([])),
    )
    const { user } = renderApp('/login?next=/medicines', { loggedIn: false })
    await user.type(await screen.findByLabelText('Почта'), 'nikita@example.com')
    await user.type(screen.getByLabelText('Пароль'), 'secret123')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    await waitFor(() => expect(location()).toBe('/medicines'))
    expect(body).toEqual({ email: 'nikita@example.com', password: 'secret123' })
    expect(localStorage.getItem('cureme.token')).toBe('jwt-1')
    expect(await screen.findByText('Аптечка пустая')).toBeInTheDocument()
  })

  it('неверный пароль — сообщение сервера', async () => {
    server.use(http.post('/api/auth/login', () => HttpResponse.json({ detail: 'Неверная почта или пароль' }, { status: 401 })))
    const { user } = renderApp('/login', { loggedIn: false })
    await user.type(await screen.findByLabelText('Почта'), 'nikita@example.com')
    await user.type(screen.getByLabelText('Пароль'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Войти' }))
    expect(await screen.findByText('Неверная почта или пароль')).toBeInTheDocument()
    expect(location()).toBe('/login')
  })

  it('ссылка на регистрацию сохраняет next', async () => {
    renderApp('/login?next=/family', { loggedIn: false })
    expect(await screen.findByRole('link', { name: 'Зарегистрироваться' })).toHaveAttribute('href', '/register?next=%2Ffamily')
  })
})

describe('регистрация', () => {
  it('по приглашению показывает название семьи и отправляет код', async () => {
    let body: Record<string, unknown> = {}
    server.use(
      http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', members: 2 })),
      http.post('/api/auth/register', async ({ request }) => {
        body = await request.json() as Record<string, unknown>
        return HttpResponse.json({ access_token: 'jwt', user: ME }, { status: 201 })
      }),
      overview,
    )
    const { user } = renderApp('/register?invite=ABCD2345', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'Вступить в «Зимины»' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Как вас зовут'), 'Мама')
    await user.type(screen.getByLabelText('Почта'), 'mom@example.com')
    await user.type(screen.getByLabelText(/^Пароль/), 'secret123')
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    await waitFor(() => expect(location()).toBe('/'))
    expect(body).toEqual({ name: 'Мама', email: 'mom@example.com', password: 'secret123', invite_code: 'ABCD2345' })
  })

  it('неверный код приглашения подсвечивается', async () => {
    server.use(http.get('/api/invites/:code', () => HttpResponse.json({ detail: 'нет' }, { status: 404 })))
    const { user } = renderApp('/register', { loggedIn: false })
    await user.type(await screen.findByLabelText(/^Код приглашения в семью/), 'WRONG1')
    expect(await screen.findByText('Такого кода нет')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Новый аккаунт' })).toBeInTheDocument()
  })
})

describe('ссылка-приглашение', () => {
  it('гостю предлагает зарегистрироваться или войти', async () => {
    server.use(http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', members: 2 })))
    renderApp('/join/ABCD2345', { loggedIn: false })
    expect(await screen.findByRole('link', { name: 'Создать аккаунт и вступить' })).toHaveAttribute('href', '/register?invite=ABCD2345')
    expect(screen.getByRole('link', { name: 'У меня уже есть аккаунт' })).toHaveAttribute('href', '/login?next=/join/ABCD2345')
  })

  it('вошедший вступает одной кнопкой', async () => {
    server.use(
      http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', members: 2 })),
      http.post('/api/families/join', () => HttpResponse.json({ id: 9, name: 'Зимины', invite_code: 'ABCD2345', role: 'member', members: [] })),
      overview,
    )
    const { user } = renderApp('/join/ABCD2345')
    await user.click(await screen.findByRole('button', { name: 'Вступить как Никита' }))
    expect(await screen.findByText('Вы в семье «Зимины»')).toBeInTheDocument()
    await waitFor(() => expect(location()).toBe('/'))
  })

  it('устаревший код', async () => {
    server.use(http.get('/api/invites/OLD', () => HttpResponse.json({ detail: 'нет' }, { status: 404 })))
    renderApp('/join/OLD', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'Приглашение не найдено' })).toBeInTheDocument()
  })
})
