import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { renderApp } from '../test/utils'

describe('юридические страницы', () => {
  it('Соглашение: редакция от 2 октября, разделы 1–13, ссылка на оферту', async () => {
    renderApp('/terms')
    expect(await screen.findByRole('heading', { name: 'Пользовательское соглашение' })).toBeInTheDocument()
    expect(screen.getByText('Редакция от 2 октября 2026 г.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '13. Сведения об Администрации' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /kapsulka\.ru\/offer/ })).toHaveAttribute('href', '/offer')
  })

  it('Политика: редакция от 2 октября', async () => {
    renderApp('/privacy')
    expect(await screen.findByText('Редакция от 2 октября 2026 г.')).toBeInTheDocument()
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
})

describe('согласие на передачу сведений доверенному лицу', () => {
  it('страница /consent-share: редакция, получатель, отзыв', async () => {
    renderApp('/consent-share', { loggedIn: false })
    expect(await screen.findByRole('heading', { name: /Согласие на передачу доверенному лицу/ })).toBeInTheDocument()
    expect(screen.getByText('Редакция согласия: share-2026-10-02.1.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '6. Срок и отзыв' })).toBeInTheDocument()
  })
})
