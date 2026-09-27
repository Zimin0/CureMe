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
    await user.click(screen.getByRole('checkbox', { name: /согласие на обработку/ }))
    await user.click(screen.getByRole('checkbox', { name: /пользовательское соглашение/ }))
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    await waitFor(() => expect(location()).toBe('/'))
    expect(body).toEqual({ name: 'Мама', email: 'mom@example.com', password: 'secret123', invite_code: 'ABCD2345', consent: true })
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

describe('согласие на обработку данных', () => {
  it('без галочек аккаунт не создаётся', async () => {
    let called = false
    server.use(http.post('/api/auth/register', () => { called = true; return HttpResponse.json({}, { status: 201 }) }))
    const { user } = renderApp('/register', { loggedIn: false })
    await user.type(await screen.findByLabelText('Как вас зовут'), 'Мама')
    await user.type(screen.getByLabelText('Почта'), 'mom@example.com')
    await user.type(screen.getByLabelText(/^Пароль/), 'secret123')
    expect(screen.getByRole('checkbox', { name: /согласие на обработку/ })).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Создать аккаунт' }))
    expect(called).toBe(false)
    expect(screen.getByRole('link', { name: 'согласие на обработку персональных данных' })).toHaveAttribute('href', '/consent')
  })

  it('старый аккаунт сначала видит экран согласия', async () => {
    let body: unknown
    let me = { ...ME, consent_needed: true }
    const { user } = renderApp('/', { me })
    server.use(  // после renderApp, чтобы /auth/me отдавал свежие данные
      http.get('/api/auth/me', () => HttpResponse.json(me)),
      http.post('/api/auth/consent', async ({ request }) => { body = await request.json(); me = { ...ME, consent_needed: false }; return HttpResponse.json(me) }),
      overview,
    )
    expect(await screen.findByRole('heading', { name: 'Нужно ваше согласие' })).toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: /согласие на обработку/ }))
    await user.click(screen.getByRole('checkbox', { name: /пользовательское соглашение/ }))
    await user.click(screen.getByRole('button', { name: 'Продолжить' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Нужно ваше согласие' })).not.toBeInTheDocument())
    expect(body).toEqual({ consent: true })
  })

  it('документы открываются без входа', async () => {
    renderApp('/privacy', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'Политика обработки персональных данных' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Пользовательское соглашение' })).toHaveAttribute('href', '/terms')
  })

  it('удаление аккаунта просит пароль и выходит', async () => {
    let body: unknown
    server.use(
      http.delete('/api/auth/me', async ({ request }) => { body = await request.json(); return new HttpResponse(null, { status: 204 }) }),
    )
    const { user } = renderApp('/', { me: { ...ME, consent_needed: true } })
    await user.click(await screen.findByRole('button', { name: 'Удалить аккаунт' }))
    await user.type(screen.getByLabelText('Пароль для подтверждения'), 'secret123')
    await user.click(screen.getByRole('button', { name: 'Удалить навсегда' }))
    await waitFor(() => expect(location()).toMatch(/^\/login/))
    expect(body).toEqual({ password: 'secret123' })
  })
})

describe('закрытый режим', () => {
  const closed = http.get('/api/auth/access', () => HttpResponse.json({ closed: true }))

  it('гость видит «Сайт в разработке» с почтой, но может войти', async () => {
    server.use(closed)
    renderApp('/login', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'Сайт в разработке' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /@/ })).toHaveAttribute('href', expect.stringMatching(/^mailto:/))
    expect(screen.getByRole('button', { name: 'Войти' })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Зарегистрироваться' })).not.toBeInTheDocument()
  })

  it('регистрация закрыта', async () => {
    server.use(closed)
    renderApp('/register', { loggedIn: false })
    expect(await screen.findByText('Регистрация пока закрыта')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Создать аккаунт' })).not.toBeInTheDocument()
  })

  it('вошедший без доступа может только удалить аккаунт или выйти', async () => {
    renderApp('/', { me: { ...ME, access_blocked: true } })
    expect(await screen.findByRole('heading', { name: 'Сайт в разработке' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Удалить аккаунт' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Выйти' })).toBeInTheDocument()
  })
})
