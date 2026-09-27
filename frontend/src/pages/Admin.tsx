import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowDown, ArrowUp, Crown, House, Pill, Plus, Search, Shield, Tags, Trash2, UserPlus, Users } from 'lucide-react'
import { useState } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { AdminFamily, AdminStats, AdminUser, api, Category } from '../api'
import { useAuth } from '../auth'
import { CategoryDraft, CategoryEditor } from '../components/CategoryEditor'
import { Empty, PageLoader, Sheet, useToast } from '../components/ui'
import { avatarColor, fmtDate, plural } from '../format'

const TABS = [
  { id: 'users', label: 'Люди' },
  { id: 'families', label: 'Семьи' },
  { id: 'categories', label: 'Категории' },
] as const
type Tab = typeof TABS[number]['id']

/** Сбрасываем всё, что могло измениться: и данные админки, и то, что показывают обычные страницы. */
function useRefresh() {
  const qc = useQueryClient()
  const { refresh } = useAuth()
  return () => {
    ['admin', 'categories', 'medicines', 'family', 'overview'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))
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
          <p className="sub">Все аккаунты и семьи Капсулки и общий для всех список категорий.</p>
        </div>
      </div>

      <div className="stats">
        <div className="stat"><span className="label"><Users size={15} />Людей</span><span className="value">{s?.users ?? '…'}</span></div>
        <div className="stat"><span className="label"><House size={15} />Семей</span><span className="value">{s?.families ?? '…'}</span></div>
        <div className="stat"><span className="label"><Pill size={15} />Лекарств</span><span className="value">{s?.medicines ?? '…'}</span></div>
        <div className="stat"><span className="label"><Tags size={15} />Категорий</span><span className="value">{s?.categories ?? '…'}</span></div>
      </div>

      <div className="segmented" role="tablist">
        {TABS.map(t => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? 'on' : ''}
            onClick={() => setParams({ tab: t.id }, { replace: true })}>{t.label}</button>
        ))}
      </div>

      {tab === 'users' && <UsersTab meId={me.id} />}
      {tab === 'families' && <FamiliesTab />}
      {tab === 'categories' && <CategoriesTab />}
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
  const onError = (e: Error) => toast(e.message, 'error')

  const save = useMutation({
    mutationFn: () => api<AdminUser>(`/admin/users/${user.id}`, {
      method: 'PATCH', body: { name, email, is_admin: isAdmin, password: password || null },
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
