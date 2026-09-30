import { useQuery } from '@tanstack/react-query'
import { FileSpreadsheet, FileText, Share2, Stethoscope } from 'lucide-react'
import { useState } from 'react'
import { api, ApiError, fetchFile, type Family } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { canShare, saveFile, shareFile } from '../files'
import { PlusBanner, usePlan, usePlusSheet } from '../plan'
import { Spinner, useToast } from './ui'

type Period = '30' | '90' | '365' | 'custom'
const PERIODS: [Period, string][] = [['30', '30 дней'], ['90', '90 дней'], ['365', 'Год'], ['custom', 'Свой']]
const isoDay = (d: Date) => d.toLocaleDateString('sv-SE')
const daysAgo = (n: number) => isoDay(new Date(Date.now() - n * 86_400_000))

/** Выписка для врача: история приёма одного человека за период, в PDF или Excel (Капсулка Плюс). */
export function DoctorReport() {
  const fam = useFamilyPath()
  const { me, familyId } = useAuth()
  const toast = useToast()
  const { data: family } = useQuery({ queryKey: ['family', familyId], queryFn: () => api<Family>(fam('')) })
  const [member, setMember] = useState<number | null>(null)
  const [period, setPeriod] = useState<Period>('30')
  const [from, setFrom] = useState(daysAgo(29))
  const [to, setTo] = useState(isoDay(new Date()))
  const [busy, setBusy] = useState<'pdf' | 'xlsx' | null>(null)
  const { available } = usePlan()
  const openPlus = usePlusSheet()
  const [ready, setReady] = useState<File | null>(null)

  const who = member ?? me?.id
  const range = period === 'custom' ? { from, to } : { from: daysAgo(Number(period) - 1), to: isoDay(new Date()) }
  const badRange = !range.from || !range.to || range.from > range.to

  const get = async (fmt: 'pdf' | 'xlsx') => {
    const qs = new URLSearchParams({ ...range, tz: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Europe/Moscow' })
    if (who && who !== me?.id) qs.set('member', String(who))
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
          <h2 className="row" style={{ gap: 8 }}>Для врача: PDF и Excel</h2>
          <p className="small muted">Что и когда принималось за период, сводка по каждому лекарству и ваши комментарии к приёму.</p>
        </div>
      </div>

      {!available('export_pdf') && (
        <PlusBanner title="Выписка для врача — в Капсулке Плюс" cta="Узнать про Плюс" label="Доступно в Плюсе: экспорт для врача"
          onClick={() => openPlus('export_pdf')} text="PDF и Excel с историей приёма и сводкой по лекарствам доступны в Капсулке Плюс." />
      )}

      <fieldset className="locked-block" disabled={!available('export_pdf')}>
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
      </fieldset>
    </section>
  )
}
