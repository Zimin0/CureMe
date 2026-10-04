import { useMutation } from '@tanstack/react-query'
import { KeyRound, MonitorOff } from 'lucide-react'
import { useState } from 'react'
import { api, Me } from '../api'
import { useAuth } from '../auth'
import { Sheet, useToast } from './ui'

type TokenOut = { access_token: string; user: Me }

/** «Выйти на всех устройствах»: старые входы перестают работать, это устройство остаётся в аккаунте. */
export function LogoutEverywhereButton() {
  const { signIn } = useAuth()
  const toast = useToast()
  const m = useMutation({
    mutationFn: () => api<TokenOut>('/auth/logout-all', { method: 'POST' }),
    onSuccess: d => { signIn(d.access_token, d.user); toast('Вы вышли на всех остальных устройствах') },
  })
  return (
    <button type="button" className="btn ghost" disabled={m.isPending}
      onClick={() => confirm('Выйти на всех остальных устройствах? На этом вы останетесь в аккаунте.') && m.mutate()}>
      <MonitorOff size={16} />Выйти на всех устройствах
    </button>
  )
}

/** Смена пароля: нужен текущий, новый не короче 12 символов (администратору 16). После смены остальные входы закрываются. */
export function ChangePasswordButton() {
  const { me, signIn } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const min = me?.is_admin ? 16 : 12
  const m = useMutation({
    mutationFn: () => api<Me & { access_token?: string }>('/auth/me', { method: 'PATCH', body: { password: next, current_password: current } }),
    onSuccess: d => {
      if (d.access_token) signIn(d.access_token, d)
      setOpen(false); setCurrent(''); setNext('')
      toast('Пароль изменён, на других устройствах вы вышли')
    },
  })
  return (
    <>
      <button type="button" className="btn ghost" onClick={() => setOpen(true)}><KeyRound size={16} />Сменить пароль</button>
      {open && (
        <Sheet title="Сменить пароль" onClose={() => setOpen(false)}>
          <form className="stack" onSubmit={e => { e.preventDefault(); m.mutate() }}>
            <label className="field"><span>Текущий пароль</span>
              <input className="input" type="password" autoComplete="current-password" required value={current} onChange={e => setCurrent(e.target.value)} />
            </label>
            <label className="field"><span>Новый пароль</span>
              <input className="input" type="password" autoComplete="new-password" required minLength={min} value={next} onChange={e => setNext(e.target.value)} />
              <span className="hint">Не короче {min} символов. Лучше фраза из нескольких слов, её легко помнить и трудно подобрать.</span>
            </label>
            {m.error && <div className="alert error">{m.error.message}</div>}
            <button className="btn primary block" disabled={m.isPending}>{m.isPending ? 'Меняем…' : 'Сменить пароль'}</button>
          </form>
        </Sheet>
      )}
    </>
  )
}
