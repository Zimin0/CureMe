import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, Medicine, Schedule } from '../api'
import { useFamilyPath } from '../auth'
import { COURSES, EVERY_DAY, addDays, mskToday } from '../schedule'
import { DayChips, TimesPicker } from './SchedulePickers'
import { Stepper } from './QuantityInput'
import { PlusBanner, usePlan } from '../plan'
import { Sheet, useToast } from './ui'

/**
 * Лист «Добавить в расписание»: лекарство из аптечки → дни → время → сколько → на какой срок.
 * С `schedule` — правка назначения: лекарство не меняется, дни и время можно только добавить
 * (убрать приёмы — через «Убрать приёмы», там выбираются дни и время серией).
 */
export function ScheduleEditor({ schedule, onClose }: { schedule?: Schedule; onClose: () => void }) {
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const editing = !!schedule
  const { available } = usePlan()
  const locked = !editing && !available('schedule')
  const [medId, setMedId] = useState<number | null>(schedule?.medicine_id ?? null)
  const [search, setSearch] = useState('')
  const [amount, setAmount] = useState(schedule?.amount ?? 1)
  const [days, setDays] = useState<number[]>(editing ? [] : EVERY_DAY)
  const [times, setTimes] = useState<number[]>([])
  const [everyWeeks, setEveryWeeks] = useState(schedule?.every_weeks ?? 1)
  const [end, setEnd] = useState<string | null>(schedule?.end_date ?? null)

  const meds = useQuery({
    queryKey: ['medicines', fam(''), ''], queryFn: () => api<Medicine[]>(fam('/medicines')), enabled: !editing,
  })
  const folded = search.trim().toLowerCase().replace(/ё/g, 'е')
  const shown = (meds.data ?? []).filter(m => !folded || m.name.toLowerCase().replace(/ё/g, 'е').includes(folded))
  const med = meds.data?.find(m => m.id === medId)

  const save = useMutation({
    mutationFn: async () => {
      if (!schedule) {
        return api(fam('/schedule'), { body: { medicine_id: medId, amount, days, times, every_weeks: everyWeeks, end_date: end } })
      }
      await api(fam(`/schedule/${schedule.id}`), { method: 'PATCH', body: { amount, every_weeks: everyWeeks, end_date: end } })
      if (times.length) await api(fam(`/schedule/${schedule.id}/slots`), { body: { days: days.length ? days : EVERY_DAY, times } })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedule'] }); toast(editing ? 'Расписание обновлено' : 'Добавили в расписание'); onClose() },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const ready = editing ? true : medId !== null && days.length > 0 && times.length > 0
  const unit = schedule?.unit ?? med?.unit ?? 'шт'

  return (
    <Sheet title={editing ? `Расписание: ${schedule.medicine_name}` : 'Добавить в расписание'} onClose={onClose}>
      <div className="stack lg">
        {locked && (
          <PlusBanner testId="plus-banner" title="Расписание — в Капсулке Плюс" to="/plus" cta="Узнать про Плюс"
            text="Подключите Плюс, и можно будет добавлять приёмы в расписание. Уже созданное останется." />
        )}
        <fieldset className="locked-block stack lg" disabled={locked}>
        {!editing && (
          <section className="stack" style={{ gap: 8 }}>
            <h3>1. Лекарство из аптечки</h3>
            {meds.data && meds.data.length === 0 ? (
              <p className="muted small">В аптечке пока пусто. <Link to="/medicines/new" onClick={onClose}>Добавьте лекарство</Link>, и его можно будет назначить.</p>
            ) : (
              <>
                {(meds.data?.length ?? 0) > 6 && (
                  <label className="search"><Search size={16} />
                    <input className="input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Найти в аптечке" aria-label="Найти лекарство" />
                  </label>
                )}
                <div className="chips wrap" role="radiogroup" aria-label="Лекарство">
                  {shown.map(m => (
                    <button key={m.id} type="button" role="radio" aria-checked={medId === m.id}
                      className={`chip${medId === m.id ? ' active' : ''}`} onClick={() => setMedId(m.id)}>{m.name}</button>
                  ))}
                </div>
              </>
            )}
          </section>
        )}

        <section className="stack" style={{ gap: 8 }}>
          <h3>{editing ? 'Сколько за раз' : '2. Сколько за раз'}</h3>
          <div className="row"><Stepper value={amount} onChange={setAmount} min={0.5} label="Доза за один приём" /><span className="muted">{unit}</span></div>
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h3>{editing ? 'Добавить дни' : '3. Дни'}</h3>
          <DayChips value={days} onChange={setDays} />
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h3>{editing ? 'Добавить время' : '4. Время (можно несколько раз в день)'}</h3>
          <TimesPicker value={times} onChange={setTimes} />
        </section>

        <section className="stack" style={{ gap: 8 }}>
          <h3>{editing ? 'Повтор и срок' : '5. Повтор и срок'}</h3>
          <div className="segmented" role="group" aria-label="Повтор">
            <button type="button" className={everyWeeks === 1 ? 'on' : ''} onClick={() => setEveryWeeks(1)}>Каждую неделю</button>
            <button type="button" className={everyWeeks === 2 ? 'on' : ''} onClick={() => setEveryWeeks(2)}>Через неделю</button>
          </div>
          <div className="chips wrap" aria-label="Срок курса">
            {COURSES.map(c => {
              const value = c.days === null ? null : addDays(schedule?.start_date ?? mskToday(), c.days - 1)
              return <button key={c.label} type="button" className={`chip${end === value ? ' active' : ''}`} onClick={() => setEnd(value)}>{c.label}</button>
            })}
          </div>
        </section>

        <button className="btn primary block" disabled={!ready || save.isPending} onClick={() => save.mutate()}>
          {editing ? 'Сохранить' : 'Добавить в расписание'}
        </button>
        </fieldset>
      </div>
    </Sheet>
  )
}
