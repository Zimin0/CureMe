import { useMutation } from '@tanstack/react-query'
import { Check, Lock, Plus } from 'lucide-react'
import { useState } from 'react'
import { api, Family } from '../api'
import { useAuth } from '../auth'
import { Sheet, useToast } from './ui'

/** Переключатель аптечек в шапке страницы. Показывается, только когда аптечек больше одной. */
export function CabinetSelect() {
  const { me, familyId, setFamilyId } = useAuth()
  if (!me || me.families.length < 2) return null
  return (
    <label className="cabinet-select">
      <span className="visually-hidden">Открытая аптечка</span>
      <select value={familyId ?? ''} onChange={e => setFamilyId(Number(e.target.value))}>
        {me.families.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
      </select>
    </label>
  )
}

/** Все аптечки человека: какая открыта, переключение и создание новой (вторая своя — в Плюсе). */
export function Cabinets() {
  const { me, familyId, setFamilyId, refresh } = useAuth()
  const toast = useToast()
  const [plusInfo, setPlusInfo] = useState(false)
  const [name, setName] = useState<string | null>(null)
  const locked = me?.own_families_left === 0

  const create = useMutation({
    mutationFn: (n: string) => api<Family>('/families', { body: { name: n } }),
    onSuccess: async d => { await refresh(); setFamilyId(d.id); setName(null); toast(`Аптечка «${d.name}» создана`) },
    // 402: лимит бесплатной версии — показываем, что это функция Плюса.
    onError: (e: Error & { status?: number }) => { setName(null); if (e.status === 402) { setPlusInfo(true); refresh() } else toast(e.message, 'error') },
  })
  if (!me) return null

  return (
    <section className="card stack">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <h2>Мои аптечки</h2>
        <button className="btn sm" onClick={() => (locked ? setPlusInfo(true) : setName(''))}>
          {locked ? <Lock size={16} /> : <Plus size={16} />}Новая аптечка
        </button>
      </div>
      <p className="muted small">
        Отдельные аптечки для дачи, машины или бабушки. У каждой свои лекарства и свои участники.
        {locked && ' В бесплатной версии одна своя аптечка, больше — в Капсулке Плюс.'}
      </p>
      <div className="cabinets">
        {me.families.map(f => (
          <button key={f.id} className={`cabinet ${f.id === familyId ? 'active' : ''}`} aria-pressed={f.id === familyId}
            onClick={() => f.id !== familyId && setFamilyId(f.id)}>
            <span className="grow ellipsis">{f.name}</span>
            {f.role === 'owner' ? <span className="faint small">своя</span> : <span className="faint small">участник</span>}
            {f.id === familyId && <Check size={16} />}
          </button>
        ))}
      </div>

      {plusInfo && (
        <Sheet title="Несколько аптечек — в Капсулке Плюс" onClose={() => setPlusInfo(false)}>
          <div className="stack">
            <p>В бесплатной версии можно завести одну свою аптечку. С Капсулкой Плюс — сколько угодно: для дачи, машины или бабушки.</p>
            <p className="muted small">Вступить в чужую аптечку по приглашению можно и без Плюса. Уже созданные аптечки остаются с вами.</p>
            <button className="btn primary block" onClick={() => setPlusInfo(false)}>Понятно</button>
          </div>
        </Sheet>
      )}
      {name !== null && (
        <Sheet title="Новая аптечка" onClose={() => setName(null)}>
          <form className="stack" onSubmit={e => { e.preventDefault(); create.mutate(name) }}>
            <p className="muted small">Например, аптечка на даче, в машине или у бабушки. Участников в неё можно пригласить отдельно.</p>
            <input className="input" autoFocus required maxLength={100} placeholder="Дача" value={name} onChange={e => setName(e.target.value)} />
            <button className="btn primary block" disabled={create.isPending}>Создать</button>
          </form>
        </Sheet>
      )}
    </section>
  )
}
