import { describe, expect, it } from 'vitest'
import { safeNext } from './redirect'

describe('safeNext: куда вести после входа', () => {
  it('пропускает пути внутри сайта вместе с параметрами', () => {
    expect(safeNext('/join/ABCD2345')).toBe('/join/ABCD2345')
    expect(safeNext('/medicines?filter=expired#top')).toBe('/medicines?filter=expired#top')
  })

  it('без адреса или с пустым — на главную', () => {
    expect(safeNext(null)).toBe('/')
    expect(safeNext(undefined)).toBe('/')
    expect(safeNext('')).toBe('/')
  })

  it.each([
    ['чужой сайт целиком', 'https://evil.example/phish'],
    ['схема без слэшей', 'javascript:alert(1)'],
    ['двойной слэш', '//evil.example/phish'],
    ['обратный слэш (обход React Router)', '/\\evil.example/phish'],
    ['обратный слэш в середине', '/join/..\\evil.example'],
    ['таб между слэшами', '/\t/evil.example'],
    ['перевод строки между слэшами', '/\n/evil.example'],
    ['относительный путь без слэша', 'evil.example/phish'],
  ])('отбрасывает: %s', (_name, raw) => {
    expect(safeNext(raw)).toBe('/')
  })
})
