import { useMutation } from '@tanstack/react-query'
import { Check, Plus } from 'lucide-react'
import { useState } from 'react'
import { api, Family } from '../api'
import { useAuth } from '../auth'
import { PlusBanner, usePlusSheet } from '../plan'
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
  const openPlus = usePlusSheet()
  const [name, setName] = useState<string | null>(null)
  const locked = me?.own_families_left === 0

  const create = useMutation({
    mutationFn: (n: string) => api<Family>('/families', { body: { name: n } }),
    onSuccess: async d => { await refresh(); setFamilyId(d.id); setName(null); toast(`Аптечка «${d.name}» создана`) },
    // 402 (лимит бесплатной версии) сам открывает шторку Плюса; обновляем счётчик своих аптечек.
    onError: (e: Error & { status?: number }) => { setName(null); if (e.status === 402) refresh(); else toast(e.message, 'error') },
  })
  if (!me) return null

  return (
    <section className="card stack">
      <div className="card-head" style={{ marginBottom: 0 }}>
        <h2>Мои аптечки</h2>
      </div>
      <fieldset className="locked-block" disabled={locked}>
        <p className="muted small">
          Отдельные аптечки для дачи, машины или бабушки. У каждой свои лекарства и свои участники.
        </p>
        <button type="button" className="btn sm" style={{ alignSelf: 'flex-start' }} onClick={() => setName('')}><Plus size={16} />Новая аптечка</button>
      </fieldset>
      {locked && me.plus_active && (
        <p className="muted small" role="note">Достигнут потолок: не больше 5 своих аптечек. Нужно больше — напишите нам.</p>
      )}
      {locked && !me.plus_active && (
        <PlusBanner title="Новая аптечка — в Капсулке Плюс" cta="Новая аптечка" onClick={() => openPlus('cabinets')}
          text="В бесплатной версии одна своя аптечка, больше — в Капсулке Плюс." />
      )}
      {/* Одна аптечка — выбирать нечего, список показываем только когда их несколько. */}
      {me.families.length > 1 && <div className="cabinets">
        {me.families.map(f => (
          <button key={f.id} className={`cabinet ${f.id === familyId ? 'active' : ''}`} aria-pressed={f.id === familyId}
            onClick={() => f.id !== familyId && setFamilyId(f.id)}>
            <span className="grow ellipsis">{f.name}</span>
            {f.role === 'owner' ? <span className="faint small">своя</span> : <span className="faint small">участник</span>}
            {f.id === familyId && <Check size={16} />}
          </button>
        ))}
      </div>}

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
