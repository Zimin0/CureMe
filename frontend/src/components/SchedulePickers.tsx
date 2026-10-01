import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import { DAY_PRESETS, DAY_SHORT, fmtMinute, TIME_PRESETS } from '../schedule'
import { TimeSlider } from './TimeSlider'

const sameDays = (a: number[], b: number[]) => a.length === b.length && a.every(d => b.includes(d))

/** Дни недели чипами: можно выбрать любые или нажать готовый набор («Будни»). Переключение — одним нажатием. */
export function DayChips({ value, onChange, presets = true, only = null }: {
  value: number[]; onChange: (days: number[]) => void; presets?: boolean
  only?: number[] | null  // показывать только эти дни (для «убрать серию»)
}) {
  const days = only ?? [0, 1, 2, 3, 4, 5, 6]
  const toggle = (d: number) => onChange(value.includes(d) ? value.filter(x => x !== d) : [...value, d].sort())
  return (
    <div className="stack" style={{ gap: 8 }}>
      <div className="chips wrap" role="group" aria-label="Дни недели">
        {days.map(d => (
          <button key={d} type="button" className={`chip day-chip${value.includes(d) ? ' active' : ''}`} aria-pressed={value.includes(d)}
            onClick={() => toggle(d)}>{DAY_SHORT[d]}</button>
        ))}
      </div>
      {presets && (
        <div className="chips wrap">
          {DAY_PRESETS.map(p => (
            <button key={p.label} type="button" className={`chip${sameDays(value, p.days) ? ' active' : ''}`} onClick={() => onChange(p.days)}>{p.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Время приёма: утро/день/вечер/на ночь одним нажатием или ползунок для любого времени. Приёмов в день может быть несколько. */
export function TimesPicker({ value, onChange, max = 12 }: { value: number[]; onChange: (times: number[]) => void; max?: number }) {
  const [custom, setCustom] = useState(12 * 60)
  const add = (m: number) => value.length < max && !value.includes(m) && onChange([...value, m].sort((a, b) => a - b))
  const remove = (m: number) => onChange(value.filter(x => x !== m))
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="chips wrap" aria-label="Готовое время">
        {TIME_PRESETS.map(p => (
          <button key={p.label} type="button" className={`chip${value.includes(p.minute) ? ' active' : ''}`}
            onClick={() => (value.includes(p.minute) ? remove(p.minute) : add(p.minute))}>
            {p.label} <span className="count">{fmtMinute(p.minute)}</span>
          </button>
        ))}
      </div>
      <TimeSlider value={custom} onChange={setCustom} label="Своё время" />
      <button type="button" className="btn ghost" disabled={value.includes(custom) || value.length >= max} onClick={() => add(custom)}>
        <Plus size={16} />Добавить {fmtMinute(custom)}
      </button>
      {value.length > 0 && (
        <div className="chips wrap" aria-label="Выбранное время">
          {value.map(m => (
            <span key={m} className="chip active time-tag">{fmtMinute(m)}
              <button type="button" aria-label={`Убрать ${fmtMinute(m)}`} onClick={() => remove(m)}><X size={14} /></button>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
