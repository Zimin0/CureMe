import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, Keyboard, Link2, PackagePlus, Plus } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Category, Medicine, MedicineDetail, PackageInput, ScanResult, uploadFile } from '../api'
import { ExpiryInput } from '../components/ExpiryInput'
import { useFamilyPath } from '../auth'
import { CategoryPicker } from '../components/CategoryPicker'
import { PhotoPicker } from '../components/PhotoPicker'
import { QuantityInput } from '../components/QuantityInput'
import { Scanner } from '../components/Scanner'
import { MedIcon, Sheet, Spinner, useToast } from '../components/ui'
import { fmtDate, fmtQty } from '../format'
import type { ScanPrefill } from './MedicineForm'

const SOURCE_LABEL = { internet: 'Найдено в интернете', user: 'Из справочника CureMe', openfoodfacts: 'Из Open Food Facts' }

export function Scan() {
  const fam = useFamilyPath()
  const [manual, setManual] = useState('')
  const [result, setResult] = useState<ScanResult | null>(null)

  const scan = useMutation({
    mutationFn: (raw: string) => api<ScanResult>(fam('/scan'), { body: { raw } }),
    onSuccess: setResult,
  })
  const onCode = useCallback((raw: string) => { if (!scan.isPending) scan.mutate(raw) }, [scan])
  const close = () => { setResult(null); scan.reset() }

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div className="page-head">
        <div>
          <h1>Сканирование</h1>
          <p className="sub">Незнакомый штрихкод найдём в интернете. Квадратный код DataMatrix ещё и подставит срок годности.</p>
        </div>
      </div>

      <Scanner onCode={onCode} paused={!!result || scan.isPending} />

      <form className="card stack" onSubmit={e => { e.preventDefault(); manual.trim() && scan.mutate(manual.trim()) }}>
        <div className="row"><Keyboard size={18} className="muted" /><h3>Ввести код вручную</h3></div>
        <div className="row">
          <input className="input grow" inputMode="numeric" placeholder="Цифры под штрихкодом, например 4605077018932"
            value={manual} onChange={e => setManual(e.target.value)} />
          <button className="btn primary" disabled={!manual.trim() || scan.isPending}>Найти</button>
        </div>
      </form>

      {scan.isPending && <div className="row" style={{ justifyContent: 'center' }}><Spinner /><span className="muted">Ищем в аптечке и в интернете…</span></div>}
      {scan.error && !result && (
        <div className="alert error row between"><span>{scan.error.message}</span><button className="btn sm" onClick={() => scan.reset()}>Ещё раз</button></div>
      )}

      {result && <ResultSheet result={result} onClose={close} />}
    </div>
  )
}

