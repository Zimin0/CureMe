import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Copy, Crown, LogOut, Pencil, RefreshCw, Share2, Shield, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, Family as FamilyT } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { Cabinets } from '../components/Cabinets'
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

  const setRole = useMutation({
    mutationFn: ({ uid, role }: { uid: number; role: string }) => api<FamilyT>(fam(`/members/${uid}`), { method: 'PATCH', body: { role } }),
    onSuccess: d => onFam(d, 'Роль изменена'), onError,
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

      <Link to="/plus" className="card list-row plus-link" style={{ textDecoration: 'none', color: 'inherit' }}>
        <Sparkles size={22} style={{ color: 'var(--plus)', flex: 'none' }} />
        <div className="grow">
          <div style={{ fontWeight: 700 }}>Капсулка Плюс</div>
          <div className="small muted">{planLabel(plan) || 'Тариф семьи'}</div>
        </div>
        <ChevronRight size={18} className="muted" />
      </Link>

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
                <button className="icon-btn" title="Передать владение"
                  onClick={() => confirm(`Передать владение: ${m.name}? Вы станете участником, автопродление Плюса отключится.`) && setRole.mutate({ uid: m.user_id, role: 'owner' })}><Crown size={16} /></button>
                <button className="icon-btn" title="Убрать из семьи" onClick={() => confirm(`Убрать ${m.name} из семьи?`) && removeMember.mutate(m.user_id)}><Trash2 size={16} /></button>
              </>
            )}
          </div>
        ))}
      </section>

      <section className="card stack">
        <h2>Пригласить в семью</h2>
        {owner ? (
          <>
            <p className="muted small">Отправьте ссылку человеку сами: она сработает один раз и действует 24 часа. Он создаст аккаунт или войдёт в свой, сам примет документы и вступит в семью. Почту человека указывать не нужно.</p>
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
