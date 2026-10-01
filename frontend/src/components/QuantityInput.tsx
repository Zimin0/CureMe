import { Minus, Plus } from 'lucide-react'
import { useState } from 'react'
import { fmtQty } from '../format'

const COUNTABLE = ['таб', 'капс', 'шт', 'пак', 'амп']

export function Stepper({ value, onChange, min = 0, label }: { value: number; onChange: (v: number) => void; min?: number; label: string }) {
  // Пока поле редактируют, держим введённый текст как есть: иначе пустое поле сразу превращается в 0,
  // и этот ноль нельзя стереть.
  const [draft, setDraft] = useState<string | null>(null)
  const step = (v: number) => { setDraft(null); onChange(v) }
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" onClick={() => step(Math.max(min, value - 1))} aria-label="Меньше"><Minus size={16} /></button>
      <input type="number" min={min} step="any" inputMode="decimal" aria-label={label}
        value={draft ?? (Number.isFinite(value) ? value : '')}
        onFocus={e => e.target.select()}
        onChange={e => {
          const text = e.target.value
          setDraft(text)
          if (text.trim() !== '' && Number.isFinite(Number(text))) onChange(Math.max(min, Number(text)))
        }}
        onBlur={() => { if (draft !== null && draft.trim() === '') onChange(min); setDraft(null) }} />
      <button type="button" onClick={() => step(value + 1)} aria-label="Больше"><Plus size={16} /></button>
    </div>
  )
}

/**
 * Сколько лекарства в упаковке: либо «блистеров × таблеток в блистере», либо просто штук.
 * Наружу всегда отдаёт итоговое количество, а размер блистера — отдельно, чтобы его запомнить.
 */
export function QuantityInput({ unit, quantity, onQuantity, blisterSize, onBlisterSize, packSize }: {
  unit: string
  quantity: number
  onQuantity: (q: number) => void
  blisterSize: number | null
  onBlisterSize?: (n: number | null) => void
  packSize?: number | null
}) {
  const countable = COUNTABLE.includes(unit)
  // Поштучно проще всего: сколько таблеток осталось, столько и вписать. Блистеры — по желанию.
  const [mode, setMode] = useState<'blisters' | 'units'>('units')
  const per = blisterSize || 10
  const perLabel = `${unit === 'капс' ? 'Капсул' : 'Таблеток'} в блистере`
  const [blisters, setBlisters] = useState(() => Math.max(0, Math.round((quantity / per) * 2) / 2))

  const setBl = (b: number) => { setBlisters(b); onQuantity(b * per) }
  const setPer = (n: number) => { onBlisterSize?.(n || null); onQuantity(blisters * n) }
  const switchTo = (m: typeof mode) => {
    setMode(m)
    if (m === 'blisters') { onBlisterSize?.(per); setBl(Math.max(0, Math.round((quantity / per) * 2) / 2)) }
  }

  // Подписи — не <label>: внутри степпера первой идёт кнопка «−», и тап по подписи нажимал бы её.
  return (
    <div className="stack" style={{ gap: 10 }}>
      {countable && (
        <div className="segmented" role="tablist">
          <button type="button" role="tab" aria-selected={mode === 'blisters'} className={mode === 'blisters' ? 'on' : ''} onClick={() => switchTo('blisters')}>Блистерами</button>
          <button type="button" role="tab" aria-selected={mode === 'units'} className={mode === 'units' ? 'on' : ''} onClick={() => switchTo('units')}>Поштучно ({unit})</button>
        </div>
      )}
      {mode === 'blisters' && countable ? (
        <div className="grid-2">
          <div className="field"><span>Осталось блистеров</span><Stepper label="Осталось блистеров" value={blisters} onChange={setBl} /></div>
          <div className="field"><span>{perLabel}</span><Stepper label={perLabel} min={1} value={per} onChange={setPer} /></div>
        </div>
      ) : (
        <div className="field"><span>Осталось, {unit}</span><Stepper label={`Осталось, ${unit}`} value={quantity} onChange={onQuantity} /></div>
      )}
      <div className="row wrap" style={{ gap: 8 }}>
        <span className="badge accent">Итого: {fmtQty(quantity)} {unit}</span>
        {packSize ? (
          <button type="button" className="chip" style={{ height: 30 }} onClick={() => {
            onQuantity(packSize)
            if (mode === 'blisters') setBlisters(Math.round((packSize / per) * 2) / 2)
          }}>Целая пачка: {fmtQty(packSize)} {unit}</button>
        ) : null}
      </div>
    </div>
  )
}
