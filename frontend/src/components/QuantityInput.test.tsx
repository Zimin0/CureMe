import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { QuantityInput } from './QuantityInput'

/** Обёртка с настоящим состоянием, как в форме лекарства. */
function Harness({ unit = 'таб', initial = 20, blister = 10 as number | null, packSize = null as number | null, spy = vi.fn() }) {
  const [q, setQ] = useState(initial)
  const [b, setB] = useState<number | null>(blister)
  return (
    <QuantityInput unit={unit} quantity={q} onQuantity={v => { setQ(v); spy(v) }} blisterSize={b} onBlisterSize={setB} packSize={packSize} />
  )
}

const total = () => screen.getByText(/^Итого:/).textContent

describe('QuantityInput', () => {
  it('по умолчанию открыт режим «Поштучно», даже если размер блистера известен', () => {
    render(<Harness />)
    expect(screen.getByRole('tab', { name: 'Поштучно (таб)' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('spinbutton', { name: 'Осталось, таб' })).toHaveValue(20)
    expect(total()).toBe('Итого: 20 таб')
  })

  it('в режиме «Блистерами» количество пересчитывается в блистеры', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
    expect(screen.getByRole('spinbutton', { name: 'Осталось блистеров' })).toHaveValue(2)
    expect(total()).toBe('Итого: 20 таб')
  })

  it('кнопки + и − меняют число блистеров и итог', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
    const [more] = screen.getAllByRole('button', { name: 'Больше' })
    await user.click(more)
    expect(total()).toBe('Итого: 30 таб')
    const [less] = screen.getAllByRole('button', { name: 'Меньше' })
    await user.click(less)
    await user.click(less)
    await user.click(less)
    await user.click(less)  // ниже нуля не уходит
    expect(total()).toBe('Итого: 0 таб')
  })

  it('размер блистера пересчитывает итог', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
    const per = screen.getByRole('spinbutton', { name: 'Таблеток в блистере' })
    await user.clear(per)
    await user.type(per, '14')
    expect(total()).toBe('Итого: 28 таб')
  })

  it('поле можно стереть и ввести новое число (ноль не «залипает»)', async () => {
    const user = userEvent.setup()
    render(<Harness blister={null} />)
    const input = screen.getByRole('spinbutton', { name: 'Осталось, таб' })
    await user.clear(input)
    expect(input).toHaveValue(null)
    await user.type(input, '7')
    expect(total()).toBe('Итого: 7 таб')
  })

  it('пустое поле при уходе фокуса становится минимумом', async () => {
    const user = userEvent.setup()
    render(<Harness blister={null} />)
    const input = screen.getByRole('spinbutton', { name: 'Осталось, таб' })
    await user.clear(input)
    await user.tab()
    expect(input).toHaveValue(0)
  })

  it('дробные остатки: пол-блистера', async () => {
    const user = userEvent.setup()
    render(<Harness initial={15} />)
    await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
    expect(screen.getByRole('spinbutton', { name: 'Осталось блистеров' })).toHaveValue(1.5)
    await user.click(screen.getByRole('tab', { name: 'Поштучно (таб)' }))
    expect(screen.getByRole('spinbutton', { name: 'Осталось, таб' })).toHaveValue(15)
  })

  it('кнопка «Целая пачка» ставит размер упаковки', async () => {
    const user = userEvent.setup()
    render(<Harness initial={3} packSize={30} />)
    await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
    await user.click(screen.getByRole('button', { name: 'Целая пачка: 30 таб' }))
    expect(total()).toBe('Итого: 30 таб')
    expect(screen.getByRole('spinbutton', { name: 'Осталось блистеров' })).toHaveValue(3)
  })

  it('для сиропа нет блистеров', () => {
    render(<Harness unit="мл" initial={100} />)
    expect(screen.queryByRole('tab')).not.toBeInTheDocument()
    expect(screen.getByRole('spinbutton', { name: 'Осталось, мл' })).toHaveValue(100)
  })
})

it('тап по подписи поля ничего не меняет (раньше срабатывала кнопка «−»)', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  await user.click(screen.getByRole('tab', { name: 'Блистерами' }))
  await user.click(screen.getByText('Осталось блистеров'))
  await user.click(screen.getByText('Таблеток в блистере'))
  expect(total()).toBe('Итого: 20 таб')
})
