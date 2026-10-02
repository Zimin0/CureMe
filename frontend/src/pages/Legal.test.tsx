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

  it('Политика осталась в прежней редакции', async () => {
    renderApp('/privacy')
    expect(await screen.findByText('Редакция от 1 октября 2026 г.')).toBeInTheDocument()
  })

  it('страница оферты сообщает, что оферта не опубликована', async () => {
    renderApp('/offer')
    expect(await screen.findByText(/пока не опубликована/)).toBeInTheDocument()
  })
})
