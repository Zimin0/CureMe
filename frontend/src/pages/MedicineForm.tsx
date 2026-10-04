import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, ScanLine } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api, Category, MedicineDetail, MedicineFields, PackageInput, ProductInfo, uploadFile } from '../api'
import { CategoryPicker } from '../components/CategoryPicker'
import { ExpiryInput } from '../components/ExpiryInput'
import { IndicationsInput } from '../components/IndicationsInput'
import { useAuth, useFamilyPath } from '../auth'
import { PhotoPicker } from '../components/PhotoPicker'
import { QuantityInput } from '../components/QuantityInput'
import { PageLoader, useToast } from '../components/ui'
import { fmtQty } from '../format'
import { useLimitReached } from '../limits'
import { LimitCounter } from '../plan'

const FORMS = ['Таблетки', 'Капсулы', 'Сироп', 'Суспензия', 'Капли', 'Спрей', 'Мазь', 'Гель', 'Крем', 'Порошок', 'Раствор', 'Свечи', 'Пластырь', 'Ампулы']
const UNITS = ['шт', 'таб', 'капс', 'мл', 'г', 'пак', 'амп', 'уп']

export interface ScanPrefill {
  fields?: Partial<MedicineFields>
  pkg?: PackageInput
  packSize?: number | null
  photo?: Blob | null
  source?: string
}

const EMPTY: MedicineFields = {
  name: '', category_ids: [], form: null, dosage: null, active_ingredient: null, manufacturer: null,
  indications: '', contraindications: '', notes: '', unit: 'шт', min_quantity: null, blister_size: null, gtin: null,
}

