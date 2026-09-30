import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Crown, House, Lightbulb, Pill, Plus, Search, Shield, Sparkles, Tags, Trash2, UserPlus, Users, X } from 'lucide-react'
import { FormEvent, useEffect, useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { AdminFamily, AdminStats, AdminUser, api, Category, PlanName } from '../api'
import { useAuth } from '../auth'
import { CategoryDraft, CategoryEditor } from '../components/CategoryEditor'
import { Empty, PageLoader, Sheet, useToast } from '../components/ui'
import { avatarColor, fmtDate, plural } from '../format'

const TABS = [
  { id: 'users', label: 'Люди' },
  { id: 'families', label: 'Семьи' },
  { id: 'categories', label: 'Категории' },
  { id: 'hints', label: 'Подсказки' },
  { id: 'access', label: 'Доступ' },
  { id: 'debug', label: 'Отладка' },
  { id: 'plans', label: 'Тарифы' },
] as const
type Tab = typeof TABS[number]['id']

/** Сбрасываем всё, что могло измениться: и данные админки, и то, что показывают обычные страницы. */
function useRefresh() {
  const qc = useQueryClient()
  const { refresh } = useAuth()
  return () => {
    ['admin', 'categories', 'medicines', 'family', 'overview', 'plan'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
    refresh()
  }
}

export function Admin() {
  const { me } = useAuth()
  const [params, setParams] = useSearchParams()
  const tab = (TABS.some(t => t.id === params.get('tab')) ? params.get('tab') : 'users') as Tab
  const stats = useQuery({ queryKey: ['admin', 'stats'], queryFn: () => api<AdminStats>('/admin/stats'), enabled: !!me?.is_admin })

  if (!me?.is_admin) return <Navigate to="/" replace />
  const s = stats.data
  return (
    <div className="page" style={{ maxWidth: 880 }}>
      <div className="page-head">
        <div>
          <h1 className="row" style={{ gap: 10 }}><Shield size={26} />Администрирование</h1>
          <p className="sub">Все аккаунты и семьи Капсулки, общий для всех список категорий и подсказок.</p>
        </div>
      </div>

      <div className="stats">
        <div className="stat"><span className="label"><Users size={15} />Людей</span><span className="value">{s?.users ?? '…'}</span></div>
        <div className="stat"><span className="label"><House size={15} />Семей</span><span className="value">{s?.families ?? '…'}</span></div>
        <div className="stat"><span className="label"><Pill size={15} />Лекарств</span><span className="value">{s?.medicines ?? '…'}</span></div>
        <div className="stat"><span className="label"><Tags size={15} />Категорий</span><span className="value">{s?.categories ?? '…'}</span></div>
      </div>

      <div className="segmented wrap" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''}
            onClick={() => setParams({ tab: t.id }, { replace: true })}>{t.label}</button>
        ))}
      </div>

      {tab === 'users' && <UsersTab meId={me.id} />}
      {tab === 'families' && <FamiliesTab />}
      {tab === 'categories' && <CategoriesTab />}
      {tab === 'hints' && <HintsTab />}
      {tab === 'access' && <AccessTab />}
      {tab === 'debug' && <DebugTab />}
      {tab === 'plans' && <PlansTab />}
    </div>
  )
}

