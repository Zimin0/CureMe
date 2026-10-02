import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bell, Mail, UserCheck } from 'lucide-react'
import { FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, SchedulePrefs, TrustedStatus } from '../api'
import { PlusBanner } from '../plan'
import { useToast } from './ui'

const KEY = ['schedule-notifications']
const LEAD = [5, 10, 15, 30, 60]
const REPEAT = [5, 10, 15, 30]
const ESCALATE = [10, 15, 30, 60]
const SHARE_CONSENT = 'Разрешаю передавать указанному мной доверенному лицу сведения о факте выполнения/пропуска запланированного приёма препарата'
const STATUS: Record<TrustedStatus, { label: string; badge: string }> = {
  pending: { label: 'Ждём согласия', badge: 'info' },
  confirmed: { label: 'Согласился(ась)', badge: 'ok' },
  declined: { label: 'Отказался(ась)', badge: 'expired' },
  revoked: { label: 'Отписался(ась)', badge: 'expired' },
}

/** Минуты чипами с готовыми значениями и ползунком для любого другого. */
function Minutes({ value, options, max, onChange, label }: { value: number; options: number[]; max: number; onChange: (n: number) => void; label: string }) {
  return (
    <div className="stack" style={{ gap: 6 }} role="group" aria-label={label}>
      <div className="chips wrap">
        {options.map(n => <button key={n} type="button" className={`chip${value === n ? ' active' : ''}`} onClick={() => onChange(n)}>{n} мин</button>)}
      </div>
      <div className="row">
        <input type="range" min={1} max={max} step={1} value={value} aria-label={`${label}: своё значение`} style={{ flex: 1 }}
          onChange={e => onChange(Number(e.target.value))} />
        <span className="muted small" style={{ minWidth: 56, textAlign: 'right' }}>{value} мин</span>
      </div>
    </div>
  )
}

/**
 * Блок «Уведомления» на вкладке «Расписание»: письмо себе за N минут до приёма, повтор, если приём не отмечен,
 * и письмо доверенному человеку. Функция Плюса. Доверенному письма идут только после его согласия по ссылке из письма.
 */
