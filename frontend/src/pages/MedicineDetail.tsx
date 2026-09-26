import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Heart, MapPin, Minus, Pencil, Plus, Star, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, MedicineDetail as Detail, Package, PackageInput } from '../api'
import { useFamilyPath } from '../auth'
import { QuantityInput } from '../components/QuantityInput'
import { Empty, MedIcon, PageLoader, Sheet, StatusBadge, useToast } from '../components/ui'
import { daysText, fmtDate, fmtQty, splitTags, subtitle } from '../format'

export interface DetailState { addPackage?: PackageInput }

export function MedicineDetail() {
  const { id } = useParams()
  const fam = useFamilyPath()
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const initial = (useLocation().state ?? {}) as DetailState
  const key = ['medicine', fam(''), id]
  const { data: m, isLoading, error } = useQuery({ queryKey: key, queryFn: () => api<Detail>(fam(`/medicines/${id}`)) })

  const [pkgSheet, setPkgSheet] = useState<{ edit?: Package; init?: PackageInput } | null>(
    initial.addPackage ? { init: initial.addPackage } : null,
  )
  const [dose, setDose] = useState(1)

  const onSaved = (d: Detail, msg?: string) => {
    qc.setQueryData(key, d)
    qc.invalidateQueries({ queryKey: ['medicines'] })
    qc.invalidateQueries({ queryKey: ['overview'] })
    if (msg) toast(msg)
  }
  const onError = (e: Error) => toast(e.message, 'error')

  const mark = useMutation({
    mutationFn: (body: { is_favorite?: boolean; helps_me?: boolean }) => api<Detail>(fam(`/medicines/${id}/mark`), { method: 'PUT', body }),
    onSuccess: d => onSaved(d), onError,
  })
  const consume = useMutation({
    mutationFn: () => api<Detail>(fam(`/medicines/${id}/consume`), { body: { amount: dose } }),
    onSuccess: d => onSaved(d, `Списано ${fmtQty(dose)} ${d.unit}. Осталось ${fmtQty(d.stock.total)}`), onError,
  })
  const removePkg = useMutation({
    mutationFn: (pid: number) => api<Detail>(fam(`/medicines/${id}/packages/${pid}`), { method: 'DELETE' }),
    onSuccess: d => onSaved(d, 'Упаковка удалена'), onError,
  })
  const remove = useMutation({
    mutationFn: () => api(fam(`/medicines/${id}`), { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['medicines'] })
      qc.invalidateQueries({ queryKey: ['overview'] })
      qc.invalidateQueries({ queryKey: ['categories'] })
      toast('Лекарство удалено')
      nav('/medicines', { replace: true })
    },
    onError,
  })

  if (isLoading) return <PageLoader />
  if (error || !m) return <div className="page"><Empty icon="🤷" title="Лекарство не найдено" action={<Link className="btn" to="/medicines">К аптечке</Link>} /></div>

  const s = m.stock
  const good = m.packages.filter(p => !p.expired && p.quantity > 0)
  const tags = splitTags(m.indications)

  return (
    <div className="page">
      <div className="row between">
        <button className="btn ghost sm" onClick={() => nav(-1)}><ArrowLeft size={16} />Назад</button>
        <div className="row" style={{ gap: 8 }}>
          <button className={`icon-btn ${m.is_favorite ? 'on-fav' : ''}`} title="Избранное" aria-pressed={m.is_favorite}
            onClick={() => mark.mutate({ is_favorite: !m.is_favorite })}>
            <Star size={19} fill={m.is_favorite ? 'currentColor' : 'none'} />
          </button>
          <Link to={`/medicines/${m.id}/edit`} className="icon-btn" title="Редактировать"><Pencil size={18} /></Link>
        </div>
      </div>

      <div className="detail-head">
        <MedIcon category={m.category} />
        <div className="grow stack" style={{ gap: 6 }}>
          <h1>{m.name}</h1>
          <p className="muted">{subtitle(m) || 'Добавьте форму и дозировку в редактировании'}</p>
          <div className="row wrap" style={{ gap: 6 }}>
            {m.category && <span className="badge accent">{m.category.icon} {m.category.name}</span>}
            <StatusBadge stock={s} />
          </div>
        </div>
      </div>

      <button className={`btn block ${m.helps_me ? 'danger' : 'ghost'}`} onClick={() => mark.mutate({ helps_me: !m.helps_me })}>
        <Heart size={18} fill={m.helps_me ? 'currentColor' : 'none'} />
        {m.helps_me ? 'Помогает мне' : 'Отметить: помогает мне'}
      </button>
      {m.helps_members.length > 0 && <p className="small muted" style={{ marginTop: -10 }}>Также помогает: {m.helps_members.join(', ')}</p>}

      <div className="two-col">
        <div className="stack lg">
          <section className="card">
            <div className="card-head">
              <div>
                <p className="muted small">Всего годного</p>
                <div className="qty" style={{ fontSize: 32 }}>{fmtQty(s.total)}<small>{m.unit}</small></div>
                {m.blister_size && s.total > 0 && <p className="small muted">≈ {fmtQty(Math.round((s.total / m.blister_size) * 10) / 10)} бл. по {m.blister_size}</p>}
                {s.nearest_expiry && <p className="small muted">Ближайший срок: {fmtDate(s.nearest_expiry)} ({daysText(s.days_left!)})</p>}
              </div>
            </div>
            <div className="row wrap">
              <div className="stepper" aria-label="Сколько списать">
                <button type="button" onClick={() => setDose(d => Math.max(0.5, d - (d > 1 ? 1 : 0.5)))}><Minus size={16} /></button>
                <input type="number" min={0.5} step="any" value={dose} onChange={e => setDose(Math.max(0, Number(e.target.value)))} />
                <button type="button" onClick={() => setDose(d => d + 1)}><Plus size={16} /></button>
              </div>
              <button className="btn primary grow" disabled={s.total <= 0 || consume.isPending || dose <= 0} onClick={() => consume.mutate()}>
                Принял(а) {fmtQty(dose)} {m.unit}
              </button>
            </div>
            <p className="faint small" style={{ marginTop: 8 }}>Списываем из упаковки, у которой срок кончается раньше</p>
          </section>

          <section className="card">
            <div className="card-head">
              <h2>Упаковки</h2>
              <button className="btn sm primary" onClick={() => setPkgSheet({})}><Plus size={16} />Добавить</button>
            </div>
            {m.packages.length === 0 ? (
              <Empty icon="📦" title="Упаковок нет" text="Добавьте упаковку, чтобы следить за сроком и остатком." />
            ) : m.packages.map(p => {
              const max = Math.max(p.quantity, ...good.map(g => g.quantity), 1)
              return (
                <div key={p.id} className="pkg">
                  <div className="grow">
                    <div className="row" style={{ gap: 8 }}>
                      <strong>{fmtQty(p.quantity)} {m.unit}</strong>
                      {p.expired ? <span className="badge expired">Просрочена</span>
                        : p.quantity <= 0 ? <span className="badge out">Пустая</span>
                        : p.days_left !== null && p.days_left <= 30 ? <span className="badge expiring">{daysText(p.days_left)}</span> : null}
                    </div>
                    <div className="small muted">
                      Годен до {fmtDate(p.expiry_date)}
                      {p.location && <> · <MapPin size={12} style={{ verticalAlign: -1 }} /> {p.location}</>}
                      {p.batch && <> · серия {p.batch}</>}
                    </div>
                    {!p.expired && <div className="bar"><i style={{ width: `${Math.min(100, (p.quantity / max) * 100)}%` }} /></div>}
                  </div>
                  <button className="icon-btn" title="Изменить" onClick={() => setPkgSheet({ edit: p })}><Pencil size={16} /></button>
                  <button className="icon-btn" title="Удалить упаковку"
                    onClick={() => confirm(p.expired ? 'Удалить просроченную упаковку? Не забудьте её утилизировать.' : 'Удалить упаковку?') && removePkg.mutate(p.id)}>
                    <Trash2 size={16} />
                  </button>
                </div>
              )
            })}
          </section>
        </div>

        <div className="stack lg">
          <section className="card stack">
            <h2>От чего помогает</h2>
            {tags.length ? <div className="tag-cloud">{tags.map(t => <Link key={t} to={`/find?q=${encodeURIComponent(t)}`} className="chip">{t}</Link>)}</div>
              : <p className="muted">Не указано. <Link to={`/medicines/${m.id}/edit`} style={{ color: 'var(--primary)' }}>Добавить</Link>, чтобы работал подбор.</p>}
            {m.contraindications && <div className="alert warn"><span><b>Внимание:</b> {m.contraindications}</span></div>}
          </section>
          <section className="card">
            <h2 style={{ marginBottom: 12 }}>Подробности</h2>
            <dl className="kv">
              <dt>Вещество</dt><dd>{m.active_ingredient || '—'}</dd>
              <dt>Производитель</dt><dd>{m.manufacturer || '—'}</dd>
              <dt>Штрихкод</dt><dd>{m.gtin ? m.gtin.replace(/^0/, '') : '—'}</dd>
              <dt>Напомнить при</dt><dd>{m.min_quantity != null ? `${fmtQty(m.min_quantity)} ${m.unit}` : '—'}</dd>
              {m.notes && <><dt>Заметки</dt><dd style={{ whiteSpace: 'pre-wrap' }}>{m.notes}</dd></>}
            </dl>
          </section>
          <button className="btn danger" onClick={() => confirm(`Удалить «${m.name}» со всеми упаковками?`) && remove.mutate()}>
            <Trash2 size={17} />Удалить лекарство
          </button>
        </div>
      </div>

      {pkgSheet && (
        <PackageSheet med={m} edit={pkgSheet.edit} init={pkgSheet.init} onClose={() => setPkgSheet(null)}
          onSaved={d => { onSaved(d, pkgSheet.edit ? 'Упаковка обновлена' : 'Упаковка добавлена'); setPkgSheet(null) }} />
      )}
    </div>
  )
}

