import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronRight, Copy, Crown, LogOut, Pencil, RefreshCw, Share2, Shield, Sparkles, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, Family as FamilyT } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { Cabinets } from '../components/Cabinets'
import { CompressSection } from '../components/PlusEnding'
import { DeleteAccountButton } from '../components/DeleteAccount'
import { Reminders } from '../components/Reminders'
import { PageLoader, Sheet, useToast } from '../components/ui'
import { copyText } from '../clipboard'
import { avatarColor, fmtDateTime } from '../format'
import { useLimitReached } from '../limits'
import { LimitCounter, planLabel, usePlan } from '../plan'
import { versionLabel } from '../version'
import { LegalLinks } from './Legal'

export function Family() {
  const { me, familyId, refresh, signOut } = useAuth()
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const key = ['family', familyId]
  const { data: f, isLoading } = useQuery({ queryKey: key, queryFn: () => api<FamilyT>(fam('')) })
  const { plan } = usePlan()

  const [rename, setRename] = useState<string | null>(null)

  const onFam = (d: FamilyT, msg?: string) => { qc.setQueryData(key, d); if (msg) toast(msg) }
  // На 402 (лимит бесплатной версии) шторка Плюса открывается сама, тост не нужен.
  const onError = (e: Error) => { if (!(e instanceof ApiError && e.status === 402)) toast(e.message, 'error') }
  const membersFull = useLimitReached('members')

  // Передача владения только с согласием принимающего (R23): предложить, попросить, принять, отказаться, забрать.
  const offer = useMutation({
    mutationFn: (uid: number) => api<FamilyT>(fam('/owner-transfer'), { method: 'POST', body: { user_id: uid } }),
    onSuccess: d => onFam(d, 'Предложение отправлено, ждём ответа'), onError,
  })
  const askToPay = useMutation({
    mutationFn: () => api<FamilyT>(fam('/owner-request'), { method: 'POST' }),
    onSuccess: d => onFam(d, 'Просьба отправлена владельцу'), onError,
  })
  const answer = useMutation({
    mutationFn: (accept: boolean) => api<FamilyT>(fam(`/owner-transfer/${accept ? 'accept' : 'decline'}`), { method: 'POST' }),
    onSuccess: async (d, accept) => { onFam(d, accept ? 'Готово, владелец семьи сменился' : 'Вы отказались'); await refresh(); qc.invalidateQueries({ queryKey: ['plan'] }) }, onError,
  })
  const withdraw = useMutation({
    mutationFn: () => api<FamilyT>(fam('/owner-transfer'), { method: 'DELETE' }),
    onSuccess: async d => { onFam(d, 'Предложение отменено'); await refresh() }, onError,
  })
  const removeMember = useMutation({
    mutationFn: (uid: number) => api(fam(`/members/${uid}`), { method: 'DELETE' }),
    onSuccess: async (_, uid) => {
      if (uid === me?.id) { await refresh(); toast('Вы вышли из семьи') }
      else { qc.invalidateQueries({ queryKey: key }); qc.invalidateQueries({ queryKey: ['plan'] }); toast('Участник удалён') }
    },
    onError,
  })
  const regen = useMutation({ mutationFn: () => api<FamilyT>(fam('/invite'), { method: 'POST' }), onSuccess: d => onFam(d, 'Новая ссылка создана, старая больше не работает'), onError })
  const doRename = useMutation({
    mutationFn: (name: string) => api<FamilyT>(fam(''), { method: 'PATCH', body: { name } }),
    onSuccess: d => { onFam(d, 'Название изменено'); setRename(null); refresh() }, onError,
  })
  if (isLoading || !f) return <PageLoader />
  const owner = f.role === 'owner'
  const transfer = f.owner_transfer ?? null
  const cooldownUntil = f.next_transfer_at && new Date(f.next_transfer_at) > new Date() ? f.next_transfer_at : null
  const link = `${location.origin}/join/${f.invite_code ?? ''}`

  const copyLink = async () => {
    const ok = await copyText(link)
    toast(ok ? 'Ссылка скопирована' : `Не удалось скопировать, ссылка: ${link}`, ok ? undefined : 'error')
  }

  return (
    <div className="page" style={{ maxWidth: 820 }}>
      <div className="page-head">
        <div>
          <h1>{f.name}</h1>
          <p className="sub">{f.members.length} в семье · общая аптечка, личные отметки у каждого свои</p>
        </div>
        {owner && <button className="btn ghost" onClick={() => setRename(f.name)}><Pencil size={16} />Переименовать</button>}
      </div>

      {transfer && (
        <section className="alert info stack" role="status" aria-label="Передача владения">
          <div>
            {transfer.can_answer && transfer.kind === 'offer' && <>{transfer.from_name} предлагает вам стать владельцем семьи: владелец приглашает людей и оплачивает Плюс. Если согласитесь, у прежнего владельца отключится автопродление, а оплаченный срок Плюса останется семье до конца.</>}
            {transfer.can_answer && transfer.kind === 'request' && <>{transfer.from_name} хочет стать владельцем семьи и оплачивать Плюс. Если согласитесь, вы станете участником, у вас отключится автопродление, а оплаченный срок Плюса останется семье до конца.</>}
            {transfer.can_withdraw && transfer.kind === 'offer' && <>Вы предложили {transfer.to_name} стать владельцем семьи. Пока ответа нет, владелец вы.</>}
            {transfer.can_withdraw && transfer.kind === 'request' && <>Вы попросили владельца ({transfer.to_name}) передать вам владение семьёй. Пока ответа нет.</>}
            {!transfer.can_answer && !transfer.can_withdraw && (transfer.kind === 'offer'
              ? <>{transfer.from_name} предлагает {transfer.to_name} стать владельцем семьи.</>
              : <>{transfer.from_name} просит владельца ({transfer.to_name}) передать ему владение семьёй.</>)}
            {' '}Ответить можно до {fmtDateTime(transfer.expires_at)}.
          </div>
          <div className="row wrap" style={{ gap: 8 }}>
            {transfer.can_answer && (
              <>
                <button className="btn primary" onClick={() => answer.mutate(true)} disabled={answer.isPending}><Check size={16} />{transfer.kind === 'offer' ? 'Принять' : 'Подтвердить'}</button>
                <button className="btn ghost" onClick={() => answer.mutate(false)} disabled={answer.isPending}><X size={16} />{transfer.kind === 'offer' ? 'Отказаться' : 'Отклонить'}</button>
              </>
            )}
            {transfer.can_withdraw && <button className="btn ghost" onClick={() => withdraw.mutate()} disabled={withdraw.isPending}>{transfer.kind === 'offer' ? 'Отменить предложение' : 'Забрать просьбу'}</button>}
          </div>
        </section>
      )}

      <Link to="/plus" className="card list-row plus-link" style={{ textDecoration: 'none', color: 'inherit' }}>
        <Sparkles size={22} style={{ color: 'var(--plus)', flex: 'none' }} />
        <div className="grow">
          <div style={{ fontWeight: 700 }}>Капсулка Плюс</div>
          <div className="small muted">{planLabel(plan) || 'Тариф семьи'}</div>
        </div>
        <ChevronRight size={18} className="muted" />
      </Link>

      <CompressSection family={f} />

      <section className="card flush">
        <div className="row between" style={{ padding: '18px 18px 6px' }}><h2>Участники</h2><LimitCounter name="members" /></div>
        {f.members.map(m => (
          <div key={m.user_id} className="list-row">
            <div className="avatar" style={{ background: avatarColor(m.user_id) }}>{m.name.slice(0, 1).toUpperCase()}</div>
            <div className="grow">
              <div style={{ fontWeight: 700 }}>{m.name}{m.user_id === me?.id && <span className="muted"> (вы)</span>}</div>
              <div className="small muted ellipsis">{m.email}</div>
            </div>
            {m.role === 'owner' && <span className="badge accent"><Crown size={12} />Владелец</span>}
            {owner && m.user_id !== me?.id && (
              <>
                <button className="icon-btn" title={cooldownUntil ? `Владение менялось недавно: передать можно с ${fmtDateTime(cooldownUntil)}` : transfer ? 'Уже есть неотвеченное предложение' : 'Предложить владение'}
                  disabled={!!transfer || !!cooldownUntil}
                  onClick={() => confirm(`Предложить ${m.name} стать владельцем семьи? Станет, только если ${m.name} согласится в течение 24 часов. Тогда вы станете участником, а автопродление Плюса у вас отключится.`) && offer.mutate(m.user_id)}><Crown size={16} /></button>
                <button className="icon-btn" title="Убрать из семьи" onClick={() => confirm(`Убрать ${m.name} из семьи?`) && removeMember.mutate(m.user_id)}><Trash2 size={16} /></button>
              </>
            )}
          </div>
        ))}
        {!owner && !transfer && (
          <div style={{ padding: '10px 18px 16px' }}>
            <button className="btn ghost" disabled={!!cooldownUntil} title={cooldownUntil ? `Владение менялось недавно: можно с ${fmtDateTime(cooldownUntil)}` : undefined}
              onClick={() => confirm('Попросить владельца передать вам владение семьёй? Станете владельцем, только если он согласится в течение 24 часов. Вы будете оплачивать Плюс, а у него автопродление отключится.') && askToPay.mutate()}><Crown size={16} />Хочу оплачивать</button>
          </div>
        )}
      </section>

      <section className="card stack">
        <h2>Пригласить в семью</h2>
        {owner ? (
          <>
            <p className="muted small">Отправьте ссылку человеку сами: она сработает один раз и действует 24 часа. Он создаст аккаунт или войдёт в свой, сам примет документы и вступит в семью. Почту человека указывать не нужно. Прежние многоразовые ссылки больше не работают: отправьте новую.</p>
            {f.invite_code ? (
              <>
                <div className="invite-box">
                  <div>
                    <div className="small muted">Ссылка-приглашение{f.invite_expires_at && ` · действует до ${fmtDateTime(f.invite_expires_at)}`}</div>
                    <div className="invite-link">{link}</div>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <button className="icon-btn" title="Скопировать ссылку" onClick={copyLink}><Copy size={18} /></button>
                    <button className="icon-btn" title="Создать новую ссылку" onClick={() => confirm('Старая ссылка перестанет работать. Продолжить?') && regen.mutate()}><RefreshCw size={18} /></button>
                  </div>
                </div>
                <button className="btn primary block" onClick={copyLink}><Share2 size={18} />Поделиться ссылкой</button>
              </>
            ) : (
              <button className="btn primary block" onClick={() => regen.mutate()} disabled={regen.isPending}><Share2 size={18} />Создать приглашение</button>
            )}
            {membersFull && (
              <div className="alert warn">
                <span>В семье уже предел бесплатной версии: по ссылке больше никто не вступит. В <Link to="/plus">Капсулке Плюс</Link> в семье до 5 человек.</span>
              </div>
            )}
          </>
        ) : (
          <p className="muted small">Приглашает владелец семьи{f.members.find(m => m.role === 'owner')?.name ? ` (${f.members.find(m => m.role === 'owner')!.name})` : ''}. Если нужно позвать ещё кого-то, попросите его прислать ссылку.</p>
        )}
      </section>

      <Cabinets />

      <Reminders />

      <section className="card stack">
        <h2>Аккаунт</h2>
        <div className="row wrap">
          {me?.is_admin && <Link to="/admin" className="btn"><Shield size={16} />Панель администратора</Link>}
          {!owner && <button className="btn ghost" onClick={() => confirm(`Выйти из «${f.name}»? У вас будет своя семья и одна из созданных вами аптечек.`) && removeMember.mutate(me!.id)}>Покинуть семью</button>}
          <button className="btn danger" onClick={signOut}><LogOut size={16} />Выйти из аккаунта</button>
          <DeleteAccountButton />
        </div>
        <LegalLinks />
        <p className="app-version">{versionLabel()}</p>
      </section>

      {rename !== null && (
        <Sheet title="Название семьи" onClose={() => setRename(null)}>
          <form className="stack" onSubmit={e => { e.preventDefault(); doRename.mutate(rename) }}>
            <input className="input" autoFocus required value={rename} onChange={e => setRename(e.target.value)} />
            <button className="btn primary block">Сохранить</button>
          </form>
        </Sheet>
      )}
    </div>
  )
}
