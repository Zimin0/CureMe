import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CreditCard } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, PayStatus } from '../api'
import { fmtDate } from '../format'
import { useToast } from './ui'

const WIDGET_SRC = 'https://yookassa.ru/checkout-widget/v1/checkout-widget.js'
type Widget = { render: (id: string) => Promise<void> | void; destroy?: () => void }
declare global {
  interface Window {
    YooMoneyCheckoutWidget?: new (o: { confirmation_token: string; return_url: string; error_callback?: (e: unknown) => void }) => Widget
  }
}

export const usePayStatus = (poll = false) => useQuery({
  queryKey: ['payments', 'me'], queryFn: () => api<PayStatus>('/payments/me'),
  refetchInterval: poll ? 2500 : false,
})

/** Если браузер заблокировал скрипт политикой безопасности (старая версия сайта в кеше), подсказываем обновить страницу. */
function loadWidget(): Promise<void> {
  if (window.YooMoneyCheckoutWidget) return Promise.resolve()
  return new Promise((resolve, reject) => {
    let blocked = false
    const onViolation = (e: Event) => { if (String((e as SecurityPolicyViolationEvent).blockedURI).includes('yookassa')) blocked = true }
    document.addEventListener('securitypolicyviolation', onViolation)
    const s = document.createElement('script')
    s.src = WIDGET_SRC
    s.onload = () => { document.removeEventListener('securitypolicyviolation', onViolation); resolve() }
    s.onerror = () => {
      document.removeEventListener('securitypolicyviolation', onViolation)
      reject(new Error(blocked
        ? 'Браузер заблокировал форму оплаты: обновите страницу (Ctrl+F5, на телефоне закройте и откройте сайт заново) и повторите.'
        : 'Не удалось загрузить форму оплаты ЮKassa. Проверьте интернет и повторите.'))
    }
    document.head.appendChild(s)
  })
}

const rub = (n: number) => `${n.toLocaleString('ru-RU')} ₽`
const PERIOD = { month: 'месяц', year: 'год' } as const
const STATUS = { pending: 'ожидает оплаты', succeeded: 'оплачено', canceled: 'не оплачено', refunded: 'возвращено' } as const

