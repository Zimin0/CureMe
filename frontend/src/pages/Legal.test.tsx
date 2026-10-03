import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderApp } from '../test/utils'

describe('юридические страницы', () => {
  it('Соглашение: редакция от 3 октября, разделы 1–13, ссылка на оферту', async () => {
    renderApp('/terms')
    expect(await screen.findByRole('heading', { name: 'Пользовательское соглашение' })).toBeInTheDocument()
    expect(screen.getByText('Редакция от 3 октября 2026 г.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '13. Сведения об Администрации' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /kapsulka\.ru\/offer/ })).toHaveAttribute('href', '/offer')
  })

  it('Политика: редакция от 3 октября, письма о приёме зависят от тарифа семьи, а не аптечки', async () => {
    renderApp('/privacy')
    expect(await screen.findByText('Редакция от 3 октября 2026 г.')).toBeInTheDocument()
    expect(screen.getByText(/Если у семьи Пользователя действует тариф «Плюс»/)).toBeInTheDocument()
    expect(screen.queryByText(/хотя бы в одной аптечке/)).not.toBeInTheDocument()
  })

  it('Соглашение: срок вступления в силу 13 октября (п. 11.2) и «член семьи» в п. 4.2', async () => {
    renderApp('/terms')
    expect(await screen.findByText('Настоящая редакция вступает в силу 13 октября 2026 г.')).toBeInTheDocument()
    expect(screen.getByText(/4\.2\. Совершеннолетний член семьи/)).toBeInTheDocument()
    expect(screen.queryByText(/участник семейной аптечки/)).not.toBeInTheDocument()
  })

  it('страница оферты: автопродление по отдельному согласию и возврат, ИНН показан флагом', async () => {
    renderApp('/offer')
    expect(await screen.findByRole('heading', { name: 'Публичная оферта «Капсулка Плюс»' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '4. Автопродление' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '5. Отказ от услуги и возврат' })).toBeInTheDocument()
    expect(screen.getByText(/ИНН 470418719903/)).toBeInTheDocument()
  })

  it('Политика называет платёжный сервис ЮKassa', async () => {
    renderApp('/privacy')
    expect(await screen.findByText(/5\.9\. Оплата\./)).toBeInTheDocument()
  })

  it('Политика: сроки хранения приглашений и журнала семьи (п. 6.4)', async () => {
    renderApp('/privacy')
    expect(await screen.findByText(/6\.4\. Служебные сведения о приглашениях в семью/)).toBeInTheDocument()
    expect(screen.getByText(/хранится 12 месяцев либо до удаления семьи/)).toBeInTheDocument()
  })

  it('Соглашение п. 6.8: передача владения только с согласием, исключение для администрации', async () => {
    renderApp('/terms', { loggedIn: false })
    expect(await screen.findByText(/Владение передаётся только с согласия принимающего человека/)).toBeInTheDocument()
    expect(screen.getByText(/уведомив об этом всех членов семьи по электронной почте/)).toBeInTheDocument()
  })
})

describe('согласие на передачу сведений доверенному лицу', () => {
  it('страница /consent-share: редакция, получатель, отзыв', async () => {
    renderApp('/consent-share', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: /Согласие на передачу доверенному лицу/ })).toBeInTheDocument()
    expect(screen.getByText('Редакция согласия: share-2026-10-02.2.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '6. Срок и отзыв' })).toBeInTheDocument()
  })

  it('телефон исполнителя в разд. 13 Соглашения', async () => {
    renderApp('/terms', { loggedIn: false })
    expect(await screen.findByText(/Телефон: \+7 931 366-12-20/)).toBeInTheDocument()
  })
})
