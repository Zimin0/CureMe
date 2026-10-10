import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Illness } from '../api'
import { AuthImage } from '../components/AuthImage'
import { IntakeTabs } from '../components/IntakeTabs'
import { Empty, PageLoader, Sheet, useToast } from '../components/ui'
import { periodLabel } from '../illness'

/** Личная история болезней: список записей, новые сверху. Записать новую и править старую — на странице формы. Видна только автору. */
export function IllnessHistory() {
  const qc = useQueryClient()
  const toast = useToast()
  const list = useQuery({ queryKey: ['illnesses'], queryFn: () => api<Illness[]>('/illnesses') })
  const [open, setOpen] = useState<string | null>(null)
  const records = list.data ?? []

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/illnesses/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['illnesses'] }); toast('Запись удалена') },
  })

  return (
    <div className="page">
      <IntakeTabs />
      <div className="page-head">
        <div>
          <h1>История болезней</h1>
          <p className="sub">Когда болели, что делали и фото справок. Записи личные: их видите только вы, даже члены семьи их не увидят.</p>
        </div>
        <Link className="btn primary" to="/illness/new"><Plus size={18} />Записать</Link>
      </div>

      {list.isLoading ? <PageLoader /> : records.length === 0 ? (
        <div className="card">
          <Empty icon="🩺" title="Пока пусто" text="Нажмите «Записать», отметьте дни в календаре и сохраните первую запись."
            action={<Link className="btn primary" to="/illness/new"><Plus size={18} />Записать</Link>} />
        </div>
      ) : (
        <section className="card" aria-label="Записи">
          {records.map(r => (
            <article key={r.id} className="ill-record">
              <div className="row between">
                <div className="grow">
                  <b>{periodLabel(r.date_from, r.date_to)}</b>
                  {r.title && <div className="ill-title">{r.title}</div>}
                </div>
                <Link className="icon-btn" to={`/illness/${r.id}/edit`} aria-label="Изменить запись"><Pencil size={16} /></Link>
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