// ---------- люди ----------
function UsersTab({ meId }: { meId: number }) {
  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: () => api<AdminUser[]>('/admin/users') })
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState<AdminUser | null>(null)
  if (users.isLoading) return <PageLoader />
  const needle = q.trim().toLowerCase()
  const list = (users.data ?? []).filter(u => !needle || `${u.name} ${u.email}`.toLowerCase().includes(needle))

  return (
    <>
      <div className="search"><Search size={18} /><input className="input" placeholder="Имя или почта" value={q} onChange={e => setQ(e.target.value)} /></div>
      <section className="card flush">
        {list.length === 0 && <div style={{ padding: 18 }} className="muted">Никого не нашли</div>}
        {list.map(u => (
          <button key={u.id} className="list-row admin-row" onClick={() => setEdit(u)}>
            <div className="avatar" style={{ background: avatarColor(u.id) }}>{u.name.slice(0, 1).toUpperCase()}</div>
            <div className="grow">
              <div style={{ fontWeight: 700 }} className="ellipsis">{u.name}{u.id === meId && <span className="muted"> (вы)</span>}</div>
              <div className="small muted ellipsis">{u.email}</div>
              <div className="small faint ellipsis">{u.families.length ? u.families.map(f => f.name).join(', ') : 'Ни в одной семье'}</div>
            </div>
            {!u.email_verified && <span className="badge low" title="Человек ещё не перешёл по ссылке из письма">Почта не подтверждена</span>}
            {u.is_admin && <span className="badge accent"><Shield size={12} />Админ</span>}
          </button>
        ))}
      </section>
      {edit && <UserSheet user={edit} isMe={edit.id === meId} onClose={() => setEdit(null)} />}
    </>
  )
}

