import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { expect, test } from 'vitest'
import type { Category } from '../api'
import { CategoryPicker } from './CategoryPicker'

const cat = (id: number, name: string): Category => ({ id, name, icon: '💊', color: '#0f9d8a', medicine_count: 0 })
const CATS = [cat(1, 'Обезболивающие'), cat(2, 'Жаропонижающие'), cat(3, 'Простуда'), cat(4, 'Аллергия')]

function Harness({ initial = [] as number[] }) {
  const [ids, setIds] = useState(initial)
  return <><CategoryPicker categories={CATS} value={ids} onChange={setIds} /><output>{ids.join(',')}</output></>
}

test('выбирает до трёх категорий в порядке нажатия, первая — основная', async () => {
  const user = userEvent.setup()
  render(<Harness />)
  const btn = (name: string) => screen.getByRole('button', { name: new RegExp(name) })
  await user.click(btn('Простуда'))
  await user.click(btn('Обезболивающие'))
  await user.click(btn('Аллергия'))
  expect(screen.getByRole('status').textContent).toBe('3,1,4')
  expect(btn('Простуда').textContent).toMatch(/^1/)  // номер 1 у основной

  expect(btn('Жаропонижающие')).toBeDisabled()        // четвёртую выбрать нельзя
  await user.click(btn('Простуда'))                   // снимаем основную — основной становится следующая
  expect(screen.getByRole('status').textContent).toBe('1,4')
  expect(btn('Жаропонижающие')).toBeEnabled()
  expect(btn('Обезболивающие')).toHaveAttribute('aria-pressed', 'true')
})