function ResultSheet({ result, onClose }: { result: ScanResult; onClose: () => void }) {
  const fam = useFamilyPath()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const p = result.product
  const known = result.medicine

  const unit = known?.unit ?? p?.unit ?? 'шт'
  const [name, setName] = useState(p?.name ?? '')
  const [categoryIds, setCategoryIds] = useState<number[]>([])
  const [quantity, setQuantity] = useState(p?.pack_size ?? 1)
  const [blister, setBlister] = useState<number | null>(known?.blister_size ?? p?.blister_size ?? null)
  const [expiry, setExpiry] = useState(result.parsed.expiry ?? '')
  const [linkTo, setLinkTo] = useState('')
  const [photo, setPhoto] = useState<Blob | null>(null)

  const cats = useQuery({ queryKey: ['categories', fam('')], queryFn: () => api<Category[]>(fam('/categories')), enabled: !known })
  const meds = useQuery({ queryKey: ['medicines', fam(''), ''], queryFn: () => api<Medicine[]>(fam('/medicines')), enabled: !known })
  const unlinked = meds.data?.filter(m => !m.gtin) ?? []

  const pkg: PackageInput = {
    quantity, expiry_date: expiry || null, serial: result.parsed.serial, batch: result.parsed.batch,
  }
  const done = (m: MedicineDetail, msg: string) => {
    ['medicines', 'overview', 'categories'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
    qc.setQueryData(['medicine', fam(''), String(m.id)], m)
    toast(msg)
    nav(`/medicines/${m.id}`)
  }

  const create = useMutation({
    mutationFn: async () => {
      const m = await api<MedicineDetail>(fam('/medicines'), {
      body: {
        name: name.trim(), category_ids: categoryIds, form: p?.form ?? null, dosage: p?.dosage ?? null,
        active_ingredient: p?.active_ingredient ?? null, manufacturer: p?.manufacturer ?? null,
        unit, blister_size: blister, gtin: result.display_code, packages: quantity > 0 ? [pkg] : [],
      },
      })
      return photo ? uploadFile<MedicineDetail>(fam(`/medicines/${m.id}/photo`), photo) : m
    },
    onSuccess: m => done(m, `«${m.name}» в аптечке`),
  })
  const addPackage = useMutation({
    mutationFn: async () => {
      if (blister && blister !== known!.blister_size) {
        await api(fam(`/medicines/${known!.id}`), { method: 'PATCH', body: { blister_size: blister } })
      }
      return api<MedicineDetail>(fam(`/medicines/${known!.id}/packages`), { body: pkg })
    },
    onSuccess: m => done(m, `Упаковка добавлена. Всего ${fmtQty(m.stock.total)} ${m.unit}`),
  })
  const link = useMutation({
    mutationFn: async (id: number) => {
      await api(fam(`/medicines/${id}`), { method: 'PATCH', body: { gtin: result.parsed.gtin, blister_size: blister } })
      return api<MedicineDetail>(fam(`/medicines/${id}/packages`), { body: pkg })
    },
    onSuccess: m => done(m, 'Код привязан, упаковка добавлена'),
  })

  const moreDetails = () => {
    const state: ScanPrefill = {
      fields: {
        name, category_ids: categoryIds, form: p?.form ?? null, dosage: p?.dosage ?? null,
        active_ingredient: p?.active_ingredient ?? null, manufacturer: p?.manufacturer ?? null,
        unit, blister_size: blister, gtin: result.display_code,
      },
      pkg,
      packSize: p?.pack_size ?? null,
      photo,
    }
    nav('/medicines/new', { state })
  }

  const error = create.error ?? addPackage.error ?? link.error

  return (
    <Sheet title={known ? 'Уже есть в аптечке' : p ? 'Нашли лекарство' : 'Новое лекарство'} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); known ? addPackage.mutate() : create.mutate() }}>
        <div className="row wrap" style={{ gap: 6 }}>
          <span className="badge">Код {result.display_code}</span>
          {result.parsed.batch && <span className="badge">Серия {result.parsed.batch}</span>}
        </div>

        {result.duplicate_package && (
          <div className="alert warn">Эту самую упаковку уже сканировали раньше. Скорее всего, она уже учтена.</div>
        )}

        {known ? (
          <div className="med-card" style={{ boxShadow: 'none' }}>
            <MedIcon category={known.category} photo={known.photo_url} />
            <div className="grow">
              <div className="name">{known.name}</div>
              <div className="meta">Сейчас в аптечке: {fmtQty(known.stock.total)} {known.unit}</div>
            </div>
          </div>
        ) : p ? (
          <div className="found">
            <span className="small muted row" style={{ gap: 6 }}><Globe size={14} />{SOURCE_LABEL[p.source]}</span>
            <span className="t">{p.title ?? p.name}</span>
            {p.manufacturer && <span className="small muted">{p.manufacturer}</span>}
          </div>
        ) : (
          <p className="muted small">В интернете этот код не нашёлся. Впишите название один раз, и в следующий раз CureMe узнает упаковку сразу.</p>
        )}

        {!known && (
          <>
            <label className="field"><span>Название</span>
              <input className="input" required value={name} onChange={e => setName(e.target.value)} placeholder="Например, Ларингобакт" />
            </label>
            <CategoryPicker categories={cats.data ?? []} value={categoryIds} onChange={setCategoryIds} />
          </>
        )}

        {!known && <PhotoPicker current={null} onChange={setPhoto} />}

        <h3 style={{ marginTop: 4 }}>Сколько осталось в этой упаковке</h3>
        <QuantityInput unit={unit} quantity={quantity} onQuantity={setQuantity}
          blisterSize={blister} onBlisterSize={setBlister} packSize={p?.pack_size} />

        <ExpiryInput value={expiry || null} onChange={v => setExpiry(v ?? '')}
          hint={result.parsed.expiry ? `Взято из кода на упаковке: ${fmtDate(result.parsed.expiry)}` : 'На штрихкоде срока нет: сфотографируйте его или впишите текстом'} />

        {error && <div className="alert error">{error.message}</div>}

        {known ? (
          <>
            <button className="btn primary block" disabled={addPackage.isPending}><PackagePlus size={18} />Добавить упаковку</button>
            <button type="button" className="btn ghost block" onClick={() => nav(`/medicines/${known.id}`)}>Открыть карточку</button>
          </>
        ) : (
          <>
            <button className="btn primary block" disabled={create.isPending || !name.trim()}><Plus size={18} />Сохранить в аптечку</button>
            <button type="button" className="btn ghost block" onClick={moreDetails}>Заполнить подробнее</button>
            {unlinked.length > 0 && (
              <div className="stack" style={{ gap: 8, marginTop: 6 }}>
                <div className="divider">или это лекарство уже есть</div>
                <div className="row">
                  <select className="grow" value={linkTo} onChange={e => setLinkTo(e.target.value)}>
                    <option value="">Выберите из добавленных вручную</option>
                    {unlinked.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                  </select>
                  <button type="button" className="btn" disabled={!linkTo || link.isPending} onClick={() => link.mutate(Number(linkTo))}><Link2 size={17} />Связать</button>
                </div>
              </div>
            )}
          </>
        )}
        <button type="button" className="btn ghost block" onClick={onClose}>Сканировать другое</button>
      </form>
    </Sheet>
  )
}
