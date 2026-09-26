import { Trash2 } from 'lucide-react'
import { CSSProperties, useState } from 'react'
import type { Category } from '../api'
import { Sheet } from './ui'

// Набор фиксированный: так значки одинаково выглядят на всех телефонах и не ломают вёрстку.
export const ICON_GROUPS: { title: string; icons: string[] }[] = [
  { title: 'Лекарства', icons: ['💊', '💉', '🩹', '🩺', '🌡️', '🧴', '🧪', '🩸', '🫙', '🧫', '⚕️', '🏥'] },
  { title: 'Тело', icons: ['❤️', '🫀', '🫁', '🧠', '🦷', '👁️', '👂', '👃', '🗣️', '🫄', '🦴', '💪', '🦶', '✋', '🧬', '🤰'] },
  { title: 'Самочувствие', icons: ['🤧', '🤒', '🤕', '🤢', '😴', '😮‍💨', '🥵', '🥶', '🧘', '🔥', '❄️', '⚡'] },
  { title: 'Разное', icons: ['🌼', '🌿', '🍃', '🍊', '🍋', '🍯', '🥛', '🌙', '☀️', '💧', '🧸', '👶', '👵', '🐾', '🚗', '✈️', '🏠', '⭐'] },
]
const ICONS = ICON_GROUPS.flatMap(g => g.icons)

// Два ряда: насыщенные и приглушённые оттенки. Старые цвета стандартных категорий сохранены в наборе.
export const COLORS = [
  '#e5484d', '#e54666', '#f76b15', '#f5a623', '#ffb224', '#30a46c', '#12a594', '#0f9d8a', '#0090ff', '#3e63dd', '#8e4ec6', '#d6409f',
  '#a1502d', '#8d7b3c', '#5b8c3a', '#2f7d7a', '#4f7fa8', '#6e56cf', '#b0578b', '#9e6a55', '#687076', '#2b2f33',
]

export type CategoryDraft = Partial<Category>

/** Окно создания и правки категории: название, значок, цвет. */
export function CategoryEditor({ initial, onSave, onDelete, onClose, busy }: {
  initial: CategoryDraft
  onSave: (c: CategoryDraft) => void
  onDelete?: (id: number) => void
  onClose: () => void
  busy?: boolean
}) {
  const [c, setC] = useState<CategoryDraft>({ icon: '💊', color: COLORS[6], ...initial })
  // Если у категории значок или цвет не из набора (задан раньше), показываем его первым, чтобы он не «пропал».
  const extraIcon = initial.icon && !ICONS.includes(initial.icon) ? initial.icon : undefined
  const extraColor = initial.color && !COLORS.includes(initial.color) ? initial.color : undefined
  return (
    <Sheet title={c.id ? 'Категория' : 'Новая категория'} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); onSave(c) }}>
        <input className="input" autoFocus required placeholder="Название" value={c.name ?? ''} onChange={e => setC({ ...c, name: e.target.value })} />
        <div className="cat-preview" aria-live="polite">
          <span className="chip cat-pick on" style={{ '--cat': c.color } as CSSProperties}>{c.icon} {c.name?.trim() || 'Название'}</span>
        </div>
        <div className="stack" style={{ gap: 8 }} role="radiogroup" aria-label="Значок">
          {extraIcon && <IconRow icons={[extraIcon]} value={c.icon} onPick={icon => setC({ ...c, icon })} />}
          {ICON_GROUPS.map(g => (
            <div key={g.title} className="stack" style={{ gap: 4 }}>
              <span className="small muted">{g.title}</span>
              <IconRow icons={g.icons} value={c.icon} onPick={icon => setC({ ...c, icon })} />
            </div>
          ))}
        </div>
        <div className="stack" style={{ gap: 4 }}>
          <span className="small muted">Цвет</span>
          <div className="row wrap" style={{ gap: 8 }} role="radiogroup" aria-label="Цвет">
            {[...(extraColor ? [extraColor] : []), ...COLORS].map(x => (
              <button type="button" key={x} role="radio" aria-checked={c.color === x} aria-label={x}
                className={`color-dot ${c.color === x ? 'active' : ''}`} style={{ background: x }} onClick={() => setC({ ...c, color: x })} />
            ))}
          </div>
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

function IconRow({ icons, value, onPick }: { icons: string[]; value?: string; onPick: (icon: string) => void }) {
  return (
    <div className="row wrap" style={{ gap: 6 }}>
      {icons.map(i => (
        <button type="button" key={i} role="radio" aria-checked={value === i} aria-label={i}
          className={`emoji-pick ${value === i ? 'active' : ''}`} onClick={() => onPick(i)}>{i}</button>
      ))}
    </div>
  )
}
