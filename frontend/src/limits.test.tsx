import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { planFixture, server } from './test/server'
import { medicine, renderApp } from './test/utils'

const FULL = planFixture({ has_plus: false, billing_enabled: true, usage: { members: 4, medicines: 60 } })

describe('лимиты бесплатной версии', () => {
  it('счётчик виден заранее, а при набранном лимите «Добавить» открывает шторку Плюса', async () => {
    server.use(
      http.get('/api/families/7/plan', () => HttpResponse.json(FULL)),
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([medicine()])),
    )
    const { user } = renderApp('/medicines')
    expect(await screen.findByText('60 из 60 лекарств')).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'Добавить' }))
    expect(await screen.findByText('Доступно в Капсулке Плюс')).toBeInTheDocument()
    expect(screen.getByText('Без лимитов')).toBeInTheDocument()
    expect(screen.getByTestId('location').textContent).toBe('/medicines')
  })

  it('пока место есть, «Добавить» ведёт в форму, где тоже виден счётчик', async () => {
    server.use(
      http.get('/api/families/7/plan', () => HttpResponse.json({ ...FULL, usage: { members: 1, medicines: 58 } })),
      http.get('/api/indication-hints', () => HttpResponse.json([])),
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([medicine()])),
    )
    const { user } = renderApp('/medicines')
    expect(await screen.findByText('58 из 60 лекарств')).toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: 'Добавить' }))
    expect(screen.getByTestId('location').textContent).toBe('/medicines/new')
    expect(await screen.findByText('58 из 60 лекарств')).toBeInTheDocument()
    expect(screen.queryByText(/Место в бесплатной версии закончилось/)).not.toBeInTheDocument()
  })

  it('без лимита счётчика нет', async () => {
    server.use(
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([medicine()])),
    )
    renderApp('/medicines')
    expect(await screen.findByText('1 в списке')).toBeInTheDocument()
    expect(screen.queryByText(/из 60/)).not.toBeInTheDocument()
  })

  it('в заполненную семью по ссылке не вступить', async () => {
    server.use(http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', owner_name: 'Анна', full: true })))
    renderApp('/join/ABCD2345')
    expect(await screen.findByText('В «Зимины» нет мест')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Вступить/ })).not.toBeInTheDocument()
  })

  it('регистрация с кодом заполненной семьи предупреждает и не отправляется', async () => {
    server.use(http.get('/api/invites/ABCD2345', () => HttpResponse.json({ family_name: 'Зимины', owner_name: 'Анна', full: true })))
    renderApp('/register?invite=ABCD2345', { loggedIn: false })
    expect(await screen.findByText(/Попросите владельца подключить Капсулку Плюс/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Создать аккаунт' })).toBeDisabled()
  })
})
