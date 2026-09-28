import type { Medicine, Stock } from './api'

export function plural(n: number, one: string, few: string, many: string) {
  const a = Math.abs(n) % 100, b = a % 10
  if (a > 10 && a < 20) return many
  if (b > 1 && b < 5) return few
  if (b === 1) return one
  return many
}

export function fmtDate(iso: string | null | undefined) {
  if (!iso) return '—'
  return new Date(iso + (iso.length === 10 ? 'T00:00:00' : '')).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

export function fmtQty(n: number) {
  return Number.isInteger(n) ? String(n) : n.toFixed(1).replace('.', ',')
}

export function daysText(days: number) {
  if (days < 0) return `просрочено ${-days} ${plural(-days, 'день', 'дня', 'дней')} назад`
  if (days === 0) return 'истекает сегодня'
  return `ещё ${days} ${plural(days, 'день', 'дня', 'дней')}`
}

export const STATUS_LABEL: Record<Stock['status'], string> = {
  ok: 'В наличии',
  low: 'Заканчивается',
  out: 'Закончилось',
  expiring: 'Скоро истекает',
  expired: 'Есть просрочка',
}

export function subtitle(m: Medicine) {
  return [m.form, m.dosage, m.manufacturer].filter(Boolean).join(' · ')
}

export function todayISO(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toLocaleDateString('sv-SE') // YYYY-MM-DD в местном времени
}

export function splitTags(s: string) {
  return s.split(/[,;\n]/).map(t => t.trim()).filter(Boolean)
}

const AVATAR_COLORS = ['#0f9d8a', '#3e63dd', '#d6409f', '#f76b15', '#8e4ec6', '#30a46c', '#e5484d']
export function avatarColor(id: number) { return AVATAR_COLORS[id % AVATAR_COLORS.length] }

/** «Сегодня», «Вчера» или дата: заголовки дней в истории приёма. */
export function dayTitle(iso: string, now = new Date()) {
  const d = new Date(iso)
  const key = (x: Date) => x.toLocaleDateString('sv-SE')
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (key(d) === key(now)) return 'Сегодня'
  if (key(d) === key(yesterday)) return 'Вчера'
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: d.getFullYear() === now.getFullYear() ? undefined : 'numeric', weekday: 'short' })
}

export function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}
