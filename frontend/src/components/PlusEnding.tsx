import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Snowflake } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Family, FamilyBrief } from '../api'
import { useAuth } from '../auth'
import { fmtDate } from '../format'
import { Sheet, useToast } from './ui'

/** Название аптечки в списках выбора: замороженная помечена. */
export const cabinetLabel = (f: FamilyBrief) => (f.status === 'frozen' ? `${f.name} (заморожена)` : f.name)

/** Вверху приложения: Плюс семьи заканчивается или закончился, идёт срок выбора состава (R13). Видят все люди семьи, решает владелец. */
export function PlusEndingBanner() {
  const { me } = useAuth()
  const e = me?.plus_ending
  if (!e) return null
  const date = fmtDate(e.date)
  return (
    <div className="alert warn" role="status" aria-label="Плюс семьи заканчивается" style={{ marginBottom: 14 }}>
      <div className="grow">
        {e.state === 'ending'
          ? <>Плюс семьи заканчивается {date}. Платные функции закроются сразу, а ещё 5 дней владелец сможет выбрать, кто из людей и какие аптечки остаются: бесплатно в семье не больше {e.people_limit} человек. Ничего не удаляется.</>
          : <>Плюс семьи закончился. До {date} владелец выбирает, кто остаётся в семье и какие аптечки остаются активными: бесплатно в семье не больше {e.people_limit} человек. Потом лишние люди перейдут в личные семьи со своей аптечкой, лишние аптечки заморозятся. Ничего не удаляется.</>}
        {' '}
        {e.is_owner
          ? <>{e.state === 'ended' && <><Link to="/family">Выбрать состав</Link>. </>}<Link to="/plus">Продлить Плюс</Link></>
          : <>Решает владелец семьи.</>}
      </div>
    </div>
  )
}

/** Замороженную аптечку можно смотреть и выгружать, но не менять (R14). */
export function FrozenNotice() {
  const { me, familyId } = useAuth()
  const cur = me?.families.find(f => f.id === familyId)
  if (cur?.status !== 'frozen') return null
  return (
    <div className="alert info" role="status" aria-label="Аптечка заморожена" style={{ marginBottom: 14 }}>
      <Snowflake size={18} style={{ flex: 'none' }} />
      <div className="grow">
        Аптечка «{cur.name}» заморожена после окончания Плюса: её можно смотреть и выгружать, но не менять. Перенесите лекарства в активную аптечку или подключите <Link to="/plus">Капсулку Плюс</Link>: заморозка снимется сразу. Ничего не удалено.
      </div>
    </div>
  )
}

/** Владелец сам выбирает, кто остаётся и какие аптечки остаются активными; выбор применяется сразу (R13). */
export function CompressSection({ family }: { family: Family }) {
  const { me } = useAuth()
  const [open, setOpen] = useState(false)
  const e = me?.plus_ending
  if (!e || e.state !== 'ended' || !e.is_owner) return null
  return (
    <section className="card stack" aria-label="Выбор состава семьи">
      <h2>Плюс закончился: выберите состав</h2>
      <p className="muted small">До {fmtDate(e.date)} в семье можно оставить до {e.people_limit} человек (вместе с вами) и столько активных аптечек, сколько людей (не больше трёх). Если выбора не будет, останетесь вы и самые давние участники, остальные перейдут в личные семьи со своей аптечкой. Ничего не удаляется.</p>
      <button className="btn primary" style={{ alignSelf: 'flex-start' }} onClick={() => setOpen(true)}>Выбрать состав</button>
      {open && <CompressSheet family={family} limit={e.people_limit} onClose={() => setOpen(false)} />}
    </section>
  )
}

function CompressSheet({ family, limit, onClose }: { family: Family; limit: number; onClose: () => void }) {
  const { me, refresh } = useAuth()
  const qc = useQueryClient()
  const toast = useToast()
  const ownerId = family.members.find(m => m.role === 'owner')?.user_id ?? me?.id ?? 0
  // По умолчанию отмечены те, кто останется без выбора: самые давние по вступлению.
  const others = [...family.members].filter(m => m.user_id !== ownerId)
    .sort((a, b) => a.joined_at.localeCompare(b.joined_at) || a.user_id - b.user_id)
  const [people, setPeople] = useState<number[]>(others.slice(0, Math.max(limit - 1, 0)).map(m => m.user_id))
  const [cabinets, setCabinets] = useState<number[]>([])
  const cabinetCap = Math.min(3, people.length + 1)
  const tooManyPeople = people.length + 1 > limit
  const tooManyCabinets = cabinets.length > cabinetCap
  const toggle = (list: number[], set: (v: number[]) => void, id: number) =>
    set(list.includes(id) ? list.filter(x => x !== id) : [...list, id])

  const save = useMutation({
    mutationFn: () => api<Family>(`/families/${family.id}/compress`, { method: 'POST', body: { keep_user_ids: people, keep_cabinet_ids: cabinets } }),
    onSuccess: async () => {
      await refresh()
      qc.invalidateQueries({ queryKey: ['family'] })
      qc.invalidateQueries({ queryKey: ['plan'] })
      toast('Состав семьи выбран')
      onClose()
    },
    onError: (err: Error) => toast(err.message, 'error'),
  })

  return (
    <Sheet title="Кто остаётся в семье" onClose={onClose}>
      <form className="stack" onSubmit={ev => {
        ev.preventDefault()
        const leaving = others.length - people.length
        if (confirm(leaving > 0
          ? `${leaving} чел. перейдут в личные семьи со своей аптечкой, остальные аптечки будут заморожены (их можно смотреть и выгружать). Ничего не удаляется. Продолжить?`
          : 'Состав семьи не меняется, лишние аптечки (если они есть) будут заморожены: их можно смотреть и выгружать. Продолжить?')) save.mutate()
      }}>
        <div className="stack" role="group" aria-label="Люди">
          <b>Люди: {people.length + 1} из {limit}</b>
          <label className="check"><input type="checkbox" checked disabled /><span>{family.members.find(m => m.user_id === ownerId)?.name ?? 'Вы'} (владелец)</span></label>
          {others.map(m => (
            <label key={m.user_id} className="check">
              <input type="checkbox" checked={people.includes(m.user_id)} onChange={() => toggle(people, setPeople, m.user_id)} />
              <span>{m.name}</span>
            </label>
          ))}
          {tooManyPeople && <span className="small" role="alert" style={{ color: 'var(--danger)' }}>Бесплатно в семье не больше {limit} человек, вместе с вами.</span>}
        </div>
        {me && me.families.length > 1 && (
          <div className="stack" role="group" aria-label="Аптечки">
            <b>Активные аптечки: {cabinets.length} из {cabinetCap}</b>
            <span className="muted small">Не отметите ни одной: останутся самые давние. Остальные заморозятся, ничего не удалится.</span>
            {me.families.map(f => (
              <label key={f.id} className="check">
                <input type="checkbox" checked={cabinets.includes(f.id)} onChange={() => toggle(cabinets, setCabinets, f.id)} />
                <span>{f.name}{f.status === 'frozen' ? ' (заморожена)' : ''}</span>
              </label>
            ))}
            {tooManyCabinets && <span className="small" role="alert" style={{ color: 'var(--danger)' }}>Активных аптечек столько, сколько людей: не больше {cabinetCap}.</span>}
          </div>
        )}
        <button className="btn primary block" disabled={save.isPending || tooManyPeople || tooManyCabinets}>Сохранить выбор</button>
      </form>
    </Sheet>
  )
}