export function ScheduleNotify() {
  const qc = useQueryClient()
  const toast = useToast()
  const { data: p } = useQuery({
    queryKey: KEY, queryFn: () => api<SchedulePrefs>('/schedule-notifications'),
    refetchInterval: q => (q.state.data?.trusted?.status === 'pending' ? 5000 : false),  // ждём, пока человек ответит на письмо
  })
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [attest, setAttest] = useState(false)
  const onError = (e: Error) => toast(e.message, 'error')
  const save = useMutation({
    mutationFn: (body: Partial<SchedulePrefs> & { escalate_consent?: boolean }) => api<SchedulePrefs>('/schedule-notifications', { method: 'PUT', body }),
    onSuccess: d => qc.setQueryData(KEY, d), onError,
  })
  const invite = useMutation({
    mutationFn: () => api<SchedulePrefs>('/schedule-notifications/trusted', { body: { name, email, attest } }),
    onSuccess: d => { qc.setQueryData(KEY, d); setName(''); setEmail(''); setAttest(false); toast('Отправили письмо с просьбой согласиться') },
    onError,
  })
  const resend = useMutation({
    mutationFn: () => api<SchedulePrefs>('/schedule-notifications/trusted/resend', { method: 'POST' }),
    onSuccess: d => { qc.setQueryData(KEY, d); toast('Письмо отправлено ещё раз') }, onError,
  })
  const remove = useMutation({
    mutationFn: () => api('/schedule-notifications/trusted', { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: KEY }); toast('Доверенный человек убран, его почта удалена') }, onError,
  })
  if (!p) return null
  const locked = !p.available
  const set = (body: Partial<SchedulePrefs> & { escalate_consent?: boolean }) => save.mutate(body)
  const t = p.trusted
  const submit = (e: FormEvent) => { e.preventDefault(); invite.mutate() }

  return (
    <section className="card stack" data-testid="schedule-notify">
      <div className="card-head"><h2><Bell size={18} style={{ verticalAlign: -3 }} /> Уведомления</h2></div>
      <p className="muted small">
        Напомним о приёме письмом. Уведомления — вспомогательная функция: письма могут приходить с задержкой
        или не приходить, поэтому не полагайтесь на них одни. Капсулка не заменяет врача.
      </p>
      {locked && (
        <PlusBanner testId="plus-banner" title="Уведомления — в Капсулке Плюс" to="/plus" cta="Узнать про Плюс"
          text="Подключите Плюс, и мы напомним о приёме и сообщим доверенному человеку, если вы забыли." />
      )}

      {!locked && <fieldset className="locked-block stack">
        <label className="check">
          <input type="checkbox" checked={p.enabled} disabled={!p.email_possible && !p.enabled}
            onChange={e => set({ enabled: e.target.checked })} />
          <span><Mail size={14} style={{ verticalAlign: -2 }} /> Напоминать мне на почту {p.email}
            {!p.email_possible && <><br /><span className="muted small">Отправка писем на сайте пока не настроена</span></>}
          </span>
        </label>

        {p.enabled && (
          <>
            <div className="stack" style={{ gap: 6 }}>
              <h3>Напомнить за</h3>
              <Minutes label="Напомнить за" value={p.lead_minutes} options={LEAD} max={120} onChange={n => set({ lead_minutes: n })} />
            </div>
            <div className="stack" style={{ gap: 6 }}>
              <h3>Если приём не отмечен, напомнить снова через</h3>
              <Minutes label="Повторное напоминание" value={p.repeat_minutes} options={REPEAT} max={60} onChange={n => set({ repeat_minutes: n })} />
              <span className="muted small">Отметкой считается «Принял(а)» в Капсулке: она попадает в историю приёма.</span>
            </div>

            <div className="stack" style={{ gap: 10 }}>
              <h3><UserCheck size={16} style={{ verticalAlign: -3 }} /> Доверенный человек</h3>
              <p className="muted small">
                Если вы и после повторного напоминания не отметили приём, мы напишем ему. Письма начнут приходить только
                после того, как он сам согласится по ссылке из письма; отписаться он сможет в любой момент.
              </p>
              {t ? (
                <div className="stack" style={{ gap: 8 }}>
                  <div className="row wrap" style={{ justifyContent: 'space-between' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700 }}>{t.name || 'Доверенный человек'}</div>
                      {t.email && <div className="muted small ellipsis">{t.email}</div>}
                    </div>
                    <span className={`badge ${STATUS[t.status].badge}`}>{STATUS[t.status].label}</span>
                  </div>
                  <div className="row wrap">
                    {t.status === 'pending' && <button className="btn ghost sm" disabled={resend.isPending} onClick={() => resend.mutate()}>Отправить письмо ещё раз</button>}
                    <button className="btn ghost sm" disabled={remove.isPending} onClick={() => remove.mutate()}>Убрать и удалить почту</button>
                  </div>
                  {(t.status === 'declined' || t.status === 'revoked') && (
                    <p className="muted small">Этот человек отказался получать письма, его имя и почта удалены. Чтобы пригласить кого-то, уберите эту запись и добавьте заново.</p>
                  )}
                  <div className="stack consent-box" style={{ gap: 8 }} data-testid="share-consent">
                    <h3>Отдельное согласие</h3>
                    <label className="check">
                      <input type="checkbox" checked={p.escalate_enabled} disabled={!p.escalate_enabled && t.status !== 'confirmed'}
                        onChange={e => set(e.target.checked ? { escalate_enabled: true, escalate_consent: true } : { escalate_enabled: false })} />
                      <span><b>{SHARE_CONSENT}</b>{t.status !== 'confirmed' && <><br /><span className="muted small">Включится, когда этот человек сам согласится по ссылке из письма</span></>}</span>
                    </label>
                    <details className="small muted">
                      <summary>Что это значит</summary>
                      <p>Такое письмо сообщает доверенному лицу сведения о вашем здоровье: что вам назначен приём лекарства и что он не отмечен. Согласие даётся отдельно от
                        регистрации и Пользовательского соглашения, добровольно и только на эту передачу; отказ от него не ограничивает остальные функции. Адресат — только указанный вами человек, письмо
                        без названия препарата, если вы не включили эту опцию ниже. Снять согласие можно здесь же, сняв отметку: письма прекратятся сразу, дата и редакция согласия сохраняются в учёте оператора
                        Полный текст: <Link to="/consent-share">Согласие на передачу сведений доверенному лицу</Link>.</p>
                    </details>
                    {p.escalate_enabled && p.escalate_consent_at && (
                      <span className="muted small">Согласие дано {new Date(p.escalate_consent_at).toLocaleString('ru-RU')}. Чтобы отозвать, снимите отметку.</span>
                    )}
                  </div>
                  {p.escalate_enabled && (
                    <>
                      <h3>Написать ему через</h3>
                      <Minutes label="Письмо доверенному" value={p.escalate_minutes} options={ESCALATE} max={120} onChange={n => set({ escalate_minutes: n })} />
                      <span className="muted small">Отсчёт идёт после повторного напоминания вам.</span>
                      <label className="check">
                        <input type="checkbox" checked={p.share_medicine_name} onChange={e => set({ share_medicine_name: e.target.checked })} />
                        <span>Называть лекарство в письме<br /><span className="muted small">По умолчанию письмо только сообщает, что плановый приём не отмечен: название лекарства — сведения о вашем здоровье</span></span>
                      </label>
                    </>
                  )}
                </div>
              ) : (
                <form className="stack" style={{ gap: 10 }} onSubmit={submit}>
                  <label className="field"><span>Как его зовут</span>
                    <input className="input" value={name} maxLength={100} onChange={e => setName(e.target.value)} autoComplete="off" />
                  </label>
                  <label className="field"><span>Его почта</span>
                    <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} autoComplete="off" />
                  </label>
                  <label className="check">
                    <input type="checkbox" checked={attest} onChange={e => setAttest(e.target.checked)} />
                    <span className="small">Я сообщил(а) этому человеку, что указываю его почту, и он не против. Я понимаю, что отвечаю за чужие данные, которые ввожу</span>
                  </label>
                  <button className="btn" type="submit" disabled={!name.trim() || !email.includes('@') || !attest || invite.isPending}>Отправить приглашение</button>
                </form>
              )}
            </div>
          </>
        )}
      </fieldset>}
    </section>
  )
}
