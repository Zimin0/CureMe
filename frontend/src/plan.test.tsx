import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { api, ApiError } from './api'
import { LimitCounter, planLabel, PlusLock, useRequirePlus } from './plan'
import { planFixture, server } from './test/server'
import { renderWithProviders } from './test/utils'

const FREE = planFixture({ has_plus: false, billing_enabled: true, usage: { members: 4, medicines: 58 } })

function withFamily() {
  localStorage.setItem('cureme.family', '7')
  localStorage.setItem('cureme.token', 't')
  server.use(http.get('/api/auth/me', () => HttpResponse.json({
    id: 1, email: 'n@example.com', name: 'Никита', is_admin: false, families: [{ id: 7, name: 'Семья', role: 'owner' }],
  })))
}

function Guarded({ onRun }: { onRun: () => void }) {
  const require = useRequirePlus()
  return <button onClick={() => require('export_pdf', onRun)}>Экспорт</button>
}

describe('Капсулка Плюс на фронтенде', () => {
  it('без лимита счётчика и замка нет', async () => {
    withFamily()
    renderWithProviders(<><LimitCounter name="medicines" /><PlusLock feature="export_pdf" /><span>готово</span></>)
    await screen.findByText('готово')
    await new Promise(r => setTimeout(r, 50))
    expect(screen.queryByText(/из 60/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Доступно в Плюсе/ })).not.toBeInTheDocument()
  })

  it('в бесплатной версии: счётчик лимита и замок открывают шторку', async () => {
    withFamily()
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(FREE)))
    const { user } = renderWithProviders(<><LimitCounter name="medicines" /><LimitCounter name="members" /><PlusLock feature="export_pdf" /></>)
    expect(await screen.findByText('58 из 60 лекарств')).toBeInTheDocument()
    expect(screen.getByText('4 из 4 участников')).toHaveClass('full')
    await user.click(screen.getByRole('button', { name: /Доступно в Плюсе/ }))
    expect(await screen.findByRole('dialog', { name: 'Доступно в Капсулке Плюс' })).toBeInTheDocument()
    expect(screen.getByText('Экспорт в PDF и Excel для врача')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: /Что даёт Плюс/ }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/plus'))
  })

  it('useRequirePlus выполняет действие, только если функция доступна', async () => {
    withFamily()
    let runs = 0
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(FREE)))
    const { user, qc } = renderWithProviders(<Guarded onRun={() => runs++} />)
    await waitFor(() => expect(qc.getQueryData(['plan', 7])).toBeTruthy())
    await user.click(screen.getByRole('button', { name: 'Экспорт' }))
    expect(runs).toBe(0)
    expect(await screen.findByRole('dialog')).toBeInTheDocument()

    qc.setQueryData(['plan', 7], planFixture())
    await user.click(screen.getByRole('button', { name: 'Закрыть' }))
    await user.click(screen.getByRole('button', { name: 'Экспорт' }))
    expect(runs).toBe(1)
  })

  it('ответ 402 сам открывает шторку и несёт функцию в ошибке', async () => {
    withFamily()
    server.use(http.post('/api/families/7/medicines', () => HttpResponse.json(
      { detail: 'В бесплатной версии не больше 60 лекарств в аптечке.' },
      { status: 402, headers: { 'X-Plus-Feature': 'no_limits' } },
    )))
    renderWithProviders(<span>страница</span>)
    await screen.findByText('страница')
    const err = await api('/families/7/medicines', { body: { name: 'X' } }).catch((e: ApiError) => e) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(402)
    expect(err.plusFeature).toBe('no_limits')
    expect(await screen.findByRole('dialog', { name: 'Доступно в Капсулке Плюс' })).toBeInTheDocument()
    expect(screen.getByText('Без лимитов')).toBeInTheDocument()
  })

  it('подпись тарифа', () => {
    expect(planLabel(planFixture())).toBe('Все функции открыты')
    expect(planLabel(FREE)).toBe('Бесплатная версия')
    expect(planLabel(planFixture({ plus_active: true, plan: 'plus' }))).toBe('Плюс бессрочно')
    expect(planLabel(planFixture({ plus_active: true, plan: 'plus', plus_until: '2026-12-31T20:59:59Z' }))).toMatch(/^Плюс до \d\d\.\d\d\.2026$/)
  })
})
