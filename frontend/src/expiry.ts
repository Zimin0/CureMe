/**
 * Достаёт срок годности из текста: того, что человек ввёл руками,
 * или того, что распознано на фото упаковки.
 *
 * На российских упаковках встречается: «Годен до 05.2027», «ГОДЕН ДО: 31.05.2027»,
 * «EXP 05/2027», «до 05/27», «2027-05», «май 2027». Рядом часто стоит дата
 * изготовления, поэтому выбираем дату после «годен/exp/до», а если слов нет — самую позднюю.
 */

const MONTHS: Record<string, number> = {
  янв: 1, фев: 2, мар: 3, апр: 4, мая: 5, май: 5, июн: 6, июл: 7, авг: 8, сен: 9, окт: 10, ноя: 11, дек: 12,
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
}
const EXPIRY_WORDS = /(годен|годн|срок|exp|use\s*by|best\s*before|до\b|g[o0]den)/i
const MADE_WORDS = /(изг|дата\s*пр|mfg|mfd|manuf|произв)/i

interface Candidate { date: Date; index: number }

const lastDay = (y: number, m: number) => new Date(y, m, 0).getDate()
const fullYear = (y: number) => (y < 100 ? 2000 + y : y)

function make(y: number, m: number, d?: number): Date | null {
  y = fullYear(y)
  if (m < 1 || m > 12 || y < 2000 || y > 2100) return null
  const day = d ?? lastDay(y, m) // только месяц и год → годен до конца месяца
  if (day < 1 || day > lastDay(y, m)) return null
  return new Date(y, m - 1, day)
}

/** OCR путает похожие символы в цифрах: O→0, I/l/|→1. Правим только «числовые» куски текста. */
function fixDigits(text: string) {
  return text.replace(/[0-9OoОоIl|][0-9OoОоIl|.\/\-]{2,}/g, chunk =>
    (chunk.match(/\d/g)?.length ?? 0) >= 2 ? chunk.replace(/[OoОо]/g, '0').replace(/[Il|]/g, '1') : chunk)
}

function candidates(raw: string): Candidate[] {
  const text = fixDigits(raw)
  const out: Candidate[] = []
  const push = (d: Date | null, index: number) => { if (d) out.push({ date: d, index }) }
  const sep = String.raw`\s*[.\/\-,]\s*`
  let m: RegExpExecArray | null

  // 31.05.2027, 31/05/27
  const dmy = new RegExp(String.raw`(?<!\d)(\d{1,2})${sep}(\d{1,2})${sep}(\d{4}|\d{2})(?!\d)`, 'g')
  const taken = new Set<number>()
  while ((m = dmy.exec(text))) {
    push(make(+m[3], +m[2], +m[1]), m.index)
    for (let i = m.index; i < m.index + m[0].length; i++) taken.add(i)
  }
  // 2027-05-31, 2027.05
  const ymd = new RegExp(String.raw`(?<!\d)(20\d{2})${sep}(\d{1,2})(?:${sep}(\d{1,2}))?(?!\d)`, 'g')
  while ((m = ymd.exec(text))) if (!taken.has(m.index)) {
    push(make(+m[1], +m[2], m[3] ? +m[3] : undefined), m.index)
    for (let i = m.index; i < m.index + m[0].length; i++) taken.add(i)
  }
  // 05.2027, 05/27, 05 2027
  const my = new RegExp(String.raw`(?<!\d)(\d{1,2})(?:${sep}|\s+)(\d{4}|\d{2})(?!\d)`, 'g')
  while ((m = my.exec(text))) if (!taken.has(m.index)) push(make(+m[2], +m[1]), m.index)
  // май 2027, MAY 27
  const named = /([a-zа-яё]{3,})\.?\s*(\d{4}|\d{2})(?!\d)/gi
  while ((m = named.exec(text))) {
    const month = MONTHS[m[1].slice(0, 3).toLowerCase()]
    if (month) push(make(+m[2], month), m.index)
  }
  return out
}

export function parseExpiry(text: string): Date | null {
  const found = candidates(text)
  if (!found.length) return null
  // Дата сразу после «годен до / EXP» — почти наверняка срок годности.
  const scored = found.map(c => {
    const before = text.slice(Math.max(0, c.index - 24), c.index)
    const score = (EXPIRY_WORDS.test(before) ? 2 : 0) - (MADE_WORDS.test(before) ? 3 : 0)
    return { ...c, score }
  })
  scored.sort((a, b) => b.score - a.score || b.date.getTime() - a.date.getTime())
  return scored[0].date
}

export function toISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
