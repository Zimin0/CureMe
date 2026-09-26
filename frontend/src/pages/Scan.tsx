import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Keyboard, Link2, PackagePlus, Plus } from 'lucide-react'
import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Medicine, PackageInput, ScanResult } from '../api'
import { useFamilyPath } from '../auth'
import { Scanner } from '../components/Scanner'
import { MedIcon, Sheet, Spinner } from '../components/ui'
import { fmtDate, fmtQty } from '../format'
import type { DetailState } from './MedicineDetail'
import type { ScanPrefill } from './MedicineForm'

export function Scan() {
  const fam = useFamilyPath()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [manual, setManual] = useState('')
  const [result, setResult] = useState<ScanResult | null>(null)
  const [linkTo, setLinkTo] = useState('')

  const scan = useMutation({
    mutationFn: (raw: string) => api<ScanResult>(fam('/scan'), { body: { raw } }),
    onSuccess: setResult,
  })
  const onCode = useCallback((raw: string) => { if (!scan.isPending) scan.mutate(raw) }, [scan])

  const meds = useQuery({
    queryKey: ['medicines', fam(''), ''],
    queryFn: () => api<Medicine[]>(fam('/medicines')),
    enabled: !!result && !result.medicine,
  })
  const unlinked = meds.data?.filter(m => !m.gtin) ?? []

  const pkgFromCode = (r: ScanResult): PackageInput => ({
    quantity: 1, expiry_date: r.parsed.expiry, serial: r.parsed.serial, batch: r.parsed.batch,
  })

  const link = useMutation({
    mutationFn: (id: number) => api<Medicine>(fam(`/medicines/${id}`), { method: 'PATCH', body: { gtin: result!.parsed.gtin } }),
    onSuccess: m => {
      qc.invalidateQueries({ queryKey: ['medicines'] })
      const state: DetailState = { addPackage: pkgFromCode(result!) }
      nav(`/medicines/${m.id}`, { state })
    },
  })

  const close = () => { setResult(null); scan.reset(); setLinkTo('') }

  const addNew = () => {
    const r = result!
    const state: ScanPrefill = {
      fields: { ...(r.product ?? {}), name: r.product?.name ?? '', gtin: r.display_code },
      pkg: pkgFromCode(r),
      source: r.product
        ? `Название подсказано ${r.product.source === 'catalog' ? 'общим справочником CureMe' : 'открытой базой товаров'} — проверьте его`
        : `Код ${r.display_code} распознан. Такого товара ещё нет в справочнике, впишите название один раз.`,
    }
    nav('/medicines/new', { state })
  }

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div className="page-head">
        <div>
          <h1>Сканирование</h1>
          <p className="sub">Лучше всего читается квадратный код DataMatrix: из него берутся срок годности и серия</p>
        </div>
      </div>

      <Scanner onCode={onCode} paused={!!result || scan.isPending} />

      <form className="card stack" onSubmit={e => { e.preventDefault(); manual.trim() && scan.mutate(manual.trim()) }}>
        <div className="row"><Keyboard size={18} className="muted" /><h3>Ввести код вручную</h3></div>
        <div className="row">
          <input className="input grow" inputMode="numeric" placeholder="Цифры под штрихкодом, например 4601234567890"
            value={manual} onChange={e => setManual(e.target.value)} />
          <button className="btn primary" disabled={!manual.trim() || scan.isPending}>Найти</button>
        </div>
      </form>

      {scan.isPending && <div className="row" style={{ justifyContent: 'center' }}><Spinner /><span className="muted">Ищем…</span></div>}
      {scan.error && !result && (
        <div className="alert error row between"><span>{scan.error.message}</span><button className="btn sm" onClick={() => scan.reset()}>Ещё раз</button></div>
      )}

      {result && (
        <Sheet title={result.medicine ? 'Уже есть в аптечке' : 'Новое лекарство'} onClose={close}>
          <div className="stack">
            <div className="row wrap" style={{ gap: 6 }}>
              <span className="badge">Код {result.display_code}</span>
              {result.parsed.expiry && <span className="badge info">Годен до {fmtDate(result.parsed.expiry)}</span>}
              {result.parsed.batch && <span className="badge">Серия {result.parsed.batch}</span>}
            </div>

            {result.duplicate_package && (
              <div className="alert warn">Эту самую упаковку уже сканировали раньше. Скорее всего, она уже учтена.</div>
            )}

            {result.medicine ? (
              <>
                <div className="med-card" style={{ boxShadow: 'none' }}>
                  <MedIcon category={result.medicine.category} />
                  <div className="grow">
                    <div className="name">{result.medicine.name}</div>
                    <div className="meta">Сейчас: {fmtQty(result.medicine.stock.total)} {result.medicine.unit}</div>
                  </div>
                </div>
                <button className="btn primary block" onClick={() => nav(`/medicines/${result.medicine!.id}`, { state: { addPackage: pkgFromCode(result) } satisfies DetailState })}>
                  <PackagePlus size={18} />Добавить упаковку
                </button>
                <button className="btn ghost block" onClick={() => nav(`/medicines/${result.medicine!.id}`)}>Открыть карточку</button>
              </>
            ) : (
              <>
                {result.product ? (
                  <div className="alert ok"><span>Похоже, это <b>{result.product.name}</b>{result.product.manufacturer ? `, ${result.product.manufacturer}` : ''}</span></div>
                ) : (
                  <p className="muted">Этого кода ещё нет в справочнике. Впишите название один раз, и в следующий раз CureMe узнает упаковку сразу.</p>
                )}
                <button className="btn primary block" onClick={addNew}><Plus size={18} />Добавить в аптечку</button>
                {unlinked.length > 0 && (
                  <div className="stack" style={{ gap: 8, marginTop: 6 }}>
                    <div className="divider">или это лекарство уже есть</div>
                    <div className="row">
                      <select className="grow" value={linkTo} onChange={e => setLinkTo(e.target.value)}>
                        <option value="">Выберите из добавленных вручную</option>
                        {unlinked.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                      </select>
                      <button className="btn" disabled={!linkTo || link.isPending} onClick={() => link.mutate(Number(linkTo))}><Link2 size={17} />Связать</button>
                    </div>
                    {link.error && <div className="alert error">{link.error.message}</div>}
                  </div>
                )}
              </>
            )}
            <button className="btn ghost block" onClick={close}>Сканировать другое</button>
          </div>
        </Sheet>
      )}
    </div>
  )
}
