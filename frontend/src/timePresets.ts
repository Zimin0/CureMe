import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { DEFAULT_PRESET_MINUTES, PRESET_LABELS } from './schedule'

export const PRESETS_KEY = ['schedule-presets']
export interface TimePresetsData { minutes: number[]; default: number[] }

/** Быстрые кнопки времени «Утро, День, Вечер, На ночь» с учётом личных настроек (пока не загрузились — стандартные). */
export function useTimePresets() {
  const { data } = useQuery({ queryKey: PRESETS_KEY, queryFn: () => api<TimePresetsData>('/schedule-presets') })
  const minutes = data?.minutes ?? DEFAULT_PRESET_MINUTES
  return PRESET_LABELS.map((label, i) => ({ label, minute: minutes[i] }))
}
