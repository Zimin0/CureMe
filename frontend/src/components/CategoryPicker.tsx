import type { CSSProperties } from 'react'
import type { Category } from '../api'

export const MAX_CATEGORIES = 3

/** Выбор до трёх категорий. Порядок важен: первая выбранная — основная (её значок и цвет в списках). */
export function CategoryPicker({ categories, value, onChange }: {
  categories: Category[]
  value: number[]
  onChange: (ids: number[]) => void
}) {
  const full = value.length >= MAX_CATEGORIES
  const toggle = (id: number) =>
    onChange(value.includes(id) ? value.filter(x => x !== id) : full ? value : [...value, id])
  return (
    <div className="field">
      <span>Категории <span className="muted">· до {MAX_CATEGORIES}, первая — основная</span></span>
      <div className="chips wrap" role="group" aria-label="Категории">
        {categories.map(c => {
          const pos = value.indexOf(c.id)
          const on = pos >= 0
          return (
            <button type="button" key={c.id} aria-pressed={on} disabled={!on && full}
              className={`chip cat-pick ${on ? 'on' : ''}`} style={{ '--cat': c.color } as CSSProperties}
              onClick={() => toggle(c.id)}>
              {on && <span className="cat-pos" title={pos === 0 ? 'Основная' : undefined}>{pos + 1}</span>}
              {c.icon} {c.name}
            </button>
          )
        })}
      </div>
    </div>
  )
}
