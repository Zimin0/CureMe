import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { medicine } from '../test/utils'
import { MedicineCard } from './MedicineCard'
import { MedIcon, Sheet, StatusBadge, ToastProvider, useToast } from './ui'

const card = (m = medicine()) => render(<MemoryRouter><MedicineCard m={m} /></MemoryRouter>)

describe('MedicineCard', () => {
  it('ведёт на карточку лекарства и показывает остаток', () => {
    card()
    expect(screen.getByRole('link')).toHaveAttribute('href', '/medicines/1')
    expect(screen.getByText('Таблетки · 200 мг')).toBeInTheDocument()
    expect(screen.getByText('20')).toBeInTheDocument()
    expect(screen.getByText('ещё 400 дней')).toBeInTheDocument()
    expect(screen.queryByText('В наличии')).not.toBeInTheDocument()  // статус «ок» не шумит
  })

  it('отметки «помогает мне» и «избранное»', () => {
    card(medicine({ helps_me: true, is_favorite: true }))
    expect(screen.getByLabelText('Помогает мне')).toBeInTheDocument()
    expect(screen.getByLabelText('В избранном')).toBeInTheDocument()
  })

  it('просрочка: бейдж есть, «ещё N дней» нет', () => {
    card(medicine({ stock: { total: 0, expired_quantity: 5, package_count: 2, nearest_expiry: null, days_left: -3, status: 'expired' } }))
    expect(screen.getByText('Есть просрочка')).toHaveClass('badge', 'expired')
    expect(screen.queryByText(/просрочено 3/)).not.toBeInTheDocument()
    expect(screen.getByText('2 уп.')).toBeInTheDocument()
  })

  it('скоро истекает — жёлтый бейдж срока', () => {
    card(medicine({ stock: { total: 5, expired_quantity: 0, package_count: 1, nearest_expiry: null, days_left: 7, status: 'expiring' } }))
    expect(screen.getByText('ещё 7 дней')).toHaveClass('expiring')
  })

  it('без формы и категории — «Без категории»', () => {
    card(medicine({ form: null, dosage: null, manufacturer: null }))
    expect(screen.getByText('Без категории')).toBeInTheDocument()
  })
})

it('StatusBadge подписывает статус по-русски', () => {
  render(<StatusBadge stock={{ total: 1, expired_quantity: 0, package_count: 1, nearest_expiry: null, days_left: null, status: 'low' }} />)
  expect(screen.getByText('Заканчивается')).toHaveClass('low')
})

it('MedIcon: фото важнее иконки категории', () => {
  const { container, rerender } = render(<MedIcon category={{ id: 1, name: 'Аллергия', icon: '🌼', color: '#ffb224', medicine_count: 1 }} />)
  expect(container).toHaveTextContent('🌼')
  rerender(<MedIcon category={null} photo="/api/media/x.jpg" />)
  expect(container.querySelector('img')).toHaveAttribute('src', '/api/media/x.jpg')
})

describe('Sheet', () => {
  it('закрывается по Escape, крестику и клику мимо', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<Sheet title="Принять" onClose={onClose}><p>Содержимое</p></Sheet>)
    expect(screen.getByRole('dialog', { name: 'Принять' })).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Закрыть' }))
    await user.click(screen.getByText('Содержимое'))  // клик внутри — не закрывает
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('Toast', () => {
  function Btn() {
    const toast = useToast()
    return <button onClick={() => toast('Сохранено')}>go</button>
  }

  it('появляется и исчезает сам', async () => {
    vi.useFakeTimers()
    render(<ToastProvider><Btn /></ToastProvider>)
    act(() => screen.getByText('go').click())
    expect(screen.getByRole('status')).toHaveTextContent('Сохранено')
    act(() => vi.advanceTimersByTime(3300))
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    vi.useRealTimers()
  })
})
