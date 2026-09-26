import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { api, Family } from '../api'
import { useAuth } from '../auth'

/** Пользователь вышел из всех семей: предлагаем создать новую или вступить по коду. */
export function NoFamily() {
  const { refresh, setFamilyId, signOut } = useAuth()
  const [name, setName] = useState('Моя семья')
  const [code, setCode] = useState('')
  const done = async (f: Family) => { await refresh(); setFamilyId(f.id) }
  const create = useMutation({ mutationFn: () => api<Family>('/families', { body: { name } }), onSuccess: done })
  const join = useMutation({ mutationFn: () => api<Family>('/families/join', { body: { code } }), onSuccess: done })
  return (
    <div className="auth-wrap">
      <div className="auth-card stack lg">
        <h1 style={{ textAlign: 'center' }}>Вы пока не в семье</h1>
        <form className="card stack" onSubmit={e => { e.preventDefault(); create.mutate() }}>
          <h2>Создать аптечку</h2>
          <input className="input" required value={name} onChange={e => setName(e.target.value)} />
          <button className="btn primary block">Создать</button>
        </form>
        <form className="card stack" onSubmit={e => { e.preventDefault(); join.mutate() }}>
          <h2>Вступить по коду</h2>
          <input className="input" required value={code} onChange={e => setCode(e.target.value)} placeholder="Код приглашения" style={{ textTransform: 'uppercase' }} />
          {join.error && <div className="alert error">{join.error.message}</div>}
          <button className="btn block">Вступить</button>
        </form>
        <button className="btn ghost" onClick={signOut}>Выйти из аккаунта</button>
      </div>
    </div>
  )
}
