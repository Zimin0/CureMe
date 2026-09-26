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
