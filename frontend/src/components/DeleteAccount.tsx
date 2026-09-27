import { useMutation } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth'
import { Sheet, useToast } from './ui'

/**
 * Удаление аккаунта. По 152-ФЗ это и отзыв согласия: данные стираются сразу,
 * а общая аптечка остаётся остальным участникам семьи.
 */
export function DeleteAccountButton({ className = 'btn ghost' }: { className?: string }) {
  const { signOut } = useAuth()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const m = useMutation({
    mutationFn: () => api<void>('/auth/me', { method: 'DELETE', body: { password } }),
    onSuccess: () => { signOut(); toast('Аккаунт удалён') },
  })
  return (
    <>
      <button type="button" className={className} onClick={() => setOpen(true)}><Trash2 size={16} />Удалить аккаунт</button>
      {open && (
        <Sheet title="Удалить аккаунт?" onClose={() => setOpen(false)}>
          <form className="stack" onSubmit={e => { e.preventDefault(); m.mutate() }}>
            <p className="muted">Удалятся ваш аккаунт, личные отметки и заметки. Лекарства общей аптечки останутся у других участников семьи, а если вы в семье один — аптечка удалится целиком. Отменить это нельзя.</p>
            <label className="field"><span>Пароль для подтверждения</span>
              <input className="input" type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
            </label>
            {m.error && <div className="alert error">{m.error.message}</div>}
            <button className="btn danger block" disabled={m.isPending}>{m.isPending ? 'Удаляем…' : 'Удалить навсегда'}</button>
          </form>
        </Sheet>
      )}
    </>
  )
}