/** Оплата Плюса: выбор срока, согласие с офертой, галочка автопродления (по умолчанию выключена), форма ЮKassa. */
export function PayBox() {
  const toast = useToast()
  const qc = useQueryClient()
  const [params, setParams] = useSearchParams()
  const returned = params.get('paid')
  const status = usePayStatus(!!returned)
  const [period, setPeriod] = useState<'month' | 'year'>('month')
  const [agree, setAgree] = useState(false)
  const [renew, setRenew] = useState(false)
  const [token, setToken] = useState<{ value: string; id: number } | null>(null)
  const widget = useRef<Widget | null>(null)

  const start = useMutation({
    mutationFn: () => api<{ payment_id: number; confirmation_token: string }>('/payments', { method: 'POST', body: { period, auto_renew: renew && !!status.data?.recurring_enabled, agree } }),
    onSuccess: r => setToken({ value: r.confirmation_token, id: r.payment_id }),
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const off = useMutation({
    mutationFn: () => api<PayStatus>('/payments/auto-renew/off', { method: 'POST' }),
    onSuccess: s => { qc.setQueryData(['payments', 'me'], s); toast('Автопродление отключено, деньги больше не спишутся') },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  useEffect(() => {
    if (!token) return
    let dead = false
    loadWidget().then(() => {
      if (dead || !window.YooMoneyCheckoutWidget) return
      widget.current = new window.YooMoneyCheckoutWidget({
        confirmation_token: token.value,
        return_url: `${window.location.origin}/plus?paid=${token.id}`,
        error_callback: () => toast('Форма оплаты сообщила об ошибке. Попробуйте ещё раз.', 'error'),
      })
      return widget.current.render('yk-widget')
    }).catch((e: Error) => toast(e.message, 'error'))
    return () => { dead = true; widget.current?.destroy?.() }
  }, [token, toast])

  const s = status.data
  const paid = returned ? s?.payments.find(p => p.id === Number(returned)) : undefined
  useEffect(() => {
    if (paid && paid.status !== 'pending') {
      ['plan', 'family', 'overview'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
    }
  }, [paid?.status]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!s) return null
  if (!s.enabled && !s.auto_renew && s.payments.length === 0) return null  // nothing to show

  // Незавершённые попытки (закрыли форму) не показываем: остаётся только платёж, к которому вернулись с оплаты.
  const shownPayments = s.payments.filter(p => p.status !== 'pending' || String(p.id) === returned)
  const price = period === 'month' ? s.price_month : s.price_year
  const canPay = s.enabled && !!price

  return (
    <section className="card stack" aria-label="Оплата">
      <h2 className="row" style={{ gap: 8 }}><CreditCard size={20} />Оплата Плюса</h2>

      {returned && (
        <p role="status" className="badge info" style={{ whiteSpace: 'normal' }}>
          {!paid || paid.status === 'pending' ? 'Проверяем оплату, это займёт несколько секунд…'
            : paid.status === 'succeeded' ? 'Оплата прошла, Плюс включён. Чек придёт на вашу почту.'
              : 'Оплата не прошла, деньги не списаны. Можно попробовать ещё раз.'}
        </p>
      )}

      {s.auto_renew && (
        <div className="stack">
          <p>Автопродление включено{s.plus_until ? `: следующее списание ${fmtDate(s.plus_until)}` : ''}. За три дня до списания мы напишем на почту.</p>
          <button className="btn danger" onClick={() => off.mutate()} disabled={off.isPending}>Отключить автопродление</button>
        </div>
      )}

      {canPay && !token && (
        <form className="stack" onSubmit={e => { e.preventDefault(); if (agree) { setParams({}, { replace: true }); start.mutate() } }}>
          <div className="segmented" role="radiogroup" aria-label="Срок подписки">
            {(['month', 'year'] as const).map(p => {
              const v = p === 'month' ? s.price_month : s.price_year
              return v ? (
                <button key={p} type="button" role="radio" aria-checked={period === p} className={period === p ? 'on' : ''}
                  onClick={() => setPeriod(p)}>{rub(v)} за {PERIOD[p]}</button>
              ) : null
            })}
          </div>
          <label className="check">
            <input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />
            <span>Я согласен(на) с <Link to="/offer" target="_blank">публичной офертой</Link>, <Link to="/terms" target="_blank">Пользовательским соглашением</Link> и <Link to="/privacy" target="_blank">Политикой обработки персональных данных</Link></span>
          </label>
          {s.recurring_enabled && (
            <label className="check">
              <input type="checkbox" checked={renew} onChange={e => setRenew(e.target.checked)} />
              <span>Сохранить способ оплаты и автоматически продлевать подписку. За три дня до списания пришлём письмо, отключить можно в любой момент.</span>
            </label>
          )}
          <p className="muted small">Данные банковской карты вводятся в платёжной форме ЮKassa и на наш сервер не передаются.</p>
          <button className="btn primary" disabled={!agree || start.isPending}>Оплатить {price ? rub(price) : ''}</button>
        </form>
      )}
      {token && <div id="yk-widget" />}

      {shownPayments.length > 0 && (
        <div className="stack">
          <h3>Ваши оплаты</h3>
          {shownPayments.map(p => (
            <div key={p.id} className="row between small">
              <span>{fmtDate(p.paid_at ?? p.created_at)}, {rub(p.amount)} за {PERIOD[p.period]}{p.recurring ? ' (автопродление)' : ''}</span>
              <span>{STATUS[p.status]}{p.receipt_url && <> · <a href={p.receipt_url} target="_blank" rel="noreferrer noopener">чек</a></>}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
