import { useMutation, useQueryClient } from '@tanstack/react-query'
import { MessageSquarePlus, Pencil } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Intake } from '../api'
import { useFamilyPath } from '../auth'
import { dayTitle, fmtQty, fmtTime } from '../format'
import { Sheet, useToast } from './ui'

/** Окно с полем комментария: и для «Принял с комментарием», и чтобы дописать комментарий позже. */
export function CommentSheet({ title, initial = '', submitLabel, pending, error, onSubmit, onClose }: {
  title: string; initial?: string; submitLabel: string; pending?: boolean; error?: string
  onSubmit: (comment: string) => void; onClose: () => void
}) {
  const [text, setText] = useState(initial)
  return (
    <Sheet title={title} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); onSubmit(text.trim()) }}>
        <label className="field"><span>Комментарий</span>
          <textarea autoFocus aria-label="Комментарий" maxLength={1000} placeholder="Например: болела голова после работы" value={text}
            onChange={e => setText(e.target.value)} />
          <span className="hint">Комментарий видите только вы</span>
        </label>
        {error && <div className="alert error">{error}</div>}
        <button className="btn primary block" disabled={pending}>{submitLabel}</button>
      </form>
    </Sheet>
  )
}

/** История приёма, разбитая по дням. showMedicine — показывать название (в общей истории). */
export function IntakeList({ items, showMedicine }: { items: Intake[]; showMedicine?: boolean }) {
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const [editing, setEditing] = useState<Intake | null>(null)
  const save = useMutation({
    mutationFn: ({ id, comment }: { id: number; comment: string }) =>
      api<Intake>(fam(`/intakes/${id}`), { method: 'PATCH', body: { comment } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intakes'] })
      toast('Комментарий сохранён')
      setEditing(null)
    },
  })

  const days: { title: string; items: Intake[] }[] = []
  for (const i of items) {
    const title = dayTitle(i.taken_at)
    if (days.at(-1)?.title !== title) days.push({ title, items: [] })
    days.at(-1)!.items.push(i)
  }

  return (
    <>
      {days.map(d => (
        <div key={d.title} className="intake-day">
          <h3 className="intake-day-title">{d.title}</h3>
          {d.items.map(i => (
            <div key={i.id} className="intake">
              <span className="intake-time">{fmtTime(i.taken_at)}</span>
              <div className="grow" style={{ minWidth: 0 }}>
                <div className="row wrap" style={{ gap: 6 }}>
                  {showMedicine && (i.medicine_id
                    ? <Link to={`/medicines/${i.medicine_id}`} className="intake-med">{i.medicine_name}</Link>
                    : <span className="intake-med" title="Лекарство удалено из аптечки">{i.medicine_name}</span>)}
                  <strong>{fmtQty(i.amount)} {i.unit}</strong>
                  <span className="small muted">{i.mine ? 'вы' : i.user_name}</span>
                </div>
                {i.comment && <p className="intake-comment">{i.comment}</p>}
              </div>
              {i.mine && (
                <button className="icon-btn" title={i.comment ? 'Изменить комментарий' : 'Добавить комментарий'}
                  aria-label={i.comment ? 'Изменить комментарий' : 'Добавить комментарий'} onClick={() => setEditing(i)}>
                  {i.comment ? <Pencil size={16} /> : <MessageSquarePlus size={16} />}
                </button>
              )}
            </div>
          ))}
        </div>
      ))}
      {editing && (
        <CommentSheet title={`${editing.medicine_name}, ${fmtTime(editing.taken_at)}`} initial={editing.comment}
          submitLabel="Сохранить" pending={save.isPending} error={save.error?.message}
          onSubmit={comment => save.mutate({ id: editing.id, comment })} onClose={() => setEditing(null)} />
      )}
    </>
  )
}
