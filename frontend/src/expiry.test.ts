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

  it('reads MMYY without separator (0730 = July 2030)', () => {
    expect(iso('Годен до: 0730')).toBe('2030-07-31')
    expect(iso('Серия: 3589\nПроизв.: 0725\nГоден до: 0730')).toBe('2030-07-31')
    expect(iso('Серия 1240')).toBeNull() // 2040 — слишком далеко для срока годности
  })

  it('reads MMYYYY and YYYYMM without separator (092027, 202705)', () => {
    expect(iso('092027')).toBe('2027-09-30')
    expect(iso('Годен до 092027')).toBe('2027-09-30')
    expect(iso('202705')).toBe('2027-05-31')
    expect(iso('EXP 202705')).toBe('2027-05-31')
    expect(iso('Произв. 092024\nГоден до 092027')).toBe('2027-09-30')
    expect(iso('Серия 4602027051')).toBeNull() // часть длинного числа — не дата
    expect(iso('132027')).toBeNull() // 13-го месяца нет
  })

  // Настоящий вывод OCR с фото упаковок (английская модель читает кириллицу как латиницу).
  it('works on real OCR output from package photos', () => {
    expect(iso('SNFA8XJCIDOMY\n\nCepus:\n\n3589\n\nEh\n\nMpowuss.:\n\n0725\n\n[oper ao:\n\n0730\n\n||\n\nLL')).toBe('2030-07-31')
    expect(iso('CH:\n\n1473\n\nSTs\n\nropes ao: 31.01.2028\n\nCepwss 100070118\n\nBE')).toBe('2028-01-31')
    expect(iso('foper AO:\n\n51.01.2028')).toBe('2028-01-31')
    expect(iso('CH: 14785\n\n08257674\n\nCepwsiss 100070118\n\nropes ao: 31.01.2028')).toBe('2028-01-31')
  })

  it('returns null when there is no date', () => {
    expect(iso('Ларингобакт №30')).toBeNull()
    expect(iso('13.2027')).toBeNull()
  })
})
