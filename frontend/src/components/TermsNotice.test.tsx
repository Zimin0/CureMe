import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { TermsNotice } from './TermsNotice'

const show = (now: Date) => render(<MemoryRouter><TermsNotice now={now} /></MemoryRouter>)

describe('Предупреждение о новой редакции Соглашения (п. 11.3)', () => {
  beforeEach(() => localStorage.clear())

  it('до 13 октября показывается и ведёт на Соглашение', () => {
    show(new Date('2026-10-05T10:00:00Z'))
    expect(screen.getByRole('status')).toHaveTextContent('С 13 октября 2026 г. вступает в силу новая редакция')
    expect(screen.getByRole('link', { name: 'Пользовательского соглашения' })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('status')).toHaveTextContent('в бесплатной семье до 3 человек')
  })

  it('«Понятно» скрывает и запоминает выбор', async () => {
    const { unmount } = show(new Date('2026-10-05T10:00:00Z'))
    await userEvent.click(screen.getByRole('button', { name: 'Понятно, скрыть' }))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    unmount()
    show(new Date('2026-10-06T10:00:00Z'))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('после вступления редакции в силу не показывается', () => {
    show(new Date('2026-10-12T21:00:00Z'))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
