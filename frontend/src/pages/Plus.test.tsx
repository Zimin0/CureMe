import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it } from 'vitest'
import { planFixture, server } from '../test/server'
import { renderApp } from '../test/utils'

describe('страница «Капсулка Плюс»', () => {
  it('пока платная версия выключена, говорит, что всё доступно', async () => {
    renderApp('/plus')
    expect(await screen.findByRole('heading', { name: /Капсулк. Плюс/ })).toBeInTheDocument()
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
    expect(screen.queryByText(/Стоимость Плюса/)).not.toBeInTheDocument()
  })

  it('заголовок сверху: «Оформите…» без Плюса и «…оформлена!» с Плюсом', async () => {
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false, billing_enabled: true }))))
    const first = renderApp('/plus')
    expect(await screen.findByRole('heading', { name: 'Оформите Капсулку Плюс' })).toBeInTheDocument()
    first.unmount()
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: true, plus_active: true, billing_enabled: true }))))
    renderApp('/plus')
    expect(await screen.findByRole('heading', { name: 'Капсулка Плюс оформлена!' })).toBeInTheDocument()
  })

  it('показывает стоимость, которую задал администратор, с пометкой «не оферта»', async () => {
    server.use(http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ price_month: 149, price_year: 990 }))))
    renderApp('/plus')
    expect(await screen.findByText('149 ₽ в месяц или 990 ₽ в год')).toBeInTheDocument()
    expect(screen.getByText(/не является публичной офертой/)).toBeInTheDocument()
  })
})

describe('публичная страница /plus для гостей', () => {
  it('открывается без входа: цена, условия оплаты, реквизиты исполнителя', async () => {
    server.use(http.get('/api/auth/access', () => HttpResponse.json({ closed: false, listed_price_month: 199, listed_price_year: 1990, billing_enabled: false })))
    renderApp('/plus', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: 'Капсулка Плюс' })).toBeInTheDocument()
    expect(screen.getByText('199 ₽ в месяц или 1 990 ₽ в год')).toBeInTheDocument()
    expect(screen.getByText(/без физической доставки/)).toBeInTheDocument()
    expect(screen.getByText(/по умолчанию выключена/)).toBeInTheDocument()
    expect(screen.getByText(/Кнопка «Отключить автопродление»/)).toBeInTheDocument()
    expect(screen.getByText(/неиспользованный оставшийся период/)).toBeInTheDocument()
    expect(screen.getByText(/с момента возврата Плюс прекращается для всей семьи/)).toBeInTheDocument()  // R15
    expect(screen.getByText(/ИНН: 470418719903/)).toBeInTheDocument()  // реквизиты в свёрнутом блоке, текст в разметке
    expect(screen.getByText('Исполнитель и контакты').closest('details')).not.toHaveAttribute('open')
    expect(screen.getByRole('link', { name: '+7 931 366-12-20' })).toHaveAttribute('href', 'tel:+79313661220')  // показ включён флагом SHOW_SELLER_ID
    expect(screen.getByText(/Зименков Никита Вячеславович/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'публичная оферта' })).toHaveAttribute('href', '/offer')
  })

  it('без цены в настройках не выдумывает её', async () => {
    renderApp('/plus', { loggedIn: false })
    expect(await screen.findByText(/Стоимость будет указана здесь/)).toBeInTheDocument()
  })
})
