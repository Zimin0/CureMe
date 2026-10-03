import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Copy, Receipt } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { AdminPayment, api } from '../api'
import { useAuth } from '../auth'
import { copyText } from '../clipboard'
import { Empty, PageLoader, useToast } from '../components/ui'
import { fmtDate } from '../format'

const PERIOD = { month: '1 месяц', year: '1 год' } as const
const STATUS = { pending: 'ожидает оплаты', succeeded: 'оплачено', canceled: 'не оплачено', refunded: 'возвращено' } as const

/** Услуга и сумма для чека в «Мой налог»: копируется одной кнопкой. */
const receiptText = (p: AdminPayment) => `Подписка Капсулка Плюс на ${PERIOD[p.period]}, ${p.amount} ₽ (оплата через ЮKassa)`

function PaymentRow({ p }: { p: AdminPayment }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [url, setUrl] = useState(p.receipt_url ?? '')
  const done = () => qc.invalidateQueries({ queryKey: ['admin', 'payments'] })
  const save = useMutation({
    mutationFn: (send_email: boolean) => api<AdminPayment>(`/admin/payments/${p.id}/receipt`, { method: 'PUT', body: { url: url.trim(), send_email } }),
    onSuccess: (r, send) => { done(); toast(send ? `Чек отправлен на ${r.email}` : 'Ссылка на чек сохранена') },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const clear = useMutation({
    mutationFn: () => api<AdminPayment>(`/admin/payments/${p.id}/receipt`, { method: 'DELETE' }),
    onSuccess: () => { setUrl(''); done(); toast('Чек сброшен') },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const recheck = useMutation({
    mutationFn: () => api<AdminPayment>(`/admin/payments/${p.id}/sync`, { method: 'POST' }),
    onSuccess: r => { done(); toast(r.status === 'succeeded' ? 'Платёж оплачен, Плюс выдан' : `В ЮKassa статус: ${STATUS[r.status]}`) },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const payable = p.status === 'succeeded' || p.status === 'refunded'

  return (
    <article className="card stack" style={{ padding: 16 }}>
      <div className="row between wrap" style={{ gap: 8 }}>
        <div>
          <b>{p.amount} ₽</b> за {PERIOD[p.period]}{p.recurring ? ' (автопродление)' : ''}
          <div className="small muted">{fmtDate(p.paid_at ?? p.created_at)} · {p.user_name ? `${p.user_name}, ` : ''}{p.email}</div>
        </div>
        <span className={`badge ${p.status === 'succeeded' ? 'ok' : p.status === 'pending' ? 'info' : 'out'}`}>{STATUS[p.status]}</span>
      </div>
      {p.status === 'pending' && (
        <div className="row small" style={{ gap: 8 }}>
          <span className="muted grow">Если человек оплатил, а Плюс не включился, проверьте платёж в ЮKassa.</span>
          <button type="button" className="btn ghost" onClick={() => recheck.mutate()} disabled={recheck.isPending}>Проверить в ЮKassa</button>
        </div>
      )}
      {payable && (
        <>
          <div className="row small" style={{ gap: 8 }}>
            <span className="muted grow">Для чека: {receiptText(p)}</span>
            <button type="button" className="btn ghost" aria-label="Скопировать данные для чека"
              onClick={async () => toast((await copyText(receiptText(p))) ? 'Скопировано' : 'Не удалось скопировать')}><Copy size={16} /></button>
          </div>
          <form className="row wrap" style={{ gap: 8 }} onSubmit={e => { e.preventDefault(); save.mutate(true) }}>
            <input className="input grow" type="url" inputMode="url" placeholder="Ссылка на чек из «Мой налог»" aria-label={`Ссылка на чек, оплата ${p.id}`}
              value={url} onChange={e => setUrl(e.target.value)} />
            <button className="btn primary" disabled={!url.trim() || save.isPending}>
              {p.receipt_sent_at ? 'Отправить ещё раз' : 'Отправить покупателю'}
            </button>
            <button type="button" className="btn ghost" disabled={!url.trim() || save.isPending} onClick={() => save.mutate(false)}>Сохранить без письма</button>
          </form>
          {p.receipt_url && (
            <div className="small row between wrap" style={{ gap: 8 }}>
              <span>
                {p.receipt_sent_at ? `Чек отправлен покупателю ${fmtDate(p.receipt_sent_at)}` : 'Ссылка сохранена, письмо не отправлялось'}
                {' · '}<a href={p.receipt_url} target="_blank" rel="noreferrer noopener">открыть чек</a>
              </span>
              <button className="btn ghost" onClick={() => clear.mutate()} disabled={clear.isPending}>Сбросить</button>
            </div>
          )}
        </>
      )}
    </article>
  )
}

/** Список оплат для ручного оформления чеков самозанятого (422-ФЗ): чек делается в «Мой налог», ссылка уходит покупателю. */
export function AdminPayments() {
  const { me } = useAuth()
  const [onlyTodo, setOnlyTodo] = useState(true)
  const list = useQuery({ queryKey: ['admin', 'payments'], queryFn: () => api<AdminPayment[]>('/admin/payments'), enabled: !!me?.is_admin })
  if (!me?.is_admin) return <Navigate to="/" replace />
  if (list.isLoading) return <PageLoader />
  const all = list.data ?? []
  const todo = all.filter(p => p.status === 'succeeded' && !p.receipt_sent_at)
  const shown = onlyTodo ? todo : all

  return (
    <div className="page stack" style={{ maxWidth: 760 }}>
      <Link to="/admin?tab=plans" className="row small muted" style={{ gap: 6 }}><ArrowLeft size={14} />Администрирование</Link>
      <div className="page-head">
        <div>
          <h1 className="row" style={{ gap: 10 }}><Receipt size={26} />Оплаты и чеки</h1>
          <p className="sub">Чек самозанятого оформляется в приложении «Мой налог». Вставьте ссылку на чек, и она уйдёт покупателю на почту.</p>
        </div>
      </div>
      <div className="segmented" role="tablist">
        <button role="tab" aria-selected={onlyTodo} className={onlyTodo ? 'on' : ''} onClick={() => setOnlyTodo(true)}>Нужен чек ({todo.length})</button>
        <button role="tab" aria-selected={!onlyTodo} className={!onlyTodo ? 'on' : ''} onClick={() => setOnlyTodo(false)}>Все оплаты ({all.length})</button>
      </div>
      {shown.length === 0 && <Empty icon={<Receipt size={28} />} title={onlyTodo ? 'Чеков к оформлению нет' : 'Оплат пока не было'} />}
      {shown.map(p => <PaymentRow key={p.id} p={p} />)}
    </div>
  )
}
