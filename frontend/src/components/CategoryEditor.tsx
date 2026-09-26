import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { Category } from '../api'
import { Sheet } from './ui'

const ICONS = ['💊', '🩹', '🌡️', '🤧', '🗣️', '🌼', '🫄', '❤️', '🩺', '🍊', '🌙', '🧸', '👁️', '🦷', '🧴', '💉', '🐾', '🧘']
export const COLORS = ['#e5484d', '#f76b15', '#ffb224', '#30a46c', '#12a594', '#0090ff', '#3e63dd', '#8e4ec6', '#d6409f', '#687076']

export type CategoryDraft = Partial<Category>

/** Окно создания и правки категории: название, значок, цвет. */
export function CategoryEditor({ initial, onSave, onDelete, onClose, busy }: {
  initial: CategoryDraft
  onSave: (c: CategoryDraft) => void
  onDelete?: (id: number) => void
  onClose: () => void
  busy?: boolean
}) {
  const [c, setC] = useState<CategoryDraft>({ icon: '💊', color: COLORS[4], ...initial })
  return (
    <Sheet title={c.id ? 'Категория' : 'Новая категория'} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); onSave(c) }}>
        <input className="input" autoFocus required placeholder="Название" value={c.name ?? ''} onChange={e => setC({ ...c, name: e.target.value })} />
        <div className="row wrap" style={{ gap: 6 }}>
          {ICONS.map(i => <button type="button" key={i} className={`emoji-pick ${c.icon === i ? 'active' : ''}`} onClick={() => setC({ ...c, icon: i })}>{i}</button>)}
        </div>
        <div className="row wrap" style={{ gap: 8 }}>
          {COLORS.map(x => <button type="button" key={x} aria-label={x} className={`color-dot ${c.color === x ? 'active' : ''}`} style={{ background: x }} onClick={() => setC({ ...c, color: x })} />)}
        </div>
        <p className="muted small">Категории общие: изменения увидят все семьи.</p>
        <button className="btn primary block" disabled={busy}>Сохранить</button>
        {c.id && onDelete && (
          <button type="button" className="btn danger block" disabled={busy}
            onClick={() => confirm(`Удалить «${c.name}» у всех семей? Лекарства останутся без категории.`) && onDelete(c.id!)}>
            <Trash2 size={16} />Удалить
          </button>
        )}
      </form>
    </Sheet>
  )
}
