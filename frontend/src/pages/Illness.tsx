import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Paperclip, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, Illness } from '../api'
import { AttachmentViewer } from '../components/AttachmentViewer'
import { IntakeTabs } from '../components/IntakeTabs'
import { Empty, PageLoader, useToast } from '../components/ui'
import { periodLabel } from '../illness'
import { usePlan, useRequirePlus } from '../plan'

/** Личная история болезней: список записей, новые сверху. Записать новую и править старую — на странице формы. Видна только автору. */
export function IllnessHistory() {
  const qc = useQueryClient()
  const toast = useToast()
  const nav = useNavigate()
  const { available } = usePlan()
  const locked = !available('illness')
  const requirePlus = useRequirePlus()
  const list = useQuery({ queryKey: ['illnesses'], queryFn: () => api<Illness[]>('/illnesses') })
  const [viewing, setViewing] = useState<Illness | null>(null)
  const records = list.data ?? []

  const remove = useMutation({
    mutationFn: (id: number) => api<void>(`/illnesses/${id}`, { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['illnesses'] }); toast('Запись удалена') },
  })

  // Новые записи платные: без Плюса кнопка открывает шторку, а уже созданное можно смотреть, править и удалять.
  const write = () => requirePlus('illness', () => nav('/illness/new'))
  const writeBtn = <button className={`btn ${locked ? 'plus-cta' : 'primary'}`} onClick={write}><Plus size={18} />Записать</button>

  return (
    <div className="page">
      <IntakeTabs />
      <div className="page-head">
        <div>
          <h1>История болезней</h1>
          <p className="sub">Когда болели, что делали и фото справок. Записи личные: их видите только вы, даже члены семьи их не увидят.</p>
        </div>
        {writeBtn}
      </div>

      {list.isLoading ? <PageLoader /> : records.length === 0 ? (
        <div className="card">
          <Empty icon="🩺" title="Пока пусто" text="Нажмите «Записать», отметьте дни в календаре и сохраните первую запись."
            action={writeBtn} />
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
                <button type="button" className="badge ok ill-attach" onClick={() => setViewing(r)}>
                  <Paperclip size={13} />Есть вложения ({r.documents.length})
                </button>
              )}
            </article>
          ))}
        </section>
      )}

      {viewing && <AttachmentViewer docs={viewing.documents} onClose={() => setViewing(null)} />}
    </div>
  )
}
