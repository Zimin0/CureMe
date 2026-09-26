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
// Второй ряд — как английская модель OCR читает кириллицу: «Годен до» → «ropeH ao», «[oper ao», «fopeH no».
const EXPIRY_WORDS = /(годен|годн|срок|exp|use\s*by|best\s*before|до\b|g[o0]den|[rfгт[(|]o[pрд]e[hнnrs]|rope|fope|\b[ab]o:)/i
const MADE_WORDS = /(изг|дата\s*пр|mfg|mfd|manuf|произв|[mn]po[wuи]|u3r|изr)/i
const LETTER_OR_DIGIT = String.raw`[\dA-Za-zА-Яа-яЁё]`

interface Candidate { date: Date; index: number; end: number; weak?: boolean }

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
  const push = (d: Date | null, index: number, len: number, weak = false) => { if (d) out.push({ date: d, index, end: index + len, weak }) }
  const sep = String.raw`\s*[.\/\-,]\s*`
  let m: RegExpExecArray | null

  // 31.05.2027, 31/05/27
  const dmy = new RegExp(String.raw`(?<!\d)(\d{1,2})${sep}(\d{1,2})${sep}(\d{4}|\d{2})(?!\d)`, 'g')
  const taken = new Set<number>()
  while ((m = dmy.exec(text))) {
    // OCR часто путает 3 и 5, 8 и 6 в дне: «51.01.2028». Месяц и год при этом верные — берём конец месяца.
    push(make(+m[3], +m[2], +m[1]) ?? (m[3].length === 4 ? make(+m[3], +m[2]) : null), m.index, m[0].length)
    for (let i = m.index; i < m.index + m[0].length; i++) taken.add(i)
  }
  // 2027-05-31, 2027.05
  const ymd = new RegExp(String.raw`(?<!\d)(20\d{2})${sep}(\d{1,2})(?:${sep}(\d{1,2}))?(?!\d)`, 'g')
  while ((m = ymd.exec(text))) if (!taken.has(m.index)) {
    push(make(+m[1], +m[2], m[3] ? +m[3] : undefined), m.index, m[0].length)
    for (let i = m.index; i < m.index + m[0].length; i++) taken.add(i)
  }
  // 05.2027, 05/27, 05 2027
  const my = new RegExp(String.raw`(?<!\d)(\d{1,2})(?:${sep}|\s+)(\d{4}|\d{2})(?!\d)`, 'g')
  while ((m = my.exec(text))) if (!taken.has(m.index)) {
    push(make(+m[2], +m[1]), m.index, m[0].length)
    for (let i = m.index; i < m.index + m[0].length; i++) taken.add(i)
  }
  // «0730» без разделителя — так печатают многие производители (ММГГ). Легко спутать с серией,
  // поэтому только отдельное слово из 4 цифр с реальным месяцем и годом 2020–2045.
  const mmyy = new RegExp(String.raw`(?<!${LETTER_OR_DIGIT})(0[1-9]|1[0-2])([2-4]\d)(?!${LETTER_OR_DIGIT})`, 'g')
  while ((m = mmyy.exec(text))) if (!taken.has(m.index)) push(make(+m[2], +m[1]), m.index, 4, true)
  // май 2027, MAY 27
  const named = /([a-zа-яё]{3,})\.?\s*(\d{4}|\d{2})(?!\d)/gi
  while ((m = named.exec(text))) {
    const month = MONTHS[m[1].slice(0, 3).toLowerCase()]
    if (month) push(make(+m[2], month), m.index, m[0].length)
  }
  return out
}

export function parseExpiry(text: string): Date | null {
  const fixed = fixDigits(text)
  const now = new Date()
  const min = new Date(now.getFullYear() - 10, 0, 1)
  const max = new Date(now.getFullYear() + 10, 11, 31)
  // Срок годности лекарств не бывает дальше 10 лет: так отсекаем серии, похожие на даты.
  const found = candidates(text).filter(c => c.date >= min && c.date <= max).sort((a, b) => a.index - b.index)
  if (!found.length) return null
  const scored = found.map((c, i) => {
    // Смотрим только на текст между предыдущей датой и этой, чтобы «Произв.» не цеплялось к соседней строке.
    const from = Math.max(i ? found[i - 1].end : 0, c.index - 24)
    const before = fixed.slice(from, c.index)
    const score = (EXPIRY_WORDS.test(before) ? 2 : 0) - (MADE_WORDS.test(before) ? 3 : 0)
    return { ...c, score }
  })
  // Дата сразу после «годен до / EXP» — почти наверняка срок годности; иначе полная дата важнее «ММГГ», затем самая поздняя.
  scored.sort((a, b) => b.score - a.score || Number(!!a.weak) - Number(!!b.weak) || b.date.getTime() - a.date.getTime())
  return scored[0].date
}

export function toISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
