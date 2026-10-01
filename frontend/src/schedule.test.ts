import { expect, it } from 'vitest'
import type { Schedule } from './api'
import { addDays, daysText, fmtMinute, mondayOf, repeatText, scheduleText, weekdayOf } from './schedule'

const sched = (over: Partial<Schedule> = {}): Schedule => ({
  id: 1, medicine_id: 1, medicine_name: 'Амепрозол', unit: 'таб', amount: 1, start_date: '2026-10-05', end_date: null, every_weeks: 1,
  slots: [], ...over,
})

it('время и даты', () => {
  expect(fmtMinute(0)).toBe('00:00')
  expect(fmtMinute(16 * 60 + 5)).toBe('16:05')
  expect(weekdayOf('2026-10-05')).toBe(0)  // понедельник
  expect(weekdayOf('2026-10-11')).toBe(6)  // воскресенье
  expect(mondayOf('2026-10-11')).toBe('2026-10-05')
  expect(addDays('2026-10-30', 3)).toBe('2026-11-02')
})

it('дни: готовые наборы и перечисление', () => {
  expect(daysText([0, 1, 2, 3, 4, 5, 6])).toBe('Каждый день')
  expect(daysText([4, 0, 3, 2, 1])).toBe('Будни')
  expect(daysText([6, 5])).toBe('Выходные')
  expect(daysText([1, 3])).toBe('Вт, Чт')
})

it('кратко про назначение: одинаковое время склеивается, разное — через точку с запятой', () => {
  const every = [0, 1, 2, 3, 4, 5, 6].flatMap(d => [480, 1200].map((minute, i) => ({ id: d * 2 + i, weekday: d, minute })))
  expect(scheduleText(sched({ slots: every }))).toBe('Каждый день · 08:00, 20:00')
  const mixed = [{ id: 1, weekday: 1, minute: 960 }, { id: 2, weekday: 3, minute: 480 }]
  expect(scheduleText(sched({ slots: mixed }))).toBe('Вт · 16:00; Чт · 08:00')
})

it('повтор и срок курса', () => {
  expect(repeatText(sched())).toBe('')
  expect(repeatText(sched({ every_weeks: 2, end_date: '2026-11-01' }))).toBe('через неделю, до 1 ноября')
})
