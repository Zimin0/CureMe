import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Pencil, Trash2, X } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { api, ApiError, Illness, uploadDocument } from '../api'
import { AuthImage } from '../components/AuthImage'
import { IllnessCalendar, Period } from '../components/IllnessCalendar'
import { IntakeTabs } from '../components/IntakeTabs'
import { Empty, PageLoader, Sheet, useToast } from '../components/ui'
import { compressImage } from '../image'
import { daysIn, dayKey, inRange, parseDay, periodLabel } from '../illness'

const MAX_PHOTOS = 10
const errText = (e: unknown) => (e instanceof ApiError ? e.message : 'Не удалось сохранить')

/** Личная история болезней: даты (клик по дню или протяжка), комментарий и фото документов. Видна только автору. */
export function IllnessHistory() {
  const qc = useQueryClient()
  const toast = useToast()
  const list = useQuery({ queryKey: ['illnesses'], queryFn: () => api<Illness[]>('/illnesses') })
  const [period, setPeriod] = useState<Period | null>(null)
  const [editing, setEditing] = useState<Illness | null>(null)
  const [title, setTitle] = useState('')
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const records = list.data ?? []
  const marked = useMemo(() => {
    const s = new Set<string>()
    for (const r of records) {
      // Длинные записи не раскладываем по дням целиком: хватает отметить каждый день до года.
      const n = Math.min(daysIn(r.date_from, r.date_to), 400)
      for (let i = 0; i < n; i++) { const d = parseDay(r.date_from); d.setDate(d.getDate() + i); s.add(dayKey(d)) }
    }
    return s
  }, [records])

  const reset = () => { setEditing(null); setPeriod(null); setTitle(''); setComment(''); setFiles([]); setError('') }
  const edit = (r: Illness) => {
    setEditing(r); setPeriod({ from: r.date_from, to: r.date_to }); setTitle(r.title); setComment(r.comment); setFiles([]); setError('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const save = useMutation({
    mutationFn: async () => {
      if (!period) throw new Error('Выберите день или период в календаре')
      const body = { title, comment, date_from: period.from, date_to: period.to }
      const rec = editing
        ? await api<Illness>(`/illnesses/${editing.id}`, { method: 'PATCH', body })
        : await api<Illness>('/illnesses', { method: 'POST', body })
      let failed = 0
      for (const f of files) {
        try { await uploadDocument<Illness>(`/illnesses/${rec.id}/documents`, await compressImage(f), 'document.jpg') } catch { failed++ }
      }
      return failed
    },
    onSuccess: failed => {
      qc.invalidateQueries({ queryKey: ['illnesses'] })
      toast(failed ? `Запись сохранена, но ${failed} фото не загрузилось` : 'Запись сохранена', failed ? 'error' : 'ok')
      reset()
    },
    onError: e => setError(e instanceof Error && !(e instanceof ApiError) ? e.message : errText(e)),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/illnesses/${id}`, { method: 'DELETE' }),
    onSuccess: (_, id) => { qc.invalidateQueries({ queryKey: ['illnesses'] }); if (editing?.id === id) reset(); toast('Запись удалена') },
  })
  const dropDoc = useMutation({
    mutationFn: ({ id, doc }: { id: number; doc: number }) => api<Illness>(`/illnesses/${id}/documents/${doc}`, { method: 'DELETE' }),
    onSuccess: rec => { qc.invalidateQueries({ queryKey: ['illnesses'] }); setEditing(rec) },
  })

  const room = MAX_PHOTOS - (editing?.documents.length ?? 0) - files.length
  const addFiles = (picked: FileList | null) => {
    if (!picked) return
    // Копируем сразу: сброс значения поля ниже очищает и сам FileList.
    const chosen = Array.from(picked).filter(f => f.type.startsWith('image/'))
    setFiles(prev => [...prev, ...chosen].slice(0, MAX_PHOTOS - (editing?.documents.length ?? 0)))
    if (picker.current) picker.current.value = ''
  }
  const setDate = (k: 'from' | 'to', v: string) => {
    if (!v) return
    const cur = period ?? { from: v, to: v }
    const next = { ...cur, [k]: v }
    if (next.to < next.from) next[k === 'from' ? 'to' : 'from'] = v
    setPeriod(next)
  }

  return (
    <div className="page">
      <IntakeTabs />
      <div className="page-head">
        <div>
          <h1>История болезней</h1>
          <p className="sub">Когда болели, что делали и фото справок. Записи личные: их видите только вы, даже члены семьи их не увидят.</p>
        </div>
      </div>

      <section className="card stack ill-form">
        <IllnessCalendar value={period} onChange={setPeriod} marked={marked} />
        <div className="row wrap history-dates">
          <label>С <input className="input" type="date" aria-label="Болезнь с даты" value={period?.from ?? ''} max={period?.to} onChange={e => setDate('from', e.target.value)} /></label>
          <label>по <input className="input" type="date" aria-label="Болезнь по дату" value={period?.to ?? ''} min={period?.from} onChange={e => setDate('to', e.target.value)} /></label>
          {period && <b className="ill-period" data-testid="period">{periodLabel(period.from, period.to)}{period.from !== period.to && ` · ${daysIn(period.from, period.to)} дн.`}</b>}
        </div>
        <label className="field"><span>Название</span>
          <input className="input" aria-label="Название болезни" maxLength={200} placeholder="Например: ОРВИ" value={title} onChange={e => setTitle(e.target.value)} />
        </label>
        <label className="field"><span>Комментарий</span>
          <textarea aria-label="Комментарий к болезни" maxLength={5000} rows={4} placeholder="Симптомы, что назначил врач, чем лечились"
            value={comment} onChange={e => setComment(e.target.value)} />
        </label>
        <div className="field"><span>Фото документов</span>
          <div className="ill-photos">
            {editing?.documents.map(d => (
              <div className="ill-thumb" key={d.id}>
                <button type="button" onClick={() => setOpen(d.url)} aria-label="Открыть фото"><AuthImage url={d.url} alt="Фото документа" /></button>
                <button type="button" className="ill-thumb-x" aria-label="Убрать фото" onClick={() => dropDoc.mutate({ id: editing.id, doc: d.id })}><X size={14} /></button>
              </div>
            ))}
            {files.map((f, i) => (
              <div className="ill-thumb" key={`${f.name}-${i}`}>
                <img src={URL.createObjectURL(f)} alt={`Выбрано: ${f.name}`} />
                <button type="button" className="ill-thumb-x" aria-label="Убрать фото" onClick={() => setFiles(files.filter((_, j) => j !== i))}><X size={14} /></button>
              </div>
            ))}
            {room > 0 && (
              <button type="button" className="ill-add" onClick={() => picker.current?.click()}><Camera size={22} />Фото</button>
            )}
            <input ref={picker} type="file" accept="image/*" multiple hidden aria-label="Добавить фото документа" onChange={e => addFiles(e.target.files)} />
          </div>
          <span className="hint">До {MAX_PHOTOS} фото. Не загружайте лишнего: снимайте только нужные страницы.</span>
        </div>
        {error && <div className="alert error">{error}</div>}
        <div className="row wrap">
          <button className="btn primary" disabled={save.isPending} onClick={() => { setError(''); save.mutate() }}>{editing ? 'Сохранить изменения' : 'Сохранить запись'}</button>
          {(editing || period || title || comment || files.length > 0) && <button className="btn ghost" type="button" onClick={reset}>{editing ? 'Отменить правку' : 'Очистить'}</button>}
        </div>
      </section>

      {list.isLoading ? <PageLoader /> : records.length === 0 ? (
        <div className="card"><Empty icon="🩺" title="Пока пусто" text="Выберите дни в календаре и сохраните первую запись." /></div>
      ) : (
        <section className="card" aria-label="Записи">
          {records.map(r => (
            <article key={r.id} className={`ill-record ${period && inRange(r.date_from, period.from, period.to) ? 'near' : ''}`}>
              <div className="row between">
                <div className="grow">
                  <b>{periodLabel(r.date_from, r.date_to)}</b>
                  {r.title && <div className="ill-title">{r.title}</div>}
                </div>
                <button className="icon-btn" onClick={() => edit(r)} aria-label="Изменить запись"><Pencil size={16} /></button>
                <button className="icon-btn" onClick={() => confirm('Удалить запись вместе с фото?') && remove.mutate(r.id)} aria-label="Удалить запись"><Trash2 size={16} /></button>
              </div>
              {r.comment && <p className="ill-comment">{r.comment}</p>}
              {r.documents.length > 0 && (
                <div className="ill-photos">
                  {r.documents.map(d => (
                    <div className="ill-thumb" key={d.id}>
                      <button type="button" onClick={() => setOpen(d.url)} aria-label="Открыть фото"><AuthImage url={d.url} alt="Фото документа" /></button>
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
        </section>
      )}

      {open && (
        <Sheet title="Фото документа" onClose={() => setOpen(null)}>
          <AuthImage className="photo-full" url={open} alt="Фото документа" />
        </Sheet>
      )}
    </div>
  )
}
