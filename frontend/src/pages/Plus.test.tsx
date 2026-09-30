import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { planFixture, server } from '../test/server'
import { renderApp } from '../test/utils'

describe('страница «Капсулка Плюс»', () => {
  it('пока платная версия выключена, говорит, что всё доступно', async () => {
    renderApp('/plus')
    expect(await screen.findByRole('heading', { name: 'Капсулка Плюс' })).toBeInTheDocument()
    expect(screen.getByText('Все функции открыты')).toBeInTheDocument()
    expect(screen.getByText(/все функции Плюса доступны бесплатно/)).toBeInTheDocument()
    expect(screen.getByText('до 60')).toBeInTheDocument()
    expect(screen.getByText('30 дней истории')).toBeInTheDocument()
  })

  it('бесплатная семья видит замки и что оплата скоро', async () => {
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false, billing_enabled: true }))))
    renderApp('/plus')
    expect(await screen.findByText('Бесплатная версия')).toBeInTheDocument()
    expect(screen.getByText(/Оплата появится скоро/)).toBeInTheDocument()
    expect(screen.getByText('Вся история приёма')).toBeInTheDocument()
  })
})
