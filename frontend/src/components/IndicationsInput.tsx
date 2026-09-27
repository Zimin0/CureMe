const HINTS = ['головная боль', 'температура', 'простуда', 'насморк', 'кашель', 'боль в горле', 'аллергия', 'изжога', 'диарея', 'порез', 'ожог', 'ушиб']

/** «От чего помогает»: текст через запятую плюс чипы с частыми болезнями. По этим словам работает подбор. */
export function IndicationsInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label?: string }) {
  const add = (t: string) => {
    const cur = value.split(',').map(s => s.trim()).filter(Boolean)
    if (!cur.includes(t)) onChange([...cur, t].join(', '))
  }
  return (
    <>
      <label className="field">
        {label && <span>{label}</span>}
        <textarea aria-label="От чего помогает" placeholder="Через запятую: головная боль, температура, зубная боль" value={value} onChange={e => onChange(e.target.value)} />
        <span className="hint">По этим словам работает подбор лекарства под болезнь</span>
      </label>
      <div className="chips wrap">
        {HINTS.map(t => <button type="button" key={t} className="chip" onClick={() => add(t)}>+ {t}</button>)}
      </div>
    </>
  )
}
