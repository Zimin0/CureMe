import { describe, expect, it } from 'vitest'
import { shelfAt } from './ShelfMap'

describe('shelfAt', () => {
  const plan = { height: 1, shelves: [{ id: 'a', name: 'Верх', x: 0, y: 0, w: 1, h: 0.4 }, { id: 'b', name: 'Низ', x: 0, y: 0.5, w: 1, h: 0.4 }] }
  it('находит полку по центру круга', () => {
    expect(shelfAt(plan, 0.5, 0.2)?.name).toBe('Верх')
    expect(shelfAt(plan, 0.5, 0.45)).toBeUndefined()
    expect(shelfAt(undefined, 0.5, 0.2)).toBeUndefined()
  })
})
