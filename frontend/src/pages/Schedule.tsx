import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight, CalendarClock, Clock, Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { api, Occurrence, Schedule as ScheduleT, ScheduleSlot } from '../api'
import { useFamilyPath } from '../auth'
import { ScheduleEditor } from '../components/ScheduleEditor'
import { ScheduleNotify } from '../components/ScheduleNotify'
import { ScheduleRemove } from '../components/ScheduleRemove'
import { SlotSheet } from '../components/SlotSheet'
import { Empty, PageLoader, useToast } from '../components/ui'
import { fmtQty } from '../format'
import { usePlan } from '../plan'
import {
  addDays, DAY_SHORT, fmtDay, fmtMinute, mondayOf, mskMinute, mskToday, repeatText, scheduleText, weekdayOf,
} from '../schedule'

const EARLY = 60  // как на сервере (backend/app/schedule.py): за час до времени приёма отметка уже засчитывается,
const LATE = 180  // и ещё три часа после него

type State = 'taken' | 'due' | 'missed' | 'soon'
function stateOf(o: Occurrence, today: string, now: number): State {
  if (o.taken) return 'taken'
  if (o.date < today) return 'missed'
  if (o.date > today || o.minute > now) return 'soon'
  return now - o.minute > LATE ? 'missed' : 'due'
}
const STATE_LABEL: Record<State, string> = { taken: 'Принято', due: 'Пора принять', missed: 'Пропущено', soon: 'Впереди' }
const STATE_BADGE: Record<State, string> = { taken: 'ok', due: 'accent', missed: 'expired', soon: 'info' }

