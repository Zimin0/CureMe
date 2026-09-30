import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Copy, Download, FileSpreadsheet, FileText, Share2, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError, fetchFile, fetchText, type Family } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { Empty, Spinner, useToast } from '../components/ui'
import { plural } from '../format'
import { PlusLock } from '../plan'

function saveFile(file: File) {
  const url = URL.createObjectURL(file)
  const a = document.createElement('a')
  a.href = url
  a.setAttribute('download', file.name)
  document.body.append(a)
  a.click()
  setTimeout(() => { a.remove(); URL.revokeObjectURL(url) }, 1000)
}
const canShare = (file: File) => typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })
async function shareFile(file: File) {
  try { await navigator.share({ files: [file], title: file.name }) } catch { /* отменили */ }
}

export function Export() {
  const fam = useFamilyPath()
  const { me, familyId } = useAuth()
  const toast = useToast()
  const [inStock, setInStock] = useState(true)
  const { data: text, isLoading, error } = useQuery({
    queryKey: ['export', fam(''), inStock],
    queryFn: () => fetchText(fam(`/export.txt${inStock ? '?in_stock=true' : ''}`)),
  })
  const count = text ? text.split('\n').filter(Boolean).length : 0
  const familyName = me?.families.find(f => f.id === familyId)?.name ?? 'аптечка'
  // Латиница в имени: часть браузеров молча заменяет кириллическое имя blob-файла на «download».
  const filename = `kapsulka-lekarstva-${new Date().toLocaleDateString('sv-SE')}.txt`
  const file = () => new File([text ?? ''], filename, { type: 'text/plain;charset=utf-8' })

  const download = () => saveFile(file())
  const canShareFile = canShare(file())
  const share = () => shareFile(file())

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <Link to="/medicines" className="btn ghost sm" style={{ alignSelf: 'flex-start' }}><ArrowLeft size={16} />Аптечка</Link>
      <div className="page-head">
        <div>
          <h1>Экспорт</h1>
          <p className="sub">Список лекарств для себя и выписка о приёме, которую удобно показать врачу.</p>
        </div>
      </div>

      <DoctorReport />

      <section className="card stack">
        <div>
          <h2>Список лекарств</h2>
          <p className="small muted">Текстовый файл: название и дозировка, по одному на строку.</p>
        </div>
        <div className="segmented" role="tablist">
          <button type="button" role="tab" aria-selected={inStock} className={inStock ? 'on' : ''} onClick={() => setInStock(true)}>Только в наличии</button>
          <button type="button" role="tab" aria-selected={!inStock} className={!inStock ? 'on' : ''} onClick={() => setInStock(false)}>Вся аптечка</button>
        </div>

        {isLoading ? <div className="center" style={{ minHeight: 120 }}><Spinner /></div>
          : error ? <div className="alert error">{(error as Error).message}</div>
          : count === 0 ? <Empty icon="📄" title="Список пуст" text={inStock ? 'Сейчас в наличии ничего нет.' : 'Добавьте лекарства в аптечку.'} />
          : (
            <>
              <div className="row between">
                <span className="small muted">{count} {plural(count, 'лекарство', 'лекарства', 'лекарств')}</span>
                <span className="small faint">{familyName}</span>
              </div>
              <pre className="export-preview">{text}</pre>
              <div className="row wrap">
                <button className="btn primary grow" onClick={download}><Download size={18} />Скачать .txt</button>
                {canShareFile && <button className="btn" onClick={share}><Share2 size={18} />Отправить</button>}
                <button className="btn ghost" onClick={() => navigator.clipboard.writeText(text!).then(() => toast('Список скопирован'))}><Copy size={18} />Копировать</button>
              </div>
            </>
          )}
      </section>
    </div>
  )
}

type Period = '30' | '90' | '365' | 'custom'
const PERIODS: [Period, string][] = [['30', '30 дней'], ['90', '90 дней'], ['365', 'Год'], ['custom', 'Свой']]
const isoDay = (d: Date) => d.toLocaleDateString('sv-SE')
const daysAgo = (n: number) => isoDay(new Date(Date.now() - n * 86_400_000))

