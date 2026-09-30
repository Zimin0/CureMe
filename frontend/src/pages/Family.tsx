import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Copy, Crown, LogOut, Pencil, Plus, RefreshCw, Settings, Share2, Shield, Sparkles, Trash2, UserPlus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, Category, Family as FamilyT } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { DeleteAccountButton } from '../components/DeleteAccount'
import { Reminders } from '../components/Reminders'
import { PageLoader, Sheet, useToast } from '../components/ui'
import { avatarColor } from '../format'
import { useLimitReached } from '../limits'
import { LimitCounter, planLabel, usePlan } from '../plan'
import { versionLabel } from '../version'
import { LegalLinks } from './Legal'

export function Family() {
  const { me, familyId, setFamilyId, refresh, signOut } = useAuth()
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const key = ['family', familyId]
  const { data: f, isLoading } = useQuery({ queryKey: key, queryFn: () => api<FamilyT>(fam('')) })
  const cats = useQuery({ queryKey: ['categories', fam('')], queryFn: () => api<Category[]>(fam('/categories')) })
  const { plan } = usePlan()

  const [email, setEmail] = useState('')
  const [rename, setRename] = useState<string | null>(null)
  const [newFamily, setNewFamily] = useState<string | null>(null)

  const onFam = (d: FamilyT, msg?: string) => { qc.setQueryData(key, d); if (msg) toast(msg) }
  // На 402 (лимит бесплатной версии) шторка Плюса открывается сама, тост не нужен.
  const onError = (e: Error) => { if (!(e instanceof ApiError && e.status === 402)) toast(e.message, 'error') }
  const membersFull = useLimitReached('members')

  const addMember = useMutation({
    mutationFn: () => api<FamilyT>(fam('/members'), { body: { email } }),
    onSuccess: d => { onFam(d, 'Участник добавлен'); setEmail(''); qc.invalidateQueries({ queryKey: ['plan'] }) }, onError,
  })
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
  const regen = useMutation({ mutationFn: () => api<FamilyT>(fam('/invite'), { method: 'POST' }), onSuccess: d => onFam(d, 'Новый код создан, старый больше не работает'), onError })
  const doRename = useMutation({
    mutationFn: (name: string) => api<FamilyT>(fam(''), { method: 'PATCH', body: { name } }),
    onSuccess: d => { onFam(d, 'Название изменено'); setRename(null); refresh() }, onError,
  })
  const createFamily = useMutation({
    mutationFn: (name: string) => api<FamilyT>('/families', { body: { name } }),
    onSuccess: async d => { await refresh(); setFamilyId(d.id); setNewFamily(null); toast(`Создана «${d.name}»`) }, onError,
  })
  if (isLoading || !f) return <PageLoader />
  const owner = f.role === 'owner'
  const link = `${location.origin}/join/${f.invite_code}`

  const share = async () => {
    const text = `Присоединяйся к нашей домашней аптечке «${f.name}» в Капсулке`
    if (navigator.share) {
      try { await navigator.share({ title: 'Капсулка', text, url: link }) } catch { /* отменили */ }
    } else {
      await navigator.clipboard.writeText(link)
      toast('Ссылка скопирована')
    }
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

      <section className="card stack">
        <h2>Пригласить в семью</h2>
        <p className="muted small">Отправьте ссылку. По ней можно создать аккаунт или войти в существующий, и аптечка сразу станет общей.</p>
        <div className="invite-box">
          <div>
            <div className="small muted">Код приглашения</div>
            <div className="invite-code">{f.invite_code}</div>
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="icon-btn" title="Скопировать ссылку" onClick={() => navigator.clipboard.writeText(link).then(() => toast('Ссылка скопирована'))}><Copy size={18} /></button>
            {owner && <button className="icon-btn" title="Сменить код" onClick={() => confirm('Старая ссылка перестанет работать. Продолжить?') && regen.mutate()}><RefreshCw size={18} /></button>}
          </div>
        </div>
        <button className="btn primary block" onClick={share}><Share2 size={18} />Поделиться ссылкой</button>
        {membersFull && (
          <div className="alert warn">
            <span>В семье уже предел бесплатной версии: по ссылке больше никто не вступит. В <Link to="/plus">Капсулке Плюс</Link> участников сколько угодно.</span>
          </div>
        )}
        {owner && (
          <form className="row" onSubmit={e => { e.preventDefault(); addMember.mutate() }}>
            <input className="input grow" type="email" required placeholder="Или добавить по почте, если аккаунт уже есть" value={email} onChange={e => setEmail(e.target.value)} />
            <button className="btn" disabled={addMember.isPending}><UserPlus size={18} /></button>
          </form>
        )}
      </section>

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
                <button className="icon-btn" title={m.role === 'owner' ? 'Сделать участником' : 'Сделать владельцем'}
                  onClick={() => setRole.mutate({ uid: m.user_id, role: m.role === 'owner' ? 'member' : 'owner' })}><Crown size={16} /></button>
                <button className="icon-btn" title="Убрать из семьи" onClick={() => confirm(`Убрать ${m.name} из семьи?`) && removeMember.mutate(m.user_id)}><Trash2 size={16} /></button>
              </>
            )}
          </div>
        ))}
      </section>

      <section className="card">
        <div className="card-head">
          <h2>Категории</h2>
          {me?.is_admin && <Link to="/admin?tab=categories" className="btn sm"><Settings size={16} />Настроить</Link>}
        </div>
        <p className="muted small" style={{ marginBottom: 10 }}>Список категорий общий для всех семей, его ведёт администратор. Цифра показывает, сколько лекарств в вашей аптечке.</p>
        <div className="chips wrap">
          {cats.data?.map(c => (
            <Link key={c.id} to={`/medicines?category=${c.id}`} className="chip" style={{ borderColor: `color-mix(in srgb, ${c.color} 40%, transparent)` }}>
              {c.icon} {c.name} <span className="count">{c.medicine_count}</span>
            </Link>
          ))}
        </div>
      </section>

      <Reminders />

      <section className="card stack">
        <h2>Аккаунт</h2>
        {me && me.families.length > 1 && (
          <label className="field"><span>Аптечка какой семьи открыта</span>
            <select value={familyId ?? ''} onChange={e => setFamilyId(Number(e.target.value))}>
              {me.families.map(x => <option key={x.id} value={x.id}>{x.name}</option>)}
            </select>
          </label>
        )}
        <div className="row wrap">
          {me?.is_admin && <Link to="/admin" className="btn"><Shield size={16} />Панель администратора</Link>}
          <button className="btn ghost" onClick={() => setNewFamily('')}><Plus size={16} />Создать ещё одну семью</button>
          <button className="btn ghost" onClick={() => confirm(`Выйти из «${f.name}»?`) && removeMember.mutate(me!.id)}>Покинуть семью</button>
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
      {newFamily !== null && (
        <Sheet title="Новая семья" onClose={() => setNewFamily(null)}>
          <form className="stack" onSubmit={e => { e.preventDefault(); createFamily.mutate(newFamily) }}>
            <p className="muted small">Например, отдельная аптечка на даче или у родителей.</p>
            <input className="input" autoFocus required placeholder="Дача" value={newFamily} onChange={e => setNewFamily(e.target.value)} />
            <button className="btn primary block">Создать</button>
          </form>
        </Sheet>
      )}
    </div>
  )
}
