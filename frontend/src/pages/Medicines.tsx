import { useQuery } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { useDeferredValue } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, Category, Medicine } from '../api'
import { useFamilyPath } from '../auth'
import { MedicineCard } from '../components/MedicineCard'
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
          <p className="sub">{meds.data ? `${meds.data.length} в списке` : ' '}</p>
        </div>
        <Link to="/medicines/new" className="btn primary"><Plus size={18} />Добавить</Link>
      </div>

      <label className="search">
        <Search size={18} />
        <input className="input" type="search" placeholder="Название, вещество, от чего помогает…" value={q} onChange={e => set('q', e.target.value)} />
      </label>

      <div className="stack" style={{ gap: 10 }}>
        <div className="chips">
          {FILTERS.map(f => (
            <button key={f.id} className={`chip ${filter === f.id ? 'active' : ''}`} onClick={() => set('filter', f.id)}>{f.label}</button>
          ))}
        </div>
        <div className="chips">
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
              action={<div className="row"><Link className="btn primary" to="/scan">Сканировать</Link><Link className="btn ghost" to="/medicines/new">Вручную</Link></div>} />
          )}
        </div>
      ) : (
        <div className="med-list wide">{meds.data!.map(m => <MedicineCard key={m.id} m={m} />)}</div>
      )}
    </div>
  )
}