function UserSheet({ user, isMe, onClose }: { user: AdminUser; isMe: boolean; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [name, setName] = useState(user.name)
  const [email, setEmail] = useState(user.email)
  const [password, setPassword] = useState('')
  const [isAdmin, setIsAdmin] = useState(user.is_admin)
  const [verified, setVerified] = useState(user.email_verified)
  const onError = (e: Error) => toast(e.message, 'error')

  const save = useMutation({
    mutationFn: () => api<AdminUser>(`/admin/users/${user.id}`, {
      method: 'PATCH', body: { name, email, is_admin: isAdmin, email_verified: verified, password: password || null },
    }),
    onSuccess: () => { refresh(); toast(password ? 'Сохранено, пароль изменён' : 'Сохранено'); onClose() }, onError,
  })
  const remove = useMutation({
    mutationFn: () => api(`/admin/users/${user.id}`, { method: 'DELETE' }),
    onSuccess: () => { refresh(); toast(`Аккаунт ${user.name} удалён`); onClose() }, onError,
  })

  return (
    <Sheet title={user.name} onClose={onClose}>
      <form className="stack" onSubmit={e => { e.preventDefault(); save.mutate() }}>
        <p className="muted small">Зарегистрирован {fmtDate(user.created_at)}</p>
        <label className="field"><span>Имя</span><input className="input" required value={name} onChange={e => setName(e.target.value)} /></label>
        <label className="field"><span>Почта</span><input className="input" type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
        <label className="field"><span>Новый пароль</span>
          <input className="input" type="text" minLength={8} autoComplete="off" placeholder="Оставьте пустым, чтобы не менять" value={password} onChange={e => setPassword(e.target.value)} />
          <span className="hint">Если человек забыл пароль: задайте новый и передайте ему</span>
        </label>
        <label className="row" style={{ gap: 10, cursor: 'pointer' }}>
          <input type="checkbox" checked={verified} disabled={isMe && user.email_verified} onChange={e => setVerified(e.target.checked)} />
          <span>Почта подтверждена{!user.email_verified && <span className="muted small"> (отметьте, если письмо не доходит)</span>}</span>
        </label>
        <label className="row" style={{ gap: 10, cursor: isMe ? 'default' : 'pointer' }}>
          <input type="checkbox" checked={isAdmin} disabled={isMe} onChange={e => setIsAdmin(e.target.checked)} />
          <span>Администратор{isMe && <span className="muted small"> (себе права снять нельзя)</span>}</span>
        </label>
        {user.families.length > 0 && (
          <div className="stack" style={{ gap: 6 }}>
            <span className="small muted">Семьи</span>
            <div className="chips wrap">
              {user.families.map(f => <span key={f.id} className="badge">{f.role === 'owner' && <Crown size={12} />}{f.name}</span>)}
            </div>
          </div>
        )}
        <button className="btn primary block" disabled={save.isPending}>Сохранить</button>
        {!isMe && (
          <button type="button" className="btn danger block" disabled={remove.isPending}
            onClick={() => confirm(`Удалить аккаунт ${user.name}? Семьи, где он был один, удалятся вместе с аптечкой.`) && remove.mutate()}>
            <Trash2 size={16} />Удалить аккаунт
          </button>
        )}
      </form>
    </Sheet>
  )
}

// ---------- семьи ----------
function FamiliesTab() {
  const fams = useQuery({ queryKey: ['admin', 'families'], queryFn: () => api<AdminFamily[]>('/admin/families') })
  const [openId, setOpenId] = useState<number | null>(null)
  if (fams.isLoading) return <PageLoader />
  const open = fams.data?.find(f => f.id === openId)
  if (!fams.data?.length) return <Empty icon={<House size={28} />} title="Семей пока нет" />

  return (
    <>
      <section className="card flush">
        {fams.data.map(f => (
          <button key={f.id} className="list-row admin-row" onClick={() => setOpenId(f.id)}>
            <div className="avatar" style={{ background: avatarColor(f.id + 7) }}><House size={18} /></div>
            <div className="grow">
              <div style={{ fontWeight: 700 }} className="ellipsis">{f.name}</div>
              <div className="small muted ellipsis">{f.members.map(m => m.name).join(', ') || 'Нет участников'}</div>
            </div>
            <div className="small muted" style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
              {f.members.length} {plural(f.members.length, 'человек', 'человека', 'человек')}<br />
              {f.medicine_count} {plural(f.medicine_count, 'лекарство', 'лекарства', 'лекарств')}
            </div>
          </button>
        ))}
      </section>
      {open && <FamilySheet family={open} onClose={() => setOpenId(null)} />}
    </>
  )
}

function FamilySheet({ family: f, onClose }: { family: AdminFamily; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [name, setName] = useState(f.name)
  const [email, setEmail] = useState('')
  const onError = (e: Error) => toast(e.message, 'error')
  const path = `/admin/families/${f.id}`

  const rename = useMutation({
    mutationFn: () => api(path, { method: 'PATCH', body: { name } }),
    onSuccess: () => { refresh(); toast('Название изменено') }, onError,
  })
  const add = useMutation({
    mutationFn: () => api(`${path}/members`, { body: { email } }),
    onSuccess: () => { refresh(); setEmail(''); toast('Участник добавлен') }, onError,
  })
  const setRole = useMutation({
    mutationFn: ({ uid, role }: { uid: number; role: string }) => api(`${path}/members/${uid}`, { method: 'PATCH', body: { role } }),
    onSuccess: refresh, onError,
  })
  const removeMember = useMutation({
    mutationFn: (uid: number) => api(`${path}/members/${uid}`, { method: 'DELETE' }),
    onSuccess: () => { refresh(); if (f.members.length === 1) onClose(); toast('Участник убран') }, onError,
  })
  const remove = useMutation({
    mutationFn: () => api(path, { method: 'DELETE' }),
    onSuccess: () => { refresh(); toast(`Семья «${f.name}» удалена`); onClose() }, onError,
  })

  return (
    <Sheet title={f.name} onClose={onClose}>
      <div className="stack">
        <p className="muted small">Создана {fmtDate(f.created_at)} · код приглашения {f.invite_code} · {f.medicine_count} {plural(f.medicine_count, 'лекарство', 'лекарства', 'лекарств')}</p>
        <form className="row" onSubmit={e => { e.preventDefault(); rename.mutate() }}>
          <input className="input grow" required value={name} onChange={e => setName(e.target.value)} aria-label="Название семьи" />
          <button className="btn" disabled={name.trim() === f.name || rename.isPending}>Переименовать</button>
        </form>

        <div className="card flush" style={{ boxShadow: 'none' }}>
          {f.members.map(m => (
            <div key={m.user_id} className="list-row">
              <div className="avatar" style={{ background: avatarColor(m.user_id) }}>{m.name.slice(0, 1).toUpperCase()}</div>
              <div className="grow">
                <div style={{ fontWeight: 700 }} className="ellipsis">{m.name}</div>
                <div className="small muted ellipsis">{m.email}</div>
              </div>
              <button className="icon-btn" title={m.role === 'owner' ? 'Владелец. Сделать участником' : 'Сделать владельцем'}
                onClick={() => setRole.mutate({ uid: m.user_id, role: m.role === 'owner' ? 'member' : 'owner' })}>
                <Crown size={16} color={m.role === 'owner' ? 'var(--warning)' : undefined} />
              </button>
              <button className="icon-btn" title="Убрать из семьи" onClick={() => confirm(`Убрать ${m.name} из «${f.name}»?`) && removeMember.mutate(m.user_id)}><Trash2 size={16} /></button>
            </div>
          ))}
        </div>

        <form className="row" onSubmit={e => { e.preventDefault(); add.mutate() }}>
          <input className="input grow" type="email" required placeholder="Добавить по почте" value={email} onChange={e => setEmail(e.target.value)} />
          <button className="btn" disabled={add.isPending} title="Добавить"><UserPlus size={18} /></button>
        </form>

        <button type="button" className="btn danger block" disabled={remove.isPending}
          onClick={() => confirm(`Удалить семью «${f.name}» вместе со всей аптечкой? Это нельзя отменить.`) && remove.mutate()}>
          <Trash2 size={16} />Удалить семью
        </button>
      </div>
    </Sheet>
  )
}

// ---------- категории ----------
function CategoriesTab() {
  const toast = useToast()
  const refresh = useRefresh()
  const qc = useQueryClient()
  const key = ['admin', 'categories']
  const cats = useQuery({ queryKey: key, queryFn: () => api<Category[]>('/admin/categories') })
  const [edit, setEdit] = useState<CategoryDraft | null>(null)
  const onError = (e: Error) => toast(e.message, 'error')

  const save = useMutation({
    mutationFn: (c: CategoryDraft) => {
      const body = { name: c.name, icon: c.icon, color: c.color }
      return c.id ? api(`/admin/categories/${c.id}`, { method: 'PUT', body }) : api('/admin/categories', { body })
    },
    onSuccess: () => { refresh(); setEdit(null); toast('Категория сохранена') }, onError,
  })
  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/categories/${id}`, { method: 'DELETE' }),
    onSuccess: () => { refresh(); setEdit(null); toast('Категория удалена') }, onError,
  })
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api<Category[]>('/admin/categories/order', { method: 'PUT', body: { ids } }),
    onMutate: ids => {
      // Двигаем сразу, не дожидаясь сервера: так стрелки не «дёргаются».
      const prev = qc.getQueryData<Category[]>(key)
      if (prev) qc.setQueryData(key, ids.map(id => prev.find(c => c.id === id)!))
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['categories'] }) }, onError,
  })
  const move = (i: number, d: -1 | 1) => {
    const ids = cats.data!.map(c => c.id)
    ;[ids[i], ids[i + d]] = [ids[i + d], ids[i]]
    reorder.mutate(ids)
  }

  if (cats.isLoading) return <PageLoader />
  const list = cats.data ?? []
  return (
    <>
      <div className="row between">
        <p className="muted small grow">Категории видят все семьи. Цифра показывает, сколько лекарств с этой категорией во всех аптечках.</p>
        <button className="btn primary sm" onClick={() => setEdit({})}><Plus size={16} />Новая</button>
      </div>
      <section className="card flush">
        {list.map((c, i) => (
          <div key={c.id} className="list-row">
            <button className="grow row admin-row" style={{ gap: 12, padding: 0 }} onClick={() => setEdit(c)}>
              <span className="cat-icon" style={{ background: `color-mix(in srgb, ${c.color} 18%, transparent)` }}>{c.icon}</span>
              <span className="grow ellipsis" style={{ fontWeight: 700 }}>{c.name}</span>
              <span className="small muted">{c.medicine_count}</span>
            </button>
            <button className="icon-btn" title="Выше" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={16} /></button>
            <button className="icon-btn" title="Ниже" disabled={i === list.length - 1} onClick={() => move(i, 1)}><ArrowDown size={16} /></button>
          </div>
        ))}
      </section>
      {edit && (
        <CategoryEditor initial={edit} busy={save.isPending || remove.isPending}
          onSave={c => save.mutate(c)} onDelete={id => remove.mutate(id)} onClose={() => setEdit(null)} />
      )}
    </>
  )
}

// ---------- подсказки «От чего помогает» ----------
function HintsTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const hints = useQuery({ queryKey: ['admin', 'indication-hints'], queryFn: () => api<string[]>('/admin/indication-hints') })
  const [list, setList] = useState<string[] | null>(null)
  const [draft, setDraft] = useState('')
  useEffect(() => { if (hints.data && list === null) setList(hints.data) }, [hints.data, list])

  const save = useMutation({
    mutationFn: (h: string[]) => api<string[]>('/admin/indication-hints', { method: 'PUT', body: { hints: h } }),
    onSuccess: h => {
      setList(h)
      qc.setQueryData(['admin', 'indication-hints'], h)
      qc.setQueryData(['indication-hints'], h)
      toast('Подсказки сохранены')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  if (hints.isLoading || list === null) return <PageLoader />
  const dirty = JSON.stringify(list) !== JSON.stringify(hints.data)
  const add = (e: FormEvent) => {
    e.preventDefault()
    const t = draft.trim().replace(/\s+/g, ' ')
    if (!t) return
    if (list.some(h => h.toLowerCase() === t.toLowerCase())) { toast('Такая подсказка уже есть', 'error'); return }
    setList([...list, t])
    setDraft('')
  }
  const move = (i: number, d: -1 | 1) => {
    const next = [...list]
    ;[next[i], next[i + d]] = [next[i + d], next[i]]
    setList(next)
  }
  return (
    <>
      <p className="muted small">Быстрые кнопки под полем «От чего помогает» при добавлении лекарства и сканировании. Список общий для всех семей.</p>
      <form className="row" onSubmit={add}>
        <input className="input grow" placeholder="Например, зубная боль" maxLength={60} value={draft} onChange={e => setDraft(e.target.value)} />
        <button className="btn" disabled={!draft.trim()}><Plus size={16} />Добавить</button>
      </form>
      <section className="card flush">
        {list.length === 0 && <Empty icon={<Lightbulb size={30} />} title="Подсказок нет" text="Добавьте первую: она появится кнопкой в форме лекарства." />}
        {list.map((h, i) => (
          <div key={h} className="list-row">
            <span className="grow ellipsis" style={{ fontWeight: 600 }}>{h}</span>
            <button className="icon-btn" title="Выше" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp size={16} /></button>
            <button className="icon-btn" title="Ниже" disabled={i === list.length - 1} onClick={() => move(i, 1)}><ArrowDown size={16} /></button>
            <button className="icon-btn" title={`Убрать «${h}»`} onClick={() => setList(list.filter(x => x !== h))}><X size={16} /></button>
          </div>
        ))}
      </section>
      <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
        {dirty && <button className="btn ghost" onClick={() => setList(hints.data!)}>Отменить</button>}
        <button className="btn primary" disabled={!dirty || save.isPending} onClick={() => save.mutate(list)}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </button>
      </div>
    </>
  )
}

// ---------- закрытый режим ----------
type Access = { closed: boolean; user_ids: number[] }

/** Сайт «в разработке»: пользоваться могут только администраторы и отмеченные здесь аккаунты. */
function AccessTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const access = useQuery({ queryKey: ['admin', 'access'], queryFn: () => api<Access>('/admin/access') })
  const users = useQuery({ queryKey: ['admin', 'users'], queryFn: () => api<AdminUser[]>('/admin/users') })
  const [draft, setDraft] = useState<Access | null>(null)
  useEffect(() => { if (access.data && draft === null) setDraft(access.data) }, [access.data, draft])

  const save = useMutation({
    mutationFn: (a: Access) => api<Access>('/admin/access', { method: 'PUT', body: a }),
    onSuccess: a => {
      setDraft(a)
      qc.setQueryData(['admin', 'access'], a)
      qc.setQueryData(['access'], (old: object | undefined) => ({ ...old, closed: a.closed }))
      toast(a.closed ? 'Сайт закрыт для остальных' : 'Сайт открыт для всех')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  if (access.isLoading || users.isLoading || draft === null) return <PageLoader />
  const dirty = JSON.stringify(draft) !== JSON.stringify(access.data)
  const toggle = (id: number, on: boolean) =>
    setDraft({ ...draft, user_ids: on ? [...draft.user_ids, id] : draft.user_ids.filter(x => x !== id) })

  return (
    <>
      <label className="check card" style={{ padding: 16 }}>
        <input type="checkbox" checked={draft.closed} onChange={e => setDraft({ ...draft, closed: e.target.checked })} />
        <span>
          <b>Сайт в разработке</b><br />
          <span className="muted small">Регистрация закрывается, остальные видят страницу «Сайт в разработке» с вашей почтой. Войти, удалить аккаунт и прочитать документы они по-прежнему могут.</span>
        </span>
      </label>
      <p className="muted small">Кому открыт сайт в этом режиме. Администраторы проходят всегда.</p>
      <section className="card flush">
        {(users.data ?? []).map(u => (
          <label key={u.id} className="list-row check" style={{ padding: '12px 16px' }}>
            <input type="checkbox" disabled={u.is_admin} checked={u.is_admin || draft.user_ids.includes(u.id)}
              onChange={e => toggle(u.id, e.target.checked)} aria-label={`Доступ: ${u.name}`} />
            <span className="grow">
              <span style={{ fontWeight: 700 }}>{u.name}</span>{u.is_admin && <span className="muted"> (админ)</span>}<br />
              <span className="small muted">{u.email}</span>
            </span>
          </label>
        ))}
      </section>
      <div className="row" style={{ justifyContent: 'flex-end', gap: 8 }}>
        {dirty && <button className="btn ghost" onClick={() => setDraft(access.data!)}>Отменить</button>}
        <button className="btn primary" disabled={!dirty || save.isPending} onClick={() => save.mutate(draft)}>
          {save.isPending ? 'Сохраняем…' : 'Сохранить'}
        </button>
      </div>
    </>
  )
}

// ---------- режим отладки ----------
/** Режим отладки: на каждой странице сверху видна версия приложения (для всех, кто открыл сайт). */
function DebugTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const debug = useQuery({ queryKey: ['admin', 'debug'], queryFn: () => api<{ enabled: boolean }>('/admin/debug') })
  const save = useMutation({
    mutationFn: (enabled: boolean) => api<{ enabled: boolean }>('/admin/debug', { method: 'PUT', body: { enabled } }),
    onSuccess: d => {
      qc.setQueryData(['admin', 'debug'], d)
      qc.setQueryData(['access'], (old: object | undefined) => ({ ...old, debug: d.enabled }))
      toast(d.enabled ? 'Режим отладки включён' : 'Режим отладки выключен')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  if (debug.isLoading) return <PageLoader />
  return (
    <>
      <label className="check card" style={{ padding: 16 }}>
        <input type="checkbox" checked={debug.data?.enabled ?? false} disabled={save.isPending}
          onChange={e => save.mutate(e.target.checked)} />
        <span>
          <b>Режим отладки</b><br />
          <span className="muted small">Вверху каждой страницы показывается версия приложения и коммит сборки. Видно всем, кто открыл сайт, в том числе на страницах входа. Включайте, когда проверяете, что выкатилась нужная версия.</span>
        </span>
      </label>
      {debug.data?.enabled && (
        <div className="card" role="note" data-testid="debug-note" style={{ padding: 16, marginTop: 12 }}>
          <b>Что меняется в режиме отладки</b>
          <ul className="muted small" style={{ margin: '8px 0 0', paddingLeft: 18 }}>
            <li>Напоминания о просроченных и скоро истекающих лекарствах приходят сразу после добавления упаковки, без обычной паузы в 12 часов.</li>
            <li>Сообщение о сроке уходит сразу после добавления, а не в ежедневной сводке в 10:00.</li>
            <li>Вверху каждой страницы показывается версия приложения.</li>
          </ul>
        </div>
      )}
    </>
  )
}

// ---------- тарифы ----------
type Billing = { enabled: boolean; price_month: number | null; price_year: number | null }

const planText = (f: AdminFamily) =>
  f.plus_active ? (f.plus_until ? `Плюс до ${fmtDate(f.plus_until)}` : 'Плюс бессрочно')
    : f.plan === 'plus' ? 'Плюс истёк' : 'Бесплатный'

/** Платная версия: общий переключатель и ручное включение Плюса семьям (оплаты пока нет). */
function PlansTab() {
  const toast = useToast()
  const qc = useQueryClient()
  const billing = useQuery({ queryKey: ['admin', 'billing'], queryFn: () => api<Billing>('/admin/billing') })
  const fams = useQuery({ queryKey: ['admin', 'families'], queryFn: () => api<AdminFamily[]>('/admin/families') })
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState<AdminFamily | null>(null)
  const [prices, setPrices] = useState<{ month: string; year: string } | null>(null)
  useEffect(() => {
    if (billing.data && prices === null) {
      setPrices({ month: billing.data.price_month?.toString() ?? '', year: billing.data.price_year?.toString() ?? '' })
    }
  }, [billing.data, prices])

  const save = useMutation({
    mutationFn: (b: Billing) => api<Billing>('/admin/billing', { method: 'PUT', body: b }),
    onSuccess: (b, sent) => {
      const priceChanged = sent.price_month !== billing.data?.price_month || sent.price_year !== billing.data?.price_year
      qc.setQueryData(['admin', 'billing'], b)
      qc.invalidateQueries({ queryKey: ['plan'] })
      toast(priceChanged ? 'Стоимость сохранена'
        : b.enabled ? 'Платная версия включена' : 'Платная версия выключена: всем доступно всё')
    },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const toPrice = (s: string) => (s.trim() ? Math.round(Number(s)) : null)

  if (billing.isLoading || fams.isLoading || !billing.data) return <PageLoader />
  const needle = q.trim().toLowerCase()
  const list = (fams.data ?? []).filter(f => !needle || `${f.name} ${f.members.map(m => `${m.name} ${m.email}`).join(' ')}`.toLowerCase().includes(needle))
  const plusCount = (fams.data ?? []).filter(f => f.plus_active).length

  return (
    <>
      <label className="check card" style={{ padding: 16 }}>
        <input type="checkbox" checked={billing.data.enabled} disabled={save.isPending}
          onChange={e => {
            const on = e.target.checked
            if (!on || confirm('Включить платную версию? Семьи без Плюса получат лимиты бесплатной версии: 4 участника, 60 лекарств, 1 своя аптечка, история за 30 дней.')) save.mutate({ ...billing.data!, enabled: on })
          }} />
        <span>
          <b>Платная версия включена</b><br />
          <span className="muted small">Пока выключено, всем семьям доступны все функции Плюса. Включите, когда будут готовы оплата и оферта.</span>
        </span>
      </label>
      {prices && (
        <form className="card stack" style={{ padding: 16 }} onSubmit={(e: FormEvent) => {
          e.preventDefault()
          save.mutate({ ...billing.data!, price_month: toPrice(prices.month), price_year: toPrice(prices.year) })
        }}>
          <b>Стоимость Плюса для всей семьи</b>
          <div className="row wrap" style={{ gap: 12 }}>
            <label className="field grow"><span>В месяц, ₽</span>
              <input className="input" type="number" min={1} max={100000} inputMode="numeric" placeholder="149"
                value={prices.month} onChange={e => setPrices({ ...prices, month: e.target.value })} />
            </label>
            <label className="field grow"><span>В год, ₽</span>
              <input className="input" type="number" min={1} max={1000000} inputMode="numeric" placeholder="990"
                value={prices.year} onChange={e => setPrices({ ...prices, year: e.target.value })} />
            </label>
          </div>
          <span className="muted small">Показывается на странице «Капсулка Плюс» и в шторке. Пустое поле — эта цена не показывается. Пока нет оплаты, цена указана только для сведения.</span>
          <button className="btn primary" style={{ alignSelf: 'flex-end' }} disabled={save.isPending}>Сохранить стоимость</button>
        </form>
      )}
      <p className="muted small">Плюс у {plusCount} {plural(plusCount, 'семьи', 'семей', 'семей')}. Нажмите на семью, чтобы включить или продлить Плюс вручную.</p>
      <div className="search"><Search size={18} /><input className="input" placeholder="Семья, имя или почта" value={q} onChange={e => setQ(e.target.value)} /></div>
      <section className="card flush">
        {list.length === 0 && <div style={{ padding: 18 }} className="muted">Ничего не нашли</div>}
        {list.map(f => (
          <button key={f.id} className="list-row admin-row" onClick={() => setEdit(f)}>
            <div className="avatar" style={{ background: avatarColor(f.id + 7) }}><House size={18} /></div>
            <div className="grow">
              <div style={{ fontWeight: 700 }} className="ellipsis">{f.name}</div>
              <div className="small muted ellipsis">{f.members.map(m => m.name).join(', ') || 'Нет участников'}</div>
            </div>
            <span className={`badge ${f.plus_active ? 'plus' : ''}`}>{f.plus_active && <Sparkles size={12} />}{planText(f)}</span>
          </button>
        ))}
      </section>
      {edit && <PlanSheet family={edit} onClose={() => setEdit(null)} />}
    </>
  )
}

/** Дата «Плюс до» для поля ввода: yyyy-mm-dd по местному времени. */
function dateInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function PlanSheet({ family, onClose }: { family: AdminFamily; onClose: () => void }) {
  const toast = useToast()
  const refresh = useRefresh()
  const [plan, setPlan] = useState<PlanName>(family.plan)
  const [until, setUntil] = useState(dateInput(family.plus_until))

  const addMonths = (n: number) => {
    const base = until ? new Date(until) : new Date()
    base.setMonth(base.getMonth() + n)
    setPlan('plus')
    setUntil(dateInput(base.toISOString()))
  }
  const save = useMutation({
    // «Плюс до 12.10» — включительно: до конца этого дня по местному времени.
    mutationFn: () => api<AdminFamily>(`/admin/families/${family.id}/plan`, {
      method: 'PUT', body: { plan, plus_until: plan === 'plus' && until ? new Date(`${until}T23:59:59`).toISOString() : null },
    }),
    onSuccess: f => { refresh(); toast(`${f.name}: ${planText(f)}`); onClose() },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  return (
    <Sheet title={`Тариф: ${family.name}`} onClose={onClose}>
      <form className="stack" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate() }}>
        <div className="segmented" role="radiogroup" aria-label="Тариф">
          <button type="button" role="radio" aria-checked={plan === 'free'} className={plan === 'free' ? 'on' : ''} onClick={() => setPlan('free')}>Бесплатный</button>
          <button type="button" role="radio" aria-checked={plan === 'plus'} className={plan === 'plus' ? 'on' : ''} onClick={() => setPlan('plus')}>Плюс</button>
        </div>
        {plan === 'plus' && (
          <>
            <label className="field"><span>Плюс до (пусто — бессрочно)</span>
              <input className="input" type="date" value={until} onChange={e => setUntil(e.target.value)} />
            </label>
            <div className="row wrap" style={{ gap: 8 }}>
              <button type="button" className="btn sm" onClick={() => addMonths(1)}>+1 месяц</button>
              <button type="button" className="btn sm" onClick={() => addMonths(12)}>+1 год</button>
              <button type="button" className="btn sm ghost" onClick={() => setUntil('')}>Бессрочно</button>
            </div>
          </>
        )}
        <p className="muted small">Сейчас: {planText(family)}.</p>
        <button className="btn primary block" disabled={save.isPending}>{save.isPending ? 'Сохраняем…' : 'Сохранить'}</button>
      </form>
    </Sheet>
  )
}
