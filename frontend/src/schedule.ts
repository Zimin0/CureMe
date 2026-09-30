// Общие мелочи расписания приёма. Время в расписании московское, как и на сервере (backend/app/schedule.py).
import type { Schedule } from './api'

export const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
export const DAY_LONG = ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']
export const EVERY_DAY = [0, 1, 2, 3, 4, 5, 6]
export const DAY_PRESETS: { label: string; days: number[] }[] = [
  { label: 'Каждый день', days: EVERY_DAY },
  { label: 'Будни', days: [0, 1, 2, 3, 4] },
  { label: 'Выходные', days: [5, 6] },
]
/** Быстрый выбор времени: утро, день, вечер, на ночь. */
export const TIME_PRESETS: { label: string; minute: number }[] = [
  { label: 'Утро', minute: 8 * 60 },
  { label: 'День', minute: 13 * 60 },
  { label: 'Вечер', minute: 19 * 60 },
  { label: 'На ночь', minute: 22 * 60 },
]
export const COURSES: { label: string; days: number | null }[] = [
  { label: 'Бессрочно', days: null },
  { label: '7 дней', days: 7 },
  { label: '14 дней', days: 14 },
  { label: '30 дней', days: 30 },
]

export function fmtMinute(m: number) {
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

function parts(): Record<string, string> {
  const f = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Moscow', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  })
  return Object.fromEntries(f.formatToParts(new Date()).map(p => [p.type, p.value]))
}
/** Сегодня по Москве: '2026-09-30'. */
export function mskToday() { const p = parts(); return `${p.year}-${p.month}-${p.day}` }
/** Сколько минут прошло с полуночи по Москве. */
export function mskMinute() { const p = parts(); return Number(p.hour) * 60 + Number(p.minute) }

export function addDays(iso: string, n: number) {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10)
}
/** День недели даты: 0 — понедельник. */
export function weekdayOf(iso: string) { return (new Date(iso + 'T00:00:00Z').getUTCDay() + 6) % 7 }
export function mondayOf(iso: string) { return addDays(iso, -weekdayOf(iso)) }
export function fmtDay(iso: string) {
  return new Date(iso + 'T00:00:00Z').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' })
}

/** «Пн, Ср, Пт» — или «Каждый день», «Будни», «Выходные». */
export function daysText(days: number[]) {
  const set = [...new Set(days)].sort((a, b) => a - b)
  for (const p of DAY_PRESETS) if (p.days.length === set.length && p.days.every((d, i) => d === set[i])) return p.label
  return set.map(d => DAY_SHORT[d]).join(', ')
}

/** Кратко про назначение: «Будни · 08:00, 20:00». Если время у дней разное, перечисляет дни отдельно. */
export function scheduleText(s: Schedule) {
  const byDay = new Map<number, number[]>()
  for (const x of s.slots) byDay.set(x.weekday, [...(byDay.get(x.weekday) ?? []), x.minute].sort((a, b) => a - b))
  const groups = new Map<string, number[]>()
  for (const [d, ms] of byDay) groups.set(ms.join(','), [...(groups.get(ms.join(',')) ?? []), d])
  return [...groups].map(([key, days]) => `${daysText(days)} · ${key.split(',').map(m => fmtMinute(Number(m))).join(', ')}`).join('; ')
}

export function repeatText(s: Schedule) {
  const every = s.every_weeks === 1 ? '' : s.every_weeks === 2 ? 'через неделю' : `раз в ${s.every_weeks} нед.`
  const until = s.end_date ? `до ${fmtDay(s.end_date)}` : ''
  return [every, until].filter(Boolean).join(', ')
}
