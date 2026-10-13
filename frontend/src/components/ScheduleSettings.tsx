import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { DEFAULT_PRESET_MINUTES, PRESET_LABELS } from '../schedule'
import { PRESETS_KEY, TimePresetsData, useTimePresets } from '../timePresets'
import { TimeSlider } from './TimeSlider'
import { Sheet, useToast } from './ui'

/** Настройки расписания: во сколько для вас «утро», «день», «вечер» и «на ночь» (кнопки быстрого выбора времени). */
export function ScheduleSettings({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const current = useTimePresets()
  const [minutes, setMinutes] = useState(current.map(p => p.minute))
  const [open, setOpen] = useState<number | null>(null)
  const save = useMutation({
    mutationFn: (m: number[]) => api<TimePresetsData>('/schedule-presets', { method: 'PUT', body: { minutes: m } }),
    onSuccess: data => { qc.setQueryData(PRESETS_KEY, data); toast('Настройки сохранены'); onClose() },
    onError: (e: Error) => toast(e.message, 'error'),
  })
  const set = (i: number, m: number) => setMinutes(minutes.map((x, j) => (j === i ? m : x)))
  const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`

  return (
    <Sheet title="Настройки расписания" onClose={onClose}>
      <div className="stack lg">
        <p className="muted small">Время кнопок «Утро», «День», «Вечер» и «На ночь» при добавлении приёма. Уже созданные приёмы не меняются.</p>
        <div className="stack" style={{ gap: 8 }}>
          {PRESET_LABELS.map((label, i) => (
            <div key={label} className="stack" style={{ gap: 8 }}>
              <button type="button" className="btn block" aria-expanded={open === i} onClick={() => setOpen(open === i ? null : i)}>
                <span>{label}</span><b style={{ marginLeft: 'auto' }}>{fmt(minutes[i])}</b>
              </button>
              {open === i && <TimeSlider value={minutes[i]} onChange={m => set(i, m)} label={`${label}: время`} />}
            </div>
          ))}
        </div>
        <button className="btn primary block" disabled={save.isPending} onClick={() => save.mutate(minutes)}>Сохранить</button>
        <button className="btn ghost block" disabled={save.isPending} onClick={() => setMinutes(DEFAULT_PRESET_MINUTES)}>Вернуть стандартное время</button>
      </div>
    </Sheet>
  )
}
