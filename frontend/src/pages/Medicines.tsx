import { useQuery } from '@tanstack/react-query'
import { FileDown, FolderInput, FolderPlus, Plus, Search } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, Category, Medicine } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { CabinetSelect } from '../components/Cabinets'
import { MedicineCard } from '../components/MedicineCard'
import { MoveSheet, SplitSheet } from '../components/MoveMedicines'
import { useMedicineLimitGuard } from '../limits'
import { LimitCounter, usePlan, useRequirePlus } from '../plan'
import { Empty, PageLoader } from '../components/ui'

const FILTERS = [
  { id: '', label: 'Все' },
  { id: 'helps_me', label: '♥ Помогают мне' },
  { id: 'favorites', label: '★ Избранное' },
  { id: 'attention', label: 'Требуют внимания' },
  { id: 'low', label: 'Заканчиваются' },
  { id: 'expired', label: 'Просроченные' },
]

export function Medicines() {
  const fam = useFamilyPath()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const filter = params.get('filter') ?? ''
  const cat = params.get('category') ?? ''
  const dq = useDeferredValue(q)
  const guard = useMedicineLimitGuard()
  const { limit } = usePlan()
  const { me } = useAuth()
  const requirePlus = useRequirePlus()
  const several = (me?.families.length ?? 0) > 1
  const all = several && params.get('scope') === 'all'
  const [picking, setPicking] = useState(false)
  const [picked, setPicked] = useState<number[]>([])
  const [sheet, setSheet] = useState<'move' | 'split' | null>(null)
  const toggle = (id: number) => setPicked(p => (p.includes(id) ? p.filter(x => x !== id) : [...p, id]))
  const stopPicking = () => { setPicking(false); setPicked([]); setSheet(null) }

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    v ? next.set(k, v) : next.delete(k)
    setParams(next, { replace: true })
  }

  const cats = useQuery({ queryKey: ['categories', fam('')], queryFn: () => api<Category[]>(fam('/categories')) })
  const qs = new URLSearchParams()
  if (dq) qs.set('q', dq)
  if (filter) qs.set('filter', filter)
  if (cat) qs.set('category_id', cat)
  if (all) qs.set('scope', 'all')
  const meds = useQuery({
    queryKey: ['medicines', fam(''), qs.toString()],
    queryFn: () => api<Medicine[]>(fam(`/medicines?${qs}`)),
    placeholderData: prev => prev,
  })

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Аптечка</h1>
          <CabinetSelect />
          <p className="sub">{meds.data ? `${meds.data.length} в списке` : ' '}{limit('medicines') !== null && <> · <LimitCounter name="medicines" /></>}</p>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <Link to="/medicines/new" className="btn primary" onClick={guard}><Plus size={18} />Добавить</Link>
          {!all && meds.data && meds.data.length > 0 && !picking && <button type="button" className="btn ghost" onClick={() => setPicking(true)}>Выбрать</button>}
          <Link to="/export" className="btn ghost"><FileDown size={18} />Экспорт</Link>
        </div>
      </div>

      <label className="search">
        <Search size={18} />
        <input className="input" type="search" placeholder="Название, вещество, от чего помогает…" value={q} onChange={e => set('q', e.target.value)} />
      </label>

      {several && (
        <div className="chips">
          <button className={`chip ${!all ? 'active' : ''}`} aria-pressed={!all} onClick={() => { stopPicking(); set('scope', '') }}>Эта аптечка</button>
          <button className={`chip ${all ? 'active' : ''}`} aria-pressed={all} onClick={() => requirePlus('search_all', () => { stopPicking(); set('scope', 'all') })}>Все аптечки</button>
        </div>
      )}

      {picking && (
        <div className="card row wrap" role="toolbar" aria-label="Действия с выбранным" style={{ gap: 8 }}>
          <b className="grow">Выбрано: {picked.length}</b>
          {several && <button type="button" className="btn sm" disabled={picked.length === 0} onClick={() => setSheet('move')}><FolderInput size={16} />Перенести</button>}
          <button type="button" className="btn sm" disabled={picked.length === 0} onClick={() => setSheet('split')}><FolderPlus size={16} />В новую аптечку</button>
          <button type="button" className="btn sm ghost" onClick={() => setPicked(meds.data?.map(m => m.id) ?? [])}>Выбрать все</button>
          <button type="button" className="btn sm ghost" onClick={stopPicking}>Отмена</button>
        </div>
      )}

      <div className="stack" style={{ gap: 10 }}>
        <div className="chips">
          {FILTERS.map(f => (
            <button key={f.id} className={`chip ${filter === f.id ? 'active' : ''}`} onClick={() => set('filter', f.id)}>{f.label}</button>
          ))}
        </div>
        <div className="chips wrap-desktop">
          <button className={`chip ${!cat ? 'active' : ''}`} onClick={() => set('category', '')}>Все категории</button>
          {cats.data?.filter(c => c.medicine_count > 0).map(c => (
            <button key={c.id} className={`chip ${cat === String(c.id) ? 'active' : ''}`} onClick={() => set('category', String(c.id))}>
              {c.icon} {c.name} <span className="count">{c.medicine_count}</span>
            </button>
          ))}
        </div>
      </div>

      {meds.isLoading ? <PageLoader /> : meds.data!.length === 0 ? (
        <div className="card">
          {q || filter || cat ? (
            <Empty icon="🔍" title="Ничего не нашлось" text="Попробуйте другой запрос или сбросьте фильтры." />
          ) : (
            <Empty icon="💊" title="Аптечка пустая" text="Добавьте первое лекарство: отсканируйте код на коробке или заполните вручную."
              action={<div className="row"><Link className="btn primary" to="/scan">Сканировать</Link><Link className="btn ghost" to="/medicines/new" onClick={guard}>Вручную</Link></div>} />
          )}
        </div>
      ) : (
        <div className="med-list wide">
          {meds.data!.map(m => picking ? (
            <label key={m.id} className="row" style={{ gap: 10, alignItems: 'center', cursor: 'pointer' }}>
              <input type="checkbox" style={{ width: 20, height: 20, flexShrink: 0 }} checked={picked.includes(m.id)} onChange={() => toggle(m.id)} aria-label={`Выбрать ${m.name}`} />
              <div className="grow" style={{ pointerEvents: 'none' }}><MedicineCard m={m} /></div>
            </label>
          ) : <MedicineCard key={m.id} m={m} showCabinet={all} />)}
        </div>
      )}
      {sheet === 'move' && <MoveSheet ids={picked} onClose={() => setSheet(null)} onDone={stopPicking} />}
      {sheet === 'split' && <SplitSheet ids={picked} onClose={() => setSheet(null)} onDone={stopPicking} />}
    </div>
  )
}
