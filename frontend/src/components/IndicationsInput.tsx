import { useQuery } from '@tanstack/react-query'
import { api } from '../api'

/** Быстрые подсказки к полю «От чего помогает». Список общий, его задаёт администратор. */
export function useIndicationHints() {
  return useQuery({ queryKey: ['indication-hints'], queryFn: () => api<string[]>('/indication-hints'), staleTime: 5 * 60_000 })
}

/** «От чего помогает»: текст через запятую плюс чипы с частыми болезнями. По этим словам работает подбор. */
export function IndicationsInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label?: string }) {
  const hints = useIndicationHints().data ?? []
  const add = (t: string) => {
    const cur = value.split(',').map(s => s.trim()).filter(Boolean)
    if (!cur.some(c => c.toLowerCase() === t.toLowerCase())) onChange([...cur, t].join(', '))
  }
  return (
    <>
      <label className="field">
        {label && <span>{label}</span>}
        <textarea aria-label="От чего помогает" placeholder="Через запятую: головная боль, температура, зубная боль" value={value} onChange={e => onChange(e.target.value)} />
        <span className="hint">По этим словам работает подбор лекарства под болезнь</span>
      </label>
      {hints.length > 0 && (
        <div className="chips wrap">
          {hints.map(t => <button type="button" key={t} className="chip" onClick={() => add(t)}>+ {t}</button>)}
        </div>
      )}
    </>
  )
}
