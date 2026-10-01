import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, Schedule } from '../api'
import { useFamilyPath } from '../auth'
import { daysText, fmtMinute } from '../schedule'
import { DayChips } from './SchedulePickers'
import { Sheet, useToast } from './ui'

/** Фраза для подтверждения: «Амепрозол: вт, 16:00». */
function summary(s: Schedule, days: number[], times: number[]) {
  const d = days.length ? daysText(days) : 'любой день'
  const t = times.length ? times.map(fmtMinute).join(', ') : 'любое время'
  return `${s.medicine_name}: ${d}, ${t}`
}

/**
 * «Больше не пью амепрозол по вторникам в 16:00»: выбираем дни и время, совпадающие приёмы уходят серией.
 * Остальные приёмы этого лекарства не трогаем.
 */
export function ScheduleRemove({ schedule, onClose }: { schedule: Schedule; onClose: () => void }) {
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const slotDays = [...new Set(schedule.slots.map(s => s.weekday))].sort()
  const slotTimes = [...new Set(schedule.slots.map(s => s.minute))].sort((a, b) => a - b)
  const [days, setDays] = useState<number[]>([])
  const [times, setTimes] = useState<number[]>([])

  const hit = schedule.slots.filter(s => (!days.length || days.includes(s.weekday)) && (!times.length || times.includes(s.minute)))
  const nothing = !days.length && !times.length
  const remove = useMutation({
    mutationFn: (body: { days: number[]; times: number[] }) => api(fam(`/schedule/${schedule.id}/remove`), { body }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedule'] }); toast('Приёмы убраны из расписания'); onClose() },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const toggleTime = (m: number) => setTimes(times.includes(m) ? times.filter(x => x !== m) : [...times, m].sort((a, b) => a - b))

  return (
    <Sheet title={`Убрать приёмы: ${schedule.medicine_name}`} onClose={onClose}>
      <div className="stack lg">
        <p className="muted small">Выберите дни и время, которые больше не нужны. Пустой выбор дней или времени значит «любые».</p>
        <section className="stack" style={{ gap: 8 }}>
          <h3>Дни</h3>
          <DayChips value={days} onChange={setDays} presets={false} only={slotDays} />
        </section>
        <section className="stack" style={{ gap: 8 }}>
          <h3>Время</h3>
          <div className="chips wrap" role="group" aria-label="Время приёма">
            {slotTimes.map(m => (
              <button key={m} type="button" className={`chip${times.includes(m) ? ' active' : ''}`} aria-pressed={times.includes(m)}
                onClick={() => toggleTime(m)}>{fmtMinute(m)}</button>
            ))}
          </div>
        </section>
        <p className="remove-summary" aria-live="polite">
          {nothing ? 'Выберите, что убрать' : hit.length
            ? <>Больше не принимать — <b>{summary(schedule, days, times)}</b> ({hit.length} из {schedule.slots.length} приёмов в неделю)</>
            : 'Таких приёмов в расписании нет'}
        </p>
        <button className="btn danger block" disabled={nothing || !hit.length || remove.isPending}
          onClick={() => remove.mutate({ days, times })}>Убрать эти приёмы</button>
        <button className="btn ghost block" disabled={remove.isPending} onClick={() => remove.mutate({ days: [], times: [] })}>
          Убрать всё расписание этого лекарства
        </button>
      </div>
    </Sheet>
  )
}

