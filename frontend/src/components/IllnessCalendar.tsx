import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { dayKey, inRange, monthGrid, orderedRange, parseDay } from '../illness'

const WEEK = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

export interface Period { from: string; to: string }

/**
 * Календарь месяца. Клик по дню выбирает один день, зажать и протянуть — период.
 * То же работает пальцем на телефоне. marked — дни, у которых уже есть записи.
 * С клавиатуры: Enter или пробел выбирает день, Shift + Enter продолжает период от выбранного дня.
 */
export function IllnessCalendar({ value, onChange, marked }: {
  value: Period | null; onChange: (p: Period) => void; marked: Set<string>
}) {
  const today = dayKey(new Date())
  const start = value ? parseDay(value.from) : new Date()
  const [shown, setShown] = useState({ y: start.getFullYear(), m: start.getMonth() })
  const anchor = useRef<string | null>(null)
  const [dragging, setDragging] = useState(false)

  // Мышь или палец отпустили где угодно (даже вне календаря) — протягивание закончено.
  useEffect(() => {
    if (!dragging) return
    const stop = () => { anchor.current = null; setDragging(false) }
    window.addEventListener('pointerup', stop)
    window.addEventListener('pointercancel', stop)
    return () => { window.removeEventListener('pointerup', stop); window.removeEventListener('pointercancel', stop) }
  }, [dragging])

  const move = (delta: number) => {
    const d = new Date(shown.y, shown.m + delta, 1)
    setShown({ y: d.getFullYear(), m: d.getMonth() })
  }
  const pick = (a: string, b: string) => { const [from, to] = orderedRange(a, b); onChange({ from, to }) }
  const raw = new Date(shown.y, shown.m, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' }).replace(/\s*г\.$/, '')
  const title = raw[0].toUpperCase() + raw.slice(1)

  // У касания указатель остаётся на первой клетке, поэтому ищем клетку под пальцем по координатам.
  const overDay = (e: React.PointerEvent) =>
    (document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null)?.closest<HTMLElement>('[data-day]')?.dataset.day

  return (
    <div className="ill-cal" aria-label="Календарь болезней">
      <div className="row between ill-cal-head">
        <button type="button" className="icon-btn" onClick={() => move(-1)} aria-label="Предыдущий месяц"><ChevronLeft size={18} /></button>
        <b className="ill-cal-title">{title}</b>
        <button type="button" className="icon-btn" onClick={() => move(1)} aria-label="Следующий месяц"><ChevronRight size={18} /></button>
      </div>
      <div className="ill-cal-week" aria-hidden="true">{WEEK.map(w => <span key={w}>{w}</span>)}</div>
      <div
        className="ill-cal-grid" role="grid"
        onPointerMove={e => { if (anchor.current) { const d = overDay(e); if (d) pick(anchor.current, d) } }}
      >
        {monthGrid(shown.y, shown.m).map((week, i) => (
          <div className="ill-cal-row" role="row" key={i}>
            {week.map((day, j) => {
              if (!day) return <span key={j} className="ill-day empty" role="gridcell" />
              const sel = !!value && inRange(day, value.from, value.to)
              const edge = sel && (day === value!.from || day === value!.to)
              const cls = ['ill-day', sel && 'sel', edge && 'edge', day === today && 'today', marked.has(day) && 'marked'].filter(Boolean).join(' ')
              return (
                <button
                  key={day} type="button" role="gridcell" data-day={day} className={cls} aria-selected={sel}
                  aria-label={parseDay(day).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })}
                  onPointerDown={e => {
                    if (e.button !== 0 && e.pointerType === 'mouse') return
                    anchor.current = day
                    setDragging(true)
                    pick(day, day)
                  }}
                  onKeyDown={e => {
                    if (e.key !== 'Enter' && e.key !== ' ') return
                    e.preventDefault()
                    if (e.shiftKey && value) pick(value.from, day)
                    else pick(day, day)
                  }}
                >{parseDay(day).getDate()}</button>
              )
            })}
          </div>
        ))}
      </div>
      <p className="hint ill-cal-hint">Нажмите на день или протяните пальцем (мышью) по нескольким дням.</p>
    </div>
  )
}
