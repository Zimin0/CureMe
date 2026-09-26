import { describe, expect, it } from 'vitest'
import { parseExpiry, toISO } from './expiry'

const iso = (t: string) => { const d = parseExpiry(t); return d ? toISO(d) : null }

describe('parseExpiry', () => {
  it.each([
    ['05.2027', '2027-05-31'],
    ['годен до 05.2027', '2027-05-31'],
    ['ГОДЕН ДО: 31.05.2027', '2027-05-31'],
    ['EXP 05/2027', '2027-05-31'],
    ['exp 02/28', '2028-02-29'],
    ['до 11/27', '2027-11-30'],
    ['2027-05', '2027-05-31'],
    ['2027-05-15', '2027-05-15'],
    ['31.12.26', '2026-12-31'],
    ['май 2027', '2027-05-31'],
    ['MAY 2027', '2027-05-31'],
    ['12 2026', '2026-12-31'],
  ])('%s → %s', (text, want) => expect(iso(text)).toBe(want))

  it('picks expiry over manufacture date', () => {
    expect(iso('Дата изг. 05.2024\nГоден до 05.2027')).toBe('2027-05-31')
    expect(iso('Годен до 04.2026 Изготовлено 04.2023')).toBe('2026-04-30')
    expect(iso('СЕРИЯ 120524 05.2024 05.2027')).toBe('2027-05-31')
  })

  it('fixes typical OCR mistakes', () => {
    expect(iso('ГОДЕН ДО O5.2O27')).toBe('2027-05-31')
    expect(iso('EXP 1l.2027')).toBe('2027-11-30')
  })

  it('returns null when there is no date', () => {
    expect(iso('Ларингобакт №30')).toBeNull()
    expect(iso('13.2027')).toBeNull()
  })
})
