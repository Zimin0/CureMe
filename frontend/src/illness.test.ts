import { expect, it } from 'vitest'
import { daysIn, monthGrid, orderedRange, periodLabel } from './illness'

it('период упорядочивается, даже если тянули назад', () => {
  expect(orderedRange('2026-10-09', '2026-10-05')).toEqual(['2026-10-05', '2026-10-09'])
  expect(orderedRange('2026-10-05', '2026-10-05')).toEqual(['2026-10-05', '2026-10-05'])
})

it('считает дни и подписывает период', () => {
  const now = new Date(2026, 9, 9)
  expect(daysIn('2026-10-05', '2026-10-09')).toBe(5)
  expect(periodLabel('2026-10-05', '2026-10-05', now)).toBe('5 октября')
  expect(periodLabel('2026-10-05', '2026-10-09', now)).toBe('5 – 9 октября')
  expect(periodLabel('2026-09-28', '2026-10-02', now)).toBe('28 сентября – 2 октября')
  expect(periodLabel('2025-12-30', '2026-01-02', now)).toContain('2025')
})

it('сетка месяца начинается с понедельника и кратна неделе', () => {
  const grid = monthGrid(2026, 9)  // октябрь 2026: 1 октября — четверг
  expect(grid[0].slice(0, 3)).toEqual([null, null, null])
  expect(grid[0][3]).toBe('2026-10-01')
  expect(grid.flat().filter(Boolean)).toHaveLength(31)
  expect(grid.every(w => w.length === 7)).toBe(true)
})
