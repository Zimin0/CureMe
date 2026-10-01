import { Minus, Plus } from 'lucide-react'
import { fmtMinute } from '../schedule'

const STEP = 5

/** Выбор времени ползунком: крупные часы по центру, шаг 5 минут, кнопки ±15 минут для точной подстройки. */
export function TimeSlider({ value, onChange, label = 'Время приёма' }: { value: number; onChange: (m: number) => void; label?: string }) {
  const nudge = (d: number) => onChange(Math.min(1435, Math.max(0, value + d)))
  return (
    <div className="time-slider" role="group" aria-label={label}>
      <div className="row" style={{ justifyContent: 'center', gap: 16 }}>
        <button type="button" className="icon-btn" onClick={() => nudge(-15)} aria-label="Раньше на 15 минут"><Minus size={18} /></button>
        <div className="time-readout" aria-live="polite">{fmtMinute(value)}</div>
        <button type="button" className="icon-btn" onClick={() => nudge(15)} aria-label="Позже на 15 минут"><Plus size={18} /></button>
      </div>
      <input type="range" min={0} max={1435} step={STEP} value={value} aria-label={label}
        onChange={e => onChange(Number(e.target.value))} />
      <div className="row between faint small"><span>00:00</span><span>12:00</span><span>23:55</span></div>
    </div>
  )
}