export function Schedule() {
  const fam = useFamilyPath()
  const { available } = usePlan()
  const locked = !available('schedule')
  const qc = useQueryClient()
  const toast = useToast()
  const today = mskToday()
  const [day, setDay] = useState(today)
  const [editor, setEditor] = useState<ScheduleT | 'new' | null>(null)
  const [removing, setRemoving] = useState<number | null>(null)
  const [slotSheet, setSlotSheet] = useState<{ schedule: number; slot: ScheduleSlot } | null>(null)

  const week = mondayOf(day)
  const schedules = useQuery({ queryKey: ['schedule', fam(''), 'list'], queryFn: () => api<ScheduleT[]>(fam('/schedule')) })
  const occ = useQuery({
    queryKey: ['schedule', fam(''), 'occ', week],
    queryFn: () => api<Occurrence[]>(fam(`/schedule/occurrences?since=${week}&until=${addDays(week, 6)}`)),
  })
  const now = mskMinute()
  const list = schedules.data ?? []
  const dayItems = (occ.data ?? []).filter(o => o.date === day)
  const counts = useMemo(() => {
    const c: Record<string, { all: number; taken: number }> = {}
    for (const o of occ.data ?? []) { c[o.date] ??= { all: 0, taken: 0 }; c[o.date].all++; if (o.taken) c[o.date].taken++ }
    return c
  }, [occ.data])

  const take = useMutation({
    mutationFn: (o: Occurrence) => api(fam(`/medicines/${o.medicine_id}/consume`), { body: { amount: o.amount } }),
    onSuccess: () => { qc.invalidateQueries(); toast('Отметили приём') },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const move = useMutation({
    mutationFn: ({ s, slot, weekday }: { s: number; slot: number; weekday: number }) =>
      api(fam(`/schedule/${s}/slots/${slot}`), { method: 'PATCH', body: { weekday } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedule'] }); toast('Приём перенесён') },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const dropAll = useMutation({
    mutationFn: (id: number) => api(fam(`/schedule/${id}`), { method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['schedule'] }); toast('Назначение удалено') },
    onError: (e: Error) => toast(e.message, 'error'),
  })

  if (schedules.isLoading) return <PageLoader />
  const byId = new Map(list.map(s => [s.id, s]))
  const removeTarget = removing !== null ? byId.get(removing) : undefined
  const sheetTarget = slotSheet ? byId.get(slotSheet.schedule) : undefined

  return (
    <div className="page" data-testid="schedule-page">
      <div className="page-head">
        <div>
          <h1>Расписание</h1>
          <p className="sub">Назначенные таблетки: что, когда и сколько принимать.</p>
        </div>
        <button className="btn primary" onClick={() => setEditor('new')}><Plus size={18} />Добавить</button>
      </div>

      {list.length === 0 && <ScheduleNotify />}

      {list.length === 0 ? (
        <Empty icon={<CalendarClock size={40} />} title="Расписание пока пустое"
          text="Добавьте лекарство из аптечки, выберите дни и время приёма, и оно появится здесь."
          action={<button className={`btn ${locked ? 'plus-cta' : 'primary'}`} onClick={() => setEditor('new')}><Plus size={18} />Добавить в расписание</button>} />
      ) : (
        <>
          <section className="card stack" aria-label="Приёмы на день">
            <div className="row between">
              <button className="icon-btn" aria-label="Предыдущая неделя" onClick={() => setDay(addDays(day, -7))}><ChevronLeft size={18} /></button>
              <strong>{day === today ? `Сегодня, ${fmtDay(day)}` : fmtDay(day)}</strong>
              <button className="icon-btn" aria-label="Следующая неделя" onClick={() => setDay(addDays(day, 7))}><ChevronRight size={18} /></button>
            </div>
            <div className="week-strip" role="tablist" aria-label="Дни недели">
              {DAY_SHORT.map((name, i) => {
                const iso = addDays(week, i)
                const c = counts[iso]
                return (
                  <button key={iso} role="tab" aria-selected={iso === day} className={`week-day${iso === day ? ' on' : ''}${iso === today ? ' today' : ''}`}
                    onClick={() => setDay(iso)}>
                    <span>{name}</span><b>{iso.slice(8)}</b>
                    <i className={c && c.taken === c.all ? 'dot done' : c ? 'dot' : 'dot none'} aria-hidden />
                  </button>
                )
              })}
            </div>
            {occ.isLoading ? <PageLoader /> : dayItems.length === 0 ? (
              <p className="muted">На этот день приёмов нет.</p>
            ) : (
              <div className="stack" style={{ gap: 0 }}>
                {dayItems.map(o => {
                  const st = stateOf(o, today, now)
                  return (
                    <div key={`${o.slot_id}-${o.date}`} className="list-row dose-row" data-testid="dose">
                      <div className="dose-time"><Clock size={14} />{fmtMinute(o.minute)}</div>
                      <div className="grow" style={{ minWidth: 0 }}>
                        <div className="ellipsis" style={{ fontWeight: 700 }}>{o.medicine_name}</div>
                        <div className="muted small">{fmtQty(o.amount)} {o.unit}</div>
                      </div>
                      <span className={`badge ${STATE_BADGE[st]}`}>{STATE_LABEL[st]}</span>
                      {st !== 'taken' && o.medicine_id !== null && (st !== 'soon' || (o.date === today && o.minute - now <= EARLY)) && (
                        <button className="btn primary sm" disabled={take.isPending} onClick={() => take.mutate(o)}><Check size={16} />Принял(а)</button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <WeekGrid schedules={list} onOpen={(schedule, slot) => setSlotSheet({ schedule, slot })}
            onMove={(s, slot, weekday) => move.mutate({ s, slot, weekday })} />

          <section className="card flush" aria-label="Назначения">
            <div className="card-head" style={{ padding: '16px 16px 0' }}><h2>Назначения</h2></div>
            {list.map(s => (
              <div key={s.id} className="list-row schedule-row" data-testid="schedule-row">
                <div className="grow" style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 700 }}>{s.medicine_name} <span className="muted small">· {fmtQty(s.amount)} {s.unit}</span></div>
                  <div className="muted small">{scheduleText(s)}</div>
                  {repeatText(s) && <div className="faint small">{repeatText(s)}</div>}
                </div>
                <button className="icon-btn" aria-label={`Изменить ${s.medicine_name}`} onClick={() => setEditor(s)}><Pencil size={17} /></button>
                <button className="btn ghost sm" onClick={() => setRemoving(s.id)}>Убрать приёмы</button>
                <button className="icon-btn" aria-label={`Удалить ${s.medicine_name}`}
                  onClick={() => window.confirm(`Удалить всё расписание «${s.medicine_name}»?`) && dropAll.mutate(s.id)}><Trash2 size={17} /></button>
              </div>
            ))}
          </section>
        </>
      )}

      {list.length > 0 && <ScheduleNotify />}

      {editor && <ScheduleEditor schedule={editor === 'new' ? undefined : editor} onClose={() => setEditor(null)} />}
      {removeTarget && <ScheduleRemove schedule={removeTarget} onClose={() => setRemoving(null)} />}
      {sheetTarget && slotSheet && (
        <SlotSheet schedule={sheetTarget} slot={slotSheet.slot} onClose={() => setSlotSheet(null)}
          onRemoveSeries={() => { setRemoving(sheetTarget.id); setSlotSheet(null) }} />
      )}
    </div>
  )
}

/**
 * Неделя по дням: у каждого приёма своя плашка, её можно перетащить на другой день
 * (пальцем или мышью), а нажатие открывает лист с точной правкой дня и времени.
 */
function WeekGrid({ schedules, onOpen, onMove }: {
  schedules: ScheduleT[]
  onOpen: (scheduleId: number, slot: ScheduleSlot) => void
  onMove: (scheduleId: number, slotId: number, weekday: number) => void
}) {
  const [drag, setDrag] = useState<{ label: string; x: number; y: number; over: number | null } | null>(null)
  const start = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const todayDay = weekdayOf(mskToday())
  const cols = DAY_SHORT.map((_, d) => schedules.flatMap(s => s.slots.filter(x => x.weekday === d).map(slot => ({ s, slot })))
    .sort((a, b) => a.slot.minute - b.slot.minute || a.s.medicine_name.localeCompare(b.s.medicine_name)))

  const overDay = (x: number, y: number) => {
    const el = document.elementFromPoint(x, y)?.closest('[data-weekday]')
    return el ? Number((el as HTMLElement).dataset.weekday) : null
  }
  const down = (e: React.PointerEvent<HTMLButtonElement>) => {
    start.current = { x: e.clientX, y: e.clientY, moved: false }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  const moveTo = (e: React.PointerEvent<HTMLButtonElement>, label: string) => {
    const st = start.current
    if (!st) return
    if (!st.moved && Math.hypot(e.clientX - st.x, e.clientY - st.y) < 6) return
    st.moved = true
    setDrag({ label, x: e.clientX, y: e.clientY, over: overDay(e.clientX, e.clientY) })
  }
  const up = (e: React.PointerEvent<HTMLButtonElement>, s: ScheduleT, slot: ScheduleSlot) => {
    const st = start.current
    start.current = null
    setDrag(null)
    if (!st?.moved) return onOpen(s.id, slot)
    const target = overDay(e.clientX, e.clientY)
    if (target !== null && target !== slot.weekday) onMove(s.id, slot.id, target)
  }

  return (
    <section className="card stack" aria-label="Неделя">
      <div className="card-head" style={{ marginBottom: 0 }}><h2>Неделя</h2><span className="muted small">перетащите приём на другой день</span></div>
      <div className="week-grid">
        {cols.map((items, d) => (
          <div key={d} data-weekday={d} className={`week-col${drag?.over === d ? ' over' : ''}${d === todayDay ? ' today' : ''}`}>
            <div className="week-col-head">{DAY_SHORT[d]}</div>
            {items.length === 0 && <div className="faint small week-empty">—</div>}
            {items.map(({ s, slot }) => {
              const label = `${s.medicine_name} ${fmtMinute(slot.minute)}`
              return (
                <button key={slot.id} type="button" className="slot-chip" aria-label={`${label}, ${DAY_SHORT[d]}`}
                  onPointerDown={down} onPointerMove={e => moveTo(e, label)} onPointerUp={e => up(e, s, slot)}
                  onPointerCancel={() => { start.current = null; setDrag(null) }}
                  onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onOpen(s.id, slot))}>
                  <b>{fmtMinute(slot.minute)}</b><span>{s.medicine_name}</span>
                </button>
              )
            })}
          </div>
        ))}
      </div>
      {drag && <div className="drag-ghost" style={{ left: drag.x, top: drag.y }}>{drag.label}</div>}
    </section>
  )
}
