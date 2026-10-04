import { useQuery } from '@tanstack/react-query'
import { Info, Search } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, SuggestResult } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { Empty, MedIcon, Spinner } from '../components/ui'
import { fmtQty, subtitle } from '../format'
import { MEDICAL_NOTE_MORE, MEDICAL_NOTE_SHORT } from '../legal'
import { useRequirePlus } from '../plan'

export function Find() {
  const fam = useFamilyPath()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const [input, setInput] = useState(q)
  const [noteOpen, setNoteOpen] = useState(false)
  const { me, familyId, setFamilyId } = useAuth()
  const requirePlus = useRequirePlus()
  const several = (me?.families.length ?? 0) > 1
  const all = several && params.get('scope') === 'all'

  const conditions = useQuery({ queryKey: ['conditions'], queryFn: () => api<string[]>('/conditions'), staleTime: Infinity })
  const res = useQuery({
    queryKey: ['suggest', fam(''), q, all],
    queryFn: () => api<SuggestResult>(fam(`/suggest?condition=${encodeURIComponent(q)}${all ? '&scope=all' : ''}`)),
    enabled: q.trim().length >= 2,
  })

  const go = (v: string) => { setInput(v); setParams(v ? { q: v, ...(all ? { scope: 'all' } : {}) } : {}, { replace: true }) }
  const setScope = (on: boolean) => {
    const next = new URLSearchParams(params)
    on ? next.set('scope', 'all') : next.delete('scope')
    setParams(next, { replace: true })
  }
  const submit = (e: FormEvent) => { e.preventDefault(); go(input.trim()) }

  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <div className="page-head">
        <div>
          <h1>Что есть дома от…</h1>
          <p className="sub">Напишите, что беспокоит. Посмотрим, что из лекарств есть дома.</p>
        </div>
      </div>

      <div className="alert warn small">
        <Info size={18} style={{ flexShrink: 0 }} />
        <span>
          {MEDICAL_NOTE_SHORT}{' '}
          <button type="button" className="linklike" aria-expanded={noteOpen} onClick={() => setNoteOpen(v => !v)}>
            {noteOpen ? 'Свернуть' : 'Подробнее'}
          </button>
          {noteOpen && <> {MEDICAL_NOTE_MORE}</>}
        </span>
      </div>

      <form onSubmit={submit} className="row">
        <label className="search grow">
          <Search size={18} />
          <input className="input" type="search" placeholder="Например: болит голова" value={input} onChange={e => setInput(e.target.value)} />
        </label>
        <button className="btn primary" style={{ height: 50 }}>Найти</button>
      </form>

      {several && (
        <div className="chips">
          <button className={`chip ${!all ? 'active' : ''}`} aria-pressed={!all} onClick={() => setScope(false)}>Эта аптечка</button>
          <button className={`chip ${all ? 'active' : ''}`} aria-pressed={all} onClick={() => requirePlus('search_all', () => setScope(true))}>Все аптечки</button>
        </div>
      )}

      <div className="chips wrap">
        {conditions.data?.map(c => (
          <button key={c} className={`chip ${q.toLowerCase() === c.toLowerCase() ? 'active' : ''}`} onClick={() => go(c)}>{c}</button>
        ))}
      </div>

      {res.isFetching && <div className="center" style={{ minHeight: 120 }}><Spinner /></div>}

      {res.data && !res.isFetching && (
        <>
          {res.data.results.length === 0 ? (
            <div className="card">
              <Empty icon="🩺" title={`Для «${res.data.query}» ничего не нашлось`}
                text="Подбор ищет по полю «От чего помогает» и категориям. Заполните его у лекарств, и они начнут находиться." />
            </div>
          ) : (
            <div className="stack">
              {res.data.results.map((r, i) => {
                const m = r.medicine
                const unavailable = m.stock.total <= 0
                return (
                  <Link key={`${m.family_id ?? ''}-${m.id}`} to={`/medicines/${m.id}`} className="card condition-result" style={unavailable ? { opacity: .7 } : undefined}
                    onClick={() => { if (all && m.family_id && m.family_id !== familyId) setFamilyId(m.family_id) }}>
                    <div className="row">
                      <span className="rank">{i + 1}</span>
                      <MedIcon category={m.category} size={44} photo={m.photo_url} />
                      <div className="grow">
                        <div style={{ fontWeight: 700, fontSize: 16 }}>{m.name}</div>
                        {all && m.family_name && <span className="badge accent">{m.family_name}</span>}
                        <div className="small muted ellipsis">{subtitle(m) || m.category?.name}</div>
                      </div>
                      <div className="qty">{fmtQty(m.stock.total)}<small>{m.unit}</small></div>
                    </div>
                    <div className="reason">
                      {r.reasons.map(x => <span key={x} className={`badge ${x === 'Вам помогает' ? 'out' : 'accent'}`}>{x === 'Вам помогает' ? '♥ ' : ''}{x}</span>)}
                    </div>
                    {r.warnings.length > 0 && (
                      <div className="stack" style={{ gap: 6 }}>
                        {r.warnings.map(w => <div key={w} className="alert warn small">{w}</div>)}
                      </div>
                    )}
                  </Link>
                )
              })}
            </div>
          )}
          <div className="alert info"><Info size={18} style={{ flexShrink: 0 }} /><span>{res.data.disclaimer}</span></div>
        </>
      )}
    </div>
  )
}
