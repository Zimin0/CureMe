import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError, Illness, uploadDocument } from '../api'
import { AuthImage } from '../components/AuthImage'
import { IllnessCalendar, Period } from '../components/IllnessCalendar'
import { PageLoader, Sheet, useToast } from '../components/ui'
import { compressImage } from '../image'
import { daysIn, dayKey, parseDay, periodLabel } from '../illness'

const MAX_PHOTOS = 10
const errText = (e: unknown) => (e instanceof ApiError ? e.message : e instanceof Error ? e.message : 'Не удалось сохранить')

/** Страница «Записать болезнь» и правка записи: календарь (клик или протяжка), название, комментарий, фото документов. */
export function IllnessForm() {
  const { id } = useParams()
  const editingId = id ? Number(id) : null
  const nav = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const list = useQuery({ queryKey: ['illnesses'], queryFn: () => api<Illness[]>('/illnesses') })
  const records = list.data ?? []
  const editing = editingId ? records.find(r => r.id === editingId) ?? null : null

  const [period, setPeriod] = useState<Period | null>(null)
  const [title, setTitle] = useState('')
  const [comment, setComment] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [error, setError] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  // Форма правки заполняется один раз, когда запись загрузилась: дальше правки человека не перезаписываем.
  const filled = useRef(false)
  useEffect(() => {
    if (editing && !filled.current) {
      filled.current = true
      setPeriod({ from: editing.date_from, to: editing.date_to })
      setTitle(editing.title)
      setComment(editing.comment)
    }
  }, [editing])

  const marked = useMemo(() => {
    const s = new Set<string>()
    for (const r of records) {
      const n = Math.min(daysIn(r.date_from, r.date_to), 400)
      for (let i = 0; i < n; i++) { const d = parseDay(r.date_from); d.setDate(d.getDate() + i); s.add(dayKey(d)) }
    }
    return s
  }, [records])

  const save = useMutation({
    mutationFn: async () => {
      if (!period) throw new Error('Выберите день или период в календаре')
      const body = { title, comment, date_from: period.from, date_to: period.to }
      const rec = editingId
        ? await api<Illness>(`/illnesses/${editingId}`, { method: 'PATCH', body })
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
      nav('/illness')
    },
    onError: e => setError(errText(e)),
  })
  const dropDoc = useMutation({
    mutationFn: (doc: number) => api<Illness>(`/illnesses/${editingId}/documents/${doc}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['illnesses'] }),
  })

  const saved = editing?.documents.length ?? 0
  const room = MAX_PHOTOS - saved - files.length
  const addFiles = (picked: FileList | null) => {
    if (!picked) return
    // Копируем сразу: сброс значения поля ниже очищает и сам FileList.
    const chosen = Array.from(picked).filter(f => f.type.startsWith('image/'))
    setFiles(prev => [...prev, ...chosen].slice(0, MAX_PHOTOS - saved))
    if (picker.current) picker.current.value = ''
  }
  const setDate = (k: 'from' | 'to', v: string) => {
    if (!v) return
    const next = { ...(period ?? { from: v, to: v }), [k]: v }
    if (next.to < next.from) next[k === 'from' ? 'to' : 'from'] = v
    setPeriod(next)
  }

  if (editingId && list.isLoading) return <PageLoader />
  if (editingId && !editing) {
    return (
      <div className="page">
        <div className="card stack"><p>Запись не найдена: возможно, она уже удалена.</p><Link className="btn" to="/illness">К списку</Link></div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{editingId ? 'Изменить запись' : 'Записать болезнь'}</h1>
          <p className="sub">Отметьте дни в календаре, добавьте комментарий и фото справок. Запись видите только вы.</p>
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
                <button type="button" className="ill-thumb-x" aria-label="Убрать фото" onClick={() => dropDoc.mutate(d.id)}><X size={14} /></button>
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
          <button className="btn primary" disabled={save.isPending} onClick={() => { setError(''); save.mutate() }}>{editingId ? 'Сохранить изменения' : 'Сохранить запись'}</button>
          <Link className="btn ghost" to="/illness">Отмена</Link>
        </div>
      </section>

      {open && (
        <Sheet title="Фото документа" onClose={() => setOpen(null)}>
          <AuthImage className="photo-full" url={open} alt="Фото документа" />
        </Sheet>
      )}
    </div>
  )
}
