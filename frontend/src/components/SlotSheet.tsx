import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, Schedule, ScheduleSlot } from '../api'
import { useFamilyPath } from '../auth'
import { DAY_LONG, DAY_SHORT, fmtMinute } from '../schedule'
import { TimeSlider } from './TimeSlider'
import { Sheet, useToast } from './ui'

/** Один приём: сдвинуть на другой день или время либо убрать. То же, что перетаскивание, но нажатиями. */
export function SlotSheet({ schedule, slot, onClose, onRemoveSeries }: {
  schedule: Schedule; slot: ScheduleSlot; onClose: () => void; onRemoveSeries: () => void
}) {
  const fam = useFamilyPath()
  const qc = useQueryClient()
  const toast = useToast()
  const [weekday, setWeekday] = useState(slot.weekday)
  const [minute, setMinute] = useState(slot.minute)
  const done = (text: string) => { qc.invalidateQueries({ queryKey: ['schedule'] }); toast(text); onClose() }
  const onError = (e: Error) => toast(e.message, 'error')
  const move = useMutation({
    mutationFn: () => api(fam(`/schedule/${schedule.id}/slots/${slot.id}`), { method: 'PATCH', body: { weekday, minute } }),
    onSuccess: () => done('Приём перенесён'), onError,
  })
  const drop = useMutation({
    mutationFn: () => api(fam(`/schedule/${schedule.id}/remove`), { body: { days: [slot.weekday], times: [slot.minute] } }),
    onSuccess: () => done('Приём убран'), onError,
  })
  const changed = weekday !== slot.weekday || minute !== slot.minute
  return (
    <Sheet title={`${schedule.medicine_name}: ${DAY_LONG[slot.weekday]}, ${fmtMinute(slot.minute)}`} onClose={onClose}>
      <div className="stack lg">
        <section className="stack" style={{ gap: 8 }}>
          <h3>День</h3>
          <div className="chips wrap" role="radiogroup" aria-label="День недели">
            {DAY_SHORT.map((d, i) => (
              <button key={d} type="button" role="radio" aria-checked={weekday === i} className={`chip day-chip${weekday === i ? ' active' : ''}`}
                onClick={() => setWeekday(i)}>{d}</button>
            ))}
          </div>
        </section>
        <section className="stack" style={{ gap: 8 }}>
          <h3>Время</h3>
          <TimeSlider value={minute} onChange={setMinute} />
        </section>
        <button className="btn primary block" disabled={!changed || move.isPending} onClick={() => move.mutate()}>Перенести</button>
        <button className="btn danger block" disabled={drop.isPending} onClick={() => drop.mutate()}>Убрать только этот приём</button>
        <button className="btn ghost block" onClick={onRemoveSeries}>Убрать серией…</button>
      </div>
    </Sheet>
  )
}
