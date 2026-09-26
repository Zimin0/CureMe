import { afterEach, describe, expect, it, vi } from 'vitest'
import { avatarColor, daysText, fmtDate, fmtQty, plural, splitTags, STATUS_LABEL, subtitle, todayISO } from './format'
import { medicine } from './test/utils'

describe('plural — русские окончания', () => {
  it.each([
    [1, 'день'], [2, 'дня'], [4, 'дня'], [5, 'дней'], [11, 'дней'], [12, 'дней'], [14, 'дней'],
    [21, 'день'], [22, 'дня'], [25, 'дней'], [101, 'день'], [111, 'дней'], [0, 'дней'], [-1, 'день'],
  ])('%i → %s', (n, word) => expect(plural(n, 'день', 'дня', 'дней')).toBe(word))
})

describe('fmtQty', () => {
  it.each([[10, '10'], [0, '0'], [2.5, '2,5'], [0.25, '0,3'], [1.04, '1,0']])('%f → %s', (n, s) => expect(fmtQty(n)).toBe(s))
})

describe('daysText', () => {
  it.each([
    [-1, 'просрочено 1 день назад'],
    [-5, 'просрочено 5 дней назад'],
    [0, 'истекает сегодня'],
    [3, 'ещё 3 дня'],
    [21, 'ещё 21 день'],
  ])('%i → %s', (d, s) => expect(daysText(d)).toBe(s))
})

describe('fmtDate', () => {
  it('пустое значение — прочерк', () => {
    expect(fmtDate(null)).toBe('—')
    expect(fmtDate(undefined)).toBe('—')
  })
  it('дата без времени не сдвигается часовым поясом', () => {
    // «2027-05-01» как UTC в поясе UTC-5 превратилось бы в 30 апреля
    expect(fmtDate('2027-05-01')).toMatch(/^1 мая 2027/)
  })
})

describe('todayISO', () => {
  afterEach(() => vi.useRealTimers())
  it('отдаёт местную дату YYYY-MM-DD со смещением', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 11, 31, 23, 30))
    expect(todayISO()).toBe('2026-12-31')
    expect(todayISO(1)).toBe('2027-01-01')
    expect(todayISO(-365)).toBe('2025-12-31')
  })
})

it('subtitle склеивает только заполненные поля', () => {
  expect(subtitle(medicine({ form: 'Таблетки', dosage: null, manufacturer: 'Рекитт' }))).toBe('Таблетки · Рекитт')
  expect(subtitle(medicine({ form: null, dosage: null, manufacturer: null }))).toBe('')
})

it('splitTags режет по запятым, точкам с запятой и строкам', () => {
  expect(splitTags('головная боль, температура;\nкашель,, ')).toEqual(['головная боль', 'температура', 'кашель'])
})

it('avatarColor стабилен и циклится', () => {
  expect(avatarColor(0)).toBe(avatarColor(7))
  expect(avatarColor(1)).not.toBe(avatarColor(2))
})

it('у каждого статуса есть подпись', () => {
  expect(Object.keys(STATUS_LABEL).sort()).toEqual(['expired', 'expiring', 'low', 'ok', 'out'])
})