export function MedicineForm() {
  const { id } = useParams()
  const editing = !!id
  const fam = useFamilyPath()
  const { familyId } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const tgOn = !!useQuery({ queryKey: ['access'], queryFn: () => api<{ closed: boolean; telegram?: boolean }>('/auth/access'), staleTime: 60_000 }).data?.telegram
  const full = useLimitReached('medicines')
  const toast = useToast()
  const prefill = (useLocation().state ?? {}) as ScanPrefill
  const focus = useSearchParams()[0].get('focus')

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
      const { name, category_ids, form, dosage, active_ingredient, manufacturer, indications, contraindications, notes, unit, min_quantity, blister_size, gtin } = existing.data
      setF({ name, category_ids, form, dosage, active_ingredient, manufacturer, indications, contraindications, notes, unit, min_quantity, blister_size, gtin: gtin?.replace(/^0/, '') ?? null })
    }
  }, [existing.data])

  // undefined — фото не трогали, null — убрали, Blob — новое.
  const [photo, setPhoto] = useState<Blob | null | undefined>(prefill.photo ?? undefined)
  const save = useMutation({
    mutationFn: async () => {
      const body = { ...f, gtin: f.gtin?.trim() || null }
      let m = editing
        ? await api<MedicineDetail>(fam(`/medicines/${id}`), { method: 'PATCH', body })
        : await api<MedicineDetail>(fam('/medicines'), { body: { ...body, packages: pkg.quantity > 0 ? [pkg] : [] } })
      if (photo) m = await uploadFile<MedicineDetail>(fam(`/medicines/${m.id}/photo`), photo)
      else if (photo === null && m.photo_url) m = await api<MedicineDetail>(fam(`/medicines/${m.id}/photo`), { method: 'DELETE' })
      return m
    },
    onSuccess: m => {
      qc.invalidateQueries({ queryKey: ['medicines'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
      qc.invalidateQueries({ queryKey: ['plan'] })
      qc.setQueryData(['medicine', fam(''), String(m.id)], m)
      toast(editing ? 'Сохранено' : `«${m.name}» в аптечке`)
      nav(`/medicines/${m.id}`, { replace: true })
    },
  })

  const [packSize, setPackSize] = useState<number | null>(prefill.packSize ?? null)
  const lookup = useMutation({
    mutationFn: () => api<ProductInfo>(`/products/${encodeURIComponent(f.gtin!.trim())}?family_id=${familyId}`),
    onSuccess: p => {
      // Заполняем только пустые поля — то, что человек уже вписал, не трогаем.
      setF(prev => ({
        ...prev,
        name: prev.name || p.name,
        form: prev.form || p.form,
        dosage: prev.dosage || p.dosage,
        active_ingredient: prev.active_ingredient || p.active_ingredient,
        manufacturer: prev.manufacturer || p.manufacturer,
        unit: !editing && p.unit ? p.unit : prev.unit,
        blister_size: prev.blister_size ?? p.blister_size,
      }))
      if (p.pack_size) { setPackSize(p.pack_size); if (!editing) setPkg(prev => ({ ...prev, quantity: p.pack_size! })) }
      toast(`Нашли: ${p.title ?? p.name}`)
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  const set = <K extends keyof MedicineFields>(k: K, v: MedicineFields[K]) => setF(prev => ({ ...prev, [k]: v }))
  const text = (k: keyof MedicineFields) => ({
    value: (f[k] as string | null) ?? '',
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => set(k, e.target.value as never),
  })

  if (editing && existing.isLoading) return <PageLoader />
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate() }

  return (
    <div className="page" style={{ maxWidth: 760 }}>
      <div className="page-head">
        <div>
          <h1>{editing ? 'Редактирование' : 'Новое лекарство'}</h1>
          {prefill.source && <p className="sub">{prefill.source}</p>}
          {!editing && <p className="sub"><LimitCounter name="medicines" /></p>}
        </div>
        {!editing && <Link to="/scan" className="btn ghost"><ScanLine size={18} />Сканировать</Link>}
      </div>

      {!editing && full && (
        <div className="alert warn">
          <span>Место в бесплатной версии закончилось. Удалите ненужные лекарства или подключите <Link to="/plus">Капсулку Плюс</Link>: в ней ограничений нет.</span>
        </div>
      )}

      <form className="stack lg" onSubmit={submit}>
        <section className="card stack">
          <h2>Основное</h2>
          <PhotoPicker current={existing.data?.photo_url ?? null} picked={prefill.photo} onChange={setPhoto} />
          <label className="field"><span>Название *</span>
            <input className="input" required autoFocus={!f.name} placeholder="Например, Нурофен" {...text('name')} />
          </label>
          <CategoryPicker categories={cats.data ?? []} value={f.category_ids} onChange={ids => set('category_ids', ids)} />
          <div className="grid-2">
            <label className="field"><span>Форма</span>
              <input className="input" list="forms" placeholder="Таблетки" {...text('form')} />
              <datalist id="forms">{FORMS.map(x => <option key={x} value={x} />)}</datalist>
            </label>
            <label className="field"><span>Дозировка</span>
              <input className="input" placeholder="200 мг" {...text('dosage')} />
            </label>
            <label className="field"><span>Действующее вещество</span>
              <input className="input" {...text('active_ingredient')} />
            </label>
            <label className="field"><span>Производитель</span>
              <input className="input" {...text('manufacturer')} />
            </label>
            <label className="field"><span>Штрихкод</span>
              <div className="row" style={{ gap: 8 }}>
                <input className="input grow" inputMode="numeric" placeholder="Заполнится при сканировании" {...text('gtin')} />
                <button type="button" className="btn" title="Найти лекарство по штрихкоду в интернете"
                  disabled={!f.gtin?.trim() || lookup.isPending} onClick={() => lookup.mutate()}>
                  <Globe size={17} />{lookup.isPending ? '…' : 'Найти'}
                </button>
              </div>
            </label>
          </div>
        </section>

        <section className="card stack">
          <h2>От чего помогает</h2>
          <IndicationsInput value={f.indications} onChange={v => set('indications', v)} autoFocus={focus === 'indications'} />
          <label className="field"><span>Противопоказания и предупреждения</span>
            <textarea placeholder="Например: не давать детям до 6 лет" {...text('contraindications')} />
          </label>
          <label className="field"><span>Заметки</span>
            <textarea placeholder="Как принимать, где лежит…" {...text('notes')} />
          </label>
        </section>

        <section className="card stack">
          <h2>Остаток</h2>
          {editing && existing.data && (
            <div className="row between wrap" style={{ gap: 8 }}>
              <div>
                <span className="muted small">Сейчас осталось</span>
                <div className="qty" data-testid="current-stock">{fmtQty(existing.data.stock.total)}<small>{existing.data.unit}</small></div>
                <span className="hint">
                  {existing.data.packages.length === 0 ? 'Упаковок нет'
                    : `Годного, во всех упаковках (${existing.data.packages.length})`}
                </span>
              </div>
              <Link to={`/medicines/${id}`} className="btn ghost sm">Изменить в упаковках</Link>
            </div>
          )}
          <div className="grid-2">
            <label className="field"><span>Единица учёта</span>
              <input className="input" list="units" {...text('unit')} />
              <datalist id="units">{UNITS.map(x => <option key={x} value={x} />)}</datalist>
            </label>
            {editing && (
              <label className="field"><span>Штук в блистере</span>
                <input className="input" type="number" min={1} placeholder="Например, 10"
                  value={f.blister_size ?? ''} onChange={e => set('blister_size', e.target.value === '' ? null : Number(e.target.value))} />
              </label>
            )}
            <label className="field"><span>Напомнить, когда останется</span>
              <input className="input" type="number" min={0} step="any" placeholder="Например, 5"
                value={f.min_quantity ?? ''} onChange={e => set('min_quantity', e.target.value === '' ? null : Number(e.target.value))} />
              <span className="hint">Пришлём {tgOn ? 'в Telegram или ' : ''}на почту: включите в «Семья» → «Напоминания»</span>
            </label>
          </div>
          {!editing && (
            <>
              <h3 style={{ marginTop: 6 }}>Первая упаковка</h3>
              <QuantityInput unit={f.unit} quantity={pkg.quantity} onQuantity={q => setPkg(prev => ({ ...prev, quantity: q }))}
                blisterSize={f.blister_size} onBlisterSize={n => set('blister_size', n)} packSize={packSize} />
              <div className="grid-2">
                <ExpiryInput value={pkg.expiry_date ?? null} onChange={v => setPkg(prev => ({ ...prev, expiry_date: v }))}
                  hint={prefill.pkg?.expiry_date ? 'Взято из кода на упаковке' : undefined} />
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