/** Выписка для врача: история приёма одного человека за период, в PDF или Excel (Капсулка Плюс). */
function DoctorReport() {
  const fam = useFamilyPath()
  const { me, familyId } = useAuth()
  const toast = useToast()
  const { data: family } = useQuery({ queryKey: ['family', familyId], queryFn: () => api<Family>(fam('')) })
  const [member, setMember] = useState<number | null>(null)
  const [period, setPeriod] = useState<Period>('30')
  const [from, setFrom] = useState(daysAgo(29))
  const [to, setTo] = useState(isoDay(new Date()))
  const [cabinet, setCabinet] = useState(false)
  const [busy, setBusy] = useState<'pdf' | 'xlsx' | null>(null)
  const [ready, setReady] = useState<File | null>(null)

  const who = member ?? me?.id
  const range = period === 'custom' ? { from, to } : { from: daysAgo(Number(period) - 1), to: isoDay(new Date()) }
  const badRange = !range.from || !range.to || range.from > range.to

  const get = async (fmt: 'pdf' | 'xlsx') => {
    const qs = new URLSearchParams({ ...range, tz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow' })
    if (who && who !== me?.id) qs.set('member', String(who))
    if (cabinet) qs.set('cabinet', 'true')
    setBusy(fmt)
    setReady(null)
    try {
      const file = await fetchFile(fam(`/report.${fmt}?${qs}`), `kapsulka-dlya-vracha.${fmt}`)
      saveFile(file)
      if (canShare(file)) setReady(file)
    } catch (e) {
      // 402 — функция Плюса: шторку «доступно в Плюсе» открывает сам api.ts
      if (!(e instanceof ApiError && e.status === 402)) toast((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const members = family?.members ?? []
  return (
    <section className="card stack">
      <div className="row" style={{ gap: 10, alignItems: 'flex-start' }}>
        <Stethoscope size={22} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
        <div>
          <h2 className="row" style={{ gap: 8 }}>Для врача: PDF и Excel<PlusLock feature="export_pdf" /></h2>
          <p className="small muted">Что и когда принималось за период, сводка по каждому лекарству и ваши комментарии к приёму.</p>
        </div>
      </div>

      {members.length > 1 && (
        <label className="field"><span>Чья история</span>
          <select className="input" value={who ?? ''} onChange={e => setMember(Number(e.target.value))}>
            {members.map(m => <option key={m.user_id} value={m.user_id}>{m.user_id === me?.id ? `${m.name} (я)` : m.name}</option>)}
          </select>
          {who !== me?.id && <span className="hint">Комментарии к приёму видит только их автор, поэтому в выписке их не будет.</span>}
        </label>
      )}

      <div className="field"><span>Период</span>
        <div className="segmented" role="tablist">
          {PERIODS.map(([k, label]) => (
            <button key={k} type="button" role="tab" aria-selected={period === k} className={period === k ? 'on' : ''} onClick={() => setPeriod(k)}>{label}</button>
          ))}
        </div>
      </div>
      {period === 'custom' && (
        <div className="row wrap" style={{ gap: 12 }}>
          <label className="field grow"><span>С</span><input className="input" type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} /></label>
          <label className="field grow"><span>По</span><input className="input" type="date" value={to} min={from} onChange={e => setTo(e.target.value)} /></label>
        </div>
      )}

      <label className="check">
        <input type="checkbox" checked={cabinet} onChange={e => setCabinet(e.target.checked)} />
        <span>Добавить, что сейчас есть в аптечке</span>
      </label>

      <div className="row wrap">
        <button className="btn primary grow" disabled={badRange || busy !== null} onClick={() => get('pdf')}>
          {busy === 'pdf' ? <Spinner /> : <FileText size={18} />}PDF
        </button>
        <button className="btn grow" disabled={badRange || busy !== null} onClick={() => get('xlsx')}>
          {busy === 'xlsx' ? <Spinner /> : <FileSpreadsheet size={18} />}Excel
        </button>
        {ready && <button className="btn ghost" onClick={() => shareFile(ready)}><Share2 size={18} />Отправить</button>}
      </div>
      <p className="small faint">Выписка составлена по вашим отметкам в приложении и не является медицинским документом.</p>
    </section>
  )
}
