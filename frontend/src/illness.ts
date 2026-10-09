/** Дни в истории болезней — строки 'YYYY-MM-DD' по местному времени: так их хранит сервер и понимает <input type="date">. */
export const dayKey = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function parseDay(key: string) {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Выбранный период в порядке «с — по», как бы ни тянули: вперёд или назад. */
export function orderedRange(a: string, b: string): [string, string] {
  return a <= b ? [a, b] : [b, a]
}

export function inRange(day: string, from: string, to: string) {
  return day >= from && day <= to
}

export function daysIn(from: string, to: string) {
  return Math.round((parseDay(to).getTime() - parseDay(from).getTime()) / 86_400_000) + 1
}

const short = (key: string, withYear: boolean) =>
  parseDay(key).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: withYear ? 'numeric' : undefined })

/** «5 октября» или «5 – 9 октября» (год добавляем, если он не текущий). */
export function periodLabel(from: string, to: string, now = new Date()) {
  const y = now.getFullYear()
  const withYear = parseDay(from).getFullYear() !== y || parseDay(to).getFullYear() !== y
  if (from === to) return short(from, withYear)
  const a = parseDay(from), b = parseDay(to)
  if (a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth()) {
    return `${a.getDate()} – ${short(to, withYear)}`
  }
  return `${short(from, withYear)} – ${short(to, withYear)}`
}

/** Недели месяца с понедельника: пустые клетки до первого и после последнего дня — null. */
export function monthGrid(year: number, month: number): (string | null)[][] {
  const first = new Date(year, month, 1)
  const lead = (first.getDay() + 6) % 7
  const total = new Date(year, month + 1, 0).getDate()
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: total }, (_, i) => dayKey(new Date(year, month, i + 1)))]
  while (cells.length % 7) cells.push(null)
  return Array.from({ length: cells.length / 7 }, (_, w) => cells.slice(w * 7, w * 7 + 7))
}
