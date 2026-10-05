import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Mail, Send } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { PlusBanner } from '../plan'
import { api, NotificationPrefs } from '../api'
import { useToast } from './ui'

const KEY = ['notifications']
const DAYS = [7, 14, 30, 60]

/** Раздел «Напоминания» на странице «Семья»: куда слать (почта, Telegram) и о чём. Функция Плюса. */
export function Reminders() {
  const qc = useQueryClient()
  const toast = useToast()
  // Ссылка на бота: пока она открыта, раз в 3 секунды проверяем, привязался ли Telegram.
  const [tgLink, setTgLink] = useState<string | null>(null)
  const [tgConsent, setTgConsent] = useState(false)
  const { data: p } = useQuery({
    queryKey: KEY, queryFn: () => api<NotificationPrefs>('/notifications'),
    refetchInterval: q => (tgLink && !q.state.data?.telegram_connected ? 3000 : false),
  })
  const onError = (e: Error) => toast(e.message, 'error')
  const save = useMutation({
    mutationFn: (body: Partial<NotificationPrefs>) => api<NotificationPrefs>('/notifications', { method: 'PUT', body }),
    onSuccess: d => qc.setQueryData(KEY, d), onError,
  })
  const link = useMutation({
    mutationFn: () => api<{ url: string }>('/notifications/telegram/link', { body: { consent: true } }),
    onSuccess: d => setTgLink(d.url), onError,
  })
  const unlink = useMutation({
    mutationFn: () => api('/notifications/telegram', { method: 'DELETE' }),
    onSuccess: () => { setTgLink(null); qc.invalidateQueries({ queryKey: KEY }); toast('Telegram отключён') }, onError,
  })
  const test = useMutation({
    mutationFn: () => api('/notifications/test', { method: 'POST' }),
    onSuccess: () => toast('Отправили пробное напоминание'), onError,
  })
  if (!p) return null

  const locked = !p.available
  const anyChannel = p.email_enabled || p.telegram_enabled
  const set = (body: Partial<NotificationPrefs>) => save.mutate(body)

  return (
    <section className="card stack" data-testid="reminders">
      <div className="card-head">
        <h2><Bell size={18} style={{ verticalAlign: -3 }} /> Напоминания</h2>
      </div>
      <p className="muted small">
        Раз в день пришлём одно сообщение, если лекарство заканчивается или у него скоро истекает срок.
        Об одном и том же повторять не будем.
      </p>
      {locked && (
        <PlusBanner testId="plus-banner" title="Напоминания — в Капсулке Плюс" to="/plus" cta="Узнать про Плюс"
          text="Подключите Плюс, и мы сами напомним о лекарствах, которые заканчиваются или портятся." />
      )}

      {!locked && <>
      <h3>Куда</h3>
      <label className="check">
        <input type="checkbox" checked={p.email_enabled} disabled={(!p.email_possible || locked) && !p.email_enabled}
          onChange={e => set({ email_enabled: e.target.checked })} />
        <span><Mail size={14} style={{ verticalAlign: -2 }} /> На почту {p.email}
          {!p.email_possible && <><br /><span className="muted small">Отправка писем на сайте пока не настроена</span></>}
        </span>
      </label>

      {/* Админ выключил Telegram (по умолчанию): про него на странице ничего не показываем. */}
      {!p.telegram_possible ? null : p.telegram_connected ? (
        <div className="row wrap" style={{ justifyContent: 'space-between' }}>
          <label className="check">
            <input type="checkbox" checked={p.telegram_enabled} disabled={locked && !p.telegram_enabled}
              onChange={e => set({ telegram_enabled: e.target.checked })} />
            <span><Send size={14} style={{ verticalAlign: -2 }} /> В Telegram {p.telegram_name ?? ''}</span>
          </label>
          <button className="btn ghost sm" onClick={() => unlink.mutate()}>Отключить</button>
        </div>
      ) : tgLink ? (
        <div className="stack" style={{ gap: 8 }}>
          <a className="btn primary" href={tgLink} target="_blank" rel="noopener noreferrer"><Send size={16} />Открыть Telegram</a>
          <span className="muted small">В чате с ботом нажмите «Запустить». Ссылка одноразовая и действует час; эта страница обновится сама.</span>
        </div>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          {/* Telegram — иностранный сервис: отдельное согласие на трансграничную передачу (ст. 12 152-ФЗ). */}
          <label className="check">
            <input type="checkbox" checked={tgConsent} disabled={locked} onChange={e => setTgConsent(e.target.checked)} />
            <span className="small">
              Согласен(на) на <Link to="/consent-telegram">передачу данных напоминаний в Telegram</Link>: названия лекарств,
              сроки и остатки пойдут через серверы Telegram за рубежом
            </span>
          </label>
          <button className="btn" disabled={locked || !tgConsent || link.isPending} onClick={() => link.mutate()}>
            <Send size={16} />Подключить Telegram
          </button>
        </div>
      )}

      <h3>О чём</h3>
      <label className="check">
        <input type="checkbox" checked={p.notify_low} onChange={e => set({ notify_low: e.target.checked })} />
        <span>Лекарство заканчивается<br />
          <span className="muted small">Порог задаётся у лекарства: «Изменить» → «Напомнить, когда останется»</span>
        </span>
      </label>
      <label className="check">
        <input type="checkbox" checked={p.notify_expiry} onChange={e => set({ notify_expiry: e.target.checked })} />
        <span>Скоро истечёт срок годности</span>
      </label>
      {p.notify_expiry && (
        <label className="field"><span>Предупредить за</span>
          <select value={p.expiry_days} onChange={e => set({ expiry_days: Number(e.target.value) })}>
            {[...new Set([...DAYS, p.expiry_days])].sort((a, b) => a - b).map(d => <option key={d} value={d}>{d} дней</option>)}
          </select>
        </label>
      )}
      <label className="check">
        <input type="checkbox" checked={p.notify_expired} onChange={e => set({ notify_expired: e.target.checked })} />
        <span>Срок годности уже истёк</span>
      </label>
      {anyChannel && (
        <button className="btn ghost" disabled={test.isPending} onClick={() => test.mutate()}>Прислать пробное напоминание</button>
      )}
      </>}
    </section>
  )
}
