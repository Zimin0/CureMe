import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExpiryInput } from './ExpiryInput'

// Настоящий OCR (tesseract, ~8 МБ wasm) в unit-тестах не нужен: подменяем модуль целиком.
vi.mock('../ocr', () => ({ recognizeText: vi.fn() }))
import { recognizeText } from '../ocr'
const ocr = vi.mocked(recognizeText)

function Harness({ hint }: { hint?: string }) {
  const [v, setV] = useState<string | null>(null)
  return <><ExpiryInput value={v} onChange={setV} hint={hint} /><output data-testid="value">{v ?? 'пусто'}</output></>
}

const value = () => screen.getByTestId('value').textContent
const photo = () => new File(['x'], 'exp.jpg', { type: 'image/jpeg' })

beforeEach(() => {
  ocr.mockReset()
  URL.createObjectURL = vi.fn(() => 'blob:preview')
})

describe('ExpiryInput', () => {
  it('обычный выбор даты', async () => {
    const user = userEvent.setup()
    const { container } = render(<Harness />)
    const date = container.querySelector('input[type=date]')!
    await user.type(date, '2027-05-31')
    expect(value()).toBe('2027-05-31')
  })

  it('ввод текстом как на упаковке', async () => {
    const user = userEvent.setup()
    render(<Harness hint="Взято из кода" />)
    expect(screen.getByText('Взято из кода')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ввести текстом' }))
    await user.type(screen.getByPlaceholderText(/Как на упаковке/), 'EXP 05/27')
    expect(value()).toBe('2027-05-31')
    expect(screen.getByText(/Годен до 31 мая 2027/)).toBeInTheDocument()
  })

  it('непонятный текст — подсказка, значение не меняется', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Ввести текстом' }))
    await user.type(screen.getByPlaceholderText(/Как на упаковке/), 'когда-нибудь')
    expect(value()).toBe('пусто')
    expect(screen.getByText(/Не понял дату/)).toBeInTheDocument()
  })

  it('фото: распознанная дата подставляется с просьбой проверить', async () => {
    ocr.mockImplementation(async (_file, progress) => { progress?.(0.5); return 'Серия 1234\nГоден до 11.2028' })
    const user = userEvent.setup()
    const { container } = render(<Harness />)
    await user.upload(container.querySelector('input[type=file]') as HTMLInputElement, photo())
    expect(await screen.findByText(/проверьте, что распознано верно/)).toBeInTheDocument()
    expect(value()).toBe('2028-11-30')
    expect(screen.getByText(/Распознано: Серия 1234/)).toBeInTheDocument()
    expect(screen.getByAltText('Фото срока годности')).toHaveAttribute('src', 'blob:preview')
  })

  it('фото без даты — предупреждение', async () => {
    ocr.mockResolvedValue('какой-то текст без даты')
    const user = userEvent.setup()
    const { container } = render(<Harness />)
    await user.upload(container.querySelector('input[type=file]') as HTMLInputElement, photo())
    expect(await screen.findByText(/Дату на фото не нашли/)).toBeInTheDocument()
    expect(value()).toBe('пусто')
  })

  it('ошибка OCR не ломает форму', async () => {
    ocr.mockRejectedValue(new Error('wasm упал'))
    const user = userEvent.setup()
    const { container } = render(<Harness />)
    await user.upload(container.querySelector('input[type=file]') as HTMLInputElement, photo())
    expect(await screen.findByText(/Не удалось распознать фото/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сфотографировать срок' })).toBeEnabled()
  })
})
