import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GOALS, getConsent, safePath, setConsent, track } from './analytics'
import { server } from './test/server'
import { renderApp } from './test/utils'

const withCounter = () => server.use(http.get('/api/auth/access', () => HttpResponse.json({ closed: false, metrika_id: '12345678' })))

describe('аналитика', () => {
  beforeEach(() => { localStorage.clear(); delete window.ym; document.head.querySelectorAll('script[src*="mc.yandex"]').forEach(n => n.remove()) })

  it('safePath отдаёт Метрике только публичные страницы без кодов', () => {
    expect(safePath('/join/ABC123')).toBe('/join')
    expect(safePath('/register')).toBe('/register')
    expect(safePath('/medicines/42')).toBe('/app')
    expect(safePath('/illness/new')).toBe('/app')
    expect(safePath('/')).toBe('/')
  })

  it('без номера счётчика баннера нет', async () => {
    renderApp('/login', { loggedIn: false })
    await screen.findByRole('button', { name: /Войти/ })
    expect(screen.queryByRole('dialog', { name: 'Файлы cookie' })).not.toBeInTheDocument()
  })

  it('до согласия скрипт Яндекса не грузится, после «Принять» грузится', async () => {
    withCounter()
    renderApp('/login', { loggedIn: false })
    const banner = await screen.findByRole('dialog', { name: 'Файлы cookie' })
    expect(document.querySelector('script[src*="mc.yandex.ru"]')).toBeNull()
    await userEvent.click(screen.getByRole('button', { name: 'Принять' }))
    expect(banner).not.toBeInTheDocument()
    expect(getConsent()).toBe('yes')
    await vi.waitFor(() => expect(document.querySelector('script[src*="mc.yandex.ru"]')).not.toBeNull())
  })

  it('«Отклонить» запоминается, скрипта нет, баннер не возвращается', async () => {
    withCounter()
    renderApp('/login', { loggedIn: false })
    await userEvent.click(await screen.findByRole('button', { name: 'Отклонить' }))
    expect(getConsent()).toBe('no')
    expect(document.querySelector('script[src*="mc.yandex.ru"]')).toBeNull()
  })

  it('отзыв согласия удаляет cookie Метрики', () => {
    document.cookie = '_ym_uid=1; path=/'
    setConsent('yes')
    setConsent('no')
    expect(document.cookie).not.toContain('_ym_uid')
  })

  it('Политика: п. 8 называет Яндекс Метрику и даёт отозвать согласие', async () => {
    withCounter()
    setConsent('yes')
    renderApp('/privacy', { loggedIn: false })
    expect(await screen.findByText(/8\.2\. Для учёта посещаемости/)).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Отозвать согласие' })).toBeInTheDocument()
  })

  it('согласие хранится с датой и редакцией Политики', () => {
    setConsent('yes')
    const saved = JSON.parse(localStorage.getItem('curemeAnalytics')!)
    expect(saved).toMatchObject({ v: 'yes', edition: '12 октября 2026 г.' })
    expect(saved.at).toMatch(/^\d{4}-\d\d-\d\dT/)
  })

  it('цель на адресе с кодом приглашения ждёт чистого адреса', async () => {
    withCounter()
    setConsent('yes')
    const ym = vi.fn()
    window.ym = ym
    window.history.pushState({}, '', '/register?invite=ABC123')
    renderApp('/register?invite=ABC123', { loggedIn: false })
    await vi.waitFor(() => expect(ym).toHaveBeenCalledWith(12345678, 'hit', expect.any(String), { title: '' }))
    ym.mockClear()
    track(GOALS.register)
    expect(ym).not.toHaveBeenCalledWith(12345678, 'reachGoal', 'register')
    window.history.pushState({}, '', '/')
    track(GOALS.register)
    expect(ym).toHaveBeenCalledWith(12345678, 'reachGoal', 'register')
  })
})
