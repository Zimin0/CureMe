import { useMutation } from '@tanstack/react-query'
import { api, Family } from './api'
import { useAuth } from './auth'
import { fmtDate } from './format'

/** Начало ответа сервера, когда у человека оплачен Плюс и без переноса дней вступить нельзя (R08 «а»). */
const NEEDS_CARRY = 'У вашей семьи оплачен Плюс'

/** Вступление по коду. Если у человека оплачен Плюс, сервер просит решение: перенести оставшиеся дни в новую семью или не вступать. */
export function useJoinFamily(code: string, onJoined: (f: Family) => void | Promise<void>) {
  const m = useMutation({
    mutationFn: (carry: boolean) => api<Family>('/families/join', { body: carry ? { code, carry_plus: true } : { code } }),
    onSuccess: onJoined,
  })
  return {
    join: () => m.mutate(false),
    joinCarrying: () => m.mutate(true),
    pending: m.isPending,
    error: m.error,
    needsCarry: !!m.error?.message.startsWith(NEEDS_CARRY),
  }
}

/** Ошибка вступления; при оплаченном Плюсе вместо тупика кнопка «Перенести дни и вступить». */
export function JoinError({ j }: { j: ReturnType<typeof useJoinFamily> }) {
  if (!j.error) return null
  return (
    <>
      <div className="alert error" role="alert">{j.error.message}</div>
      {j.needsCarry && <button type="button" className="btn primary block" disabled={j.pending} onClick={j.joinCarrying}>Перенести дни и вступить</button>}
    </>
  )
}

/** Смена семьи раз в 30 дней (R11): пока рано, показываем дату заранее, а не ошибкой после нажатия. */
export function CooldownNote() {
  const { me } = useAuth()
  const until = me?.next_change_at
  if (!until || new Date(until).getTime() <= Date.now()) return null
  return <p className="muted small" role="note">Сменить семью можно раз в 30 дней: следующий раз с {fmtDate(until)}.</p>
}
