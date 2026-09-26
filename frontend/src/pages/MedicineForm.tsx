import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ScanLine } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, Category, MedicineDetail, MedicineFields, PackageInput } from '../api'
import { useFamilyPath } from '../auth'
import { PageLoader, useToast } from '../components/ui'

const FORMS = ['Таблетки', 'Капсулы', 'Сироп', 'Суспензия', 'Капли', 'Спрей', 'Мазь', 'Гель', 'Крем', 'Порошок', 'Раствор', 'Свечи', 'Пластырь', 'Ампулы']
const UNITS = ['шт', 'таб', 'капс', 'мл', 'г', 'пак', 'амп', 'уп']
const INDICATION_HINTS = ['головная боль', 'температура', 'простуда', 'насморк', 'кашель', 'боль в горле', 'аллергия', 'изжога', 'диарея', 'порез', 'ожог', 'ушиб']

export interface ScanPrefill {
  fields?: Partial<MedicineFields>
  pkg?: PackageInput
  source?: string
}

const EMPTY: MedicineFields = {
  name: '', category_id: null, form: null, dosage: null, active_ingredient: null, manufacturer: null,
  indications: '', contraindications: '', notes: '', unit: 'шт', min_quantity: null, gtin: null,
}

export function MedicineForm() {
  const { id } = useParams()
  const editing = !!id
  const fam = useFamilyPath()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const prefill = (useLocation().state ?? {}) as ScanPrefill

  const [f, setF] = useState<MedicineFields>({ ...EMPTY, ...prefill.fields })
  const [pkg, setPkg] = useState<PackageInput>({ quantity: 1, expiry_date: null, ...prefill.pkg })

  const cats = useQuery({ queryKey: ['categories', fam('')], queryFn: () => api<Category[]>(fam('/categories')) })
  const existing = useQuery({
    queryKey: ['medicine', fam(''), id],
    queryFn: () => api<MedicineDetail>(fam(`/medicines/${id}`)),
    enabled: editing,
  })
  useEffect(() => {
    if (existing.data) {
      const { name, category_id, form, dosage, active_ingredient, manufacturer, indications, contraindications, notes, unit, min_quantity, gtin } = existing.data
      setF({ name, category_id, form, dosage, active_ingredient, manufacturer, indications, contraindications, notes, unit, min_quantity, gtin })
    }
  }, [existing.data])

  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, gtin: f.gtin?.trim() || null }
      return editing
        ? api<MedicineDetail>(fam(`/medicines/${id}`), { method: 'PATCH', body })
        : api<MedicineDetail>(fam('/medicines'), { body: { ...body, packages: pkg.quantity > 0 ? [pkg] : [] } })
    },
    onSuccess: m => {
      qc.invalidateQueries({ queryKey: ['medicines'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
      qc.setQueryData(['medicine', fam(''), String(m.id)], m)
      toast(editing ? 'Сохранено' : `«${m.name}» в аптечке`)
      nav(`/medicines/${m.id}`, { replace: true })
    },
  })

  const set = <K extends keyof MedicineFields>(k: K, v: MedicineFields[K]) => setF(prev => ({ ...prev, [k]: v }))
  const text = (k: keyof MedicineFields) => ({
    value: (f[k] as string | null) ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => set(k, e.target.value as never),
  })
  const addIndication = (t: string) => {
    const cur = f.indications.split(',').map(s => s.trim()).filter(Boolean)
    if (!cur.includes(t)) set('indications', [...cur, t].join(', '))
  }

  if (editing && existing.isLoading) return <PageLoader />
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }

  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <div className="page-head">
        <div>
          <h1>{editing ? 'Редактирование' : 'Новое лекарство'}</h1>
          {prefill.source && <p className="sub">{prefill.source}</p>}
        </div>
        {!editing && <Link to="/scan" className="btn ghost"><ScanLine size={18} />Сканировать</Link>}
      </div>

      <form className="stack lg" onSubmit={submit}>
        <section className="card stack">
          <h2>Основное</h2>
          <label className="field"><span>Название *</span>
            <input className="input" required autoFocus={!f.name} placeholder="Например, Нурофен" {...text('name')} />
          </label>
          <div className="grid-2">
            <label className="field"><span>Категория</span>
              <select value={f.category_id ?? ''} onChange={e => set('category_id', e.target.value ? Number(e.target.value) : null)}>
                <option value="">Без категории</option>
                {cats.data?.map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
              </select>
            </label>
            <label className="field"><span>Форма</span>
              <input className="input" list="forms" placeholder="Таблетки" {...text('form')} />
              <datalist id="forms">{FORMS.map(x => <option key={x} value={x} />)}</datalist>
            </label>
            <label className="field"><span>Дозировка</span>
              <input className="input" placeholder="200 мг" {...text('dosage')} />
            </label>
            <label className="field"><span>Действующее вещество</span>
              <input className="input" placeholder="Ибупрофен" {...text('active_ingredient')} />
            </label>
            <label className="field"><span>Производитель</span>
              <input className="input" {...text('manufacturer')} />
            </label>
            <label className="field"><span>Штрихкод</span>
              <input className="input" inputMode="numeric" placeholder="Заполнится при сканировании" {...text('gtin')} />
            </label>
          </div>
        </section>

        <section className="card stack">
          <h2>От чего помогает</h2>
          <label className="field">
            <textarea placeholder="Через запятую: головная боль, температура, зубная боль" {...text('indications')} />
            <span className="hint">По этим словам работает подбор лекарства под болезнь</span>
          </label>
          <div className="chips wrap">
            {INDICATION_HINTS.map(t => <button type="button" key={t} className="chip" onClick={() => addIndication(t)}>+ {t}</button>)}
          </div>
          <label className="field"><span>Противопоказания и предупреждения</span>
            <textarea placeholder="Например: не давать детям до 6 лет" {...text('contraindications')} />
          </label>
          <label className="field"><span>Заметки</span>
            <textarea placeholder="Как принимать, где лежит…" {...text('notes')} />
          </label>
        </section>

        <section className="card stack">
          <h2>Остаток</h2>
          <div className="grid-2">
            <label className="field"><span>Единица учёта</span>
              <input className="input" list="units" {...text('unit')} />
              <datalist id="units">{UNITS.map(x => <option key={x} value={x} />)}</datalist>
            </label>
            <label className="field"><span>Напомнить, когда останется</span>
              <input className="input" type="number" min={0} step="any" placeholder="Например, 5"
                value={f.min_quantity ?? ''} onChange={e => set('min_quantity', e.target.value === '' ? null : Number(e.target.value))} />
            </label>
          </div>
          {!editing && (
            <>
              <h3 style={{ marginTop: 6 }}>Первая упаковка</h3>
              <div className="grid-2">
                <label className="field"><span>Количество в упаковке ({f.unit})</span>
                  <input className="input" type="number" min={0} step="any" value={pkg.quantity}
                    onChange={e => setPkg({ ...pkg, quantity: Number(e.target.value) })} />
                </label>
                <label className="field"><span>Годен до</span>
                  <input className="input" type="date" value={pkg.expiry_date ?? ''} onChange={e => setPkg({ ...pkg, expiry_date: e.target.value || null })} />
                  {prefill.pkg?.expiry_date && <span className="hint">Взято из кода на упаковке</span>}
                </label>
                <label className="field"><span>Где лежит</span>
                  <input className="input" placeholder="Кухня, верхняя полка" value={pkg.location ?? ''} onChange={e => setPkg({ ...pkg, location: e.target.value || null })} />
                </label>
              </div>
            </>
          )}
        </section>

        {save.error && <div className="alert error">{save.error.message}</div>}
        <div className="row" style={{ justifyContent: 'flex-end' }}>
          <button type="button" className="btn ghost" onClick={() => nav(-1)}>Отмена</button>
          <button className="btn primary" disabled={save.isPending}>{save.isPending ? 'Сохраняем…' : editing ? 'Сохранить' : 'Добавить в аптечку'}</button>
        </div>
      </form>
    </div>
  )
}