function PackageSheet({ med, edit, init, onClose, onSaved }: {
  med: Detail; edit?: Package; init?: PackageInput; onClose: () => void; onSaved: (d: Detail) => void
}) {
  const fam = useFamilyPath()
  const [p, setP] = useState<PackageInput>(edit
    ? { quantity: edit.quantity, expiry_date: edit.expiry_date, location: edit.location, batch: edit.batch }
    : { quantity: med.packages.at(-1)?.quantity || 1, expiry_date: null, location: med.packages.at(-1)?.location ?? null, ...init })
  const [blister, setBlister] = useState<number | null>(med.blister_size)
  const save = useMutation({
    mutationFn: async () => {
      if (blister !== med.blister_size) await api(fam(`/medicines/${med.id}`), { method: 'PATCH', body: { blister_size: blister } })
      return edit
      ? api<Detail>(fam(`/medicines/${med.id}/packages/${edit.id}`), { method: 'PATCH', body: p })
      : api<Detail>(fam(`/medicines/${med.id}/packages`), { body: p })
    },
    onSuccess: onSaved,
  })
  return (
    <Sheet title={edit ? 'Упаковка' : `Новая упаковка: ${med.name}`} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); save.mutate() }}>
        {init?.serial && <div className="alert ok">Срок и серия взяты из кода на упаковке</div>}
        <QuantityInput unit={med.unit} quantity={p.quantity} onQuantity={q => setP(prev => ({ ...prev, quantity: q }))}
          blisterSize={blister} onBlisterSize={setBlister} />
        <label className="field"><span>Годен до</span>
          <input className="input" type="date" value={p.expiry_date ?? ''} onChange={e => setP({ ...p, expiry_date: e.target.value || null })} />
        </label>
        <label className="field"><span>Где лежит</span>
          <input className="input" placeholder="Кухня, верхняя полка" value={p.location ?? ''} onChange={e => setP({ ...p, location: e.target.value || null })} />
        </label>
        {save.error && <div className="alert error">{save.error.message}</div>}
        <button className="btn primary block" disabled={save.isPending}>{edit ? 'Сохранить' : 'Добавить упаковку'}</button>
      </form>
    </Sheet>
  )
}
