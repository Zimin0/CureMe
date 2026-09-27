import { Camera, Type } from 'lucide-react'
import { useRef, useState } from 'react'
import { parseExpiry, toISO } from '../expiry'
import { fmtDate } from '../format'
import { recognizeText } from '../ocr'

const isoToDots = (iso: string) => iso.split('-').reverse().join('.')

/** Что человек набрал в поле срока. Восемь цифр подряд без точек — ДДММГГГГ (на iPhone в цифровой клавиатуре точки нет). */
function parseTyped(t: string) {
  const s = t.trim()
  const eight = /^(\d{2})(\d{2})(\d{4})$/.exec(s)
  return parseExpiry(eight ? `${eight[1]}.${eight[2]}.${eight[3]}` : s)
}

/**
 * Поле «Годен до» с двумя подсказками: сфотографировать срок на упаковке
 * или вписать его как написано («05.2027», «EXP 05/27», «май 2027»).
 */
export function ExpiryInput({ value, onChange, hint }: { value: string | null; onChange: (iso: string | null) => void; hint?: string }) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [mode, setMode] = useState<'none' | 'text' | 'photo'>('none')
  const [text, setText] = useState('')
  const [progress, setProgress] = useState<number | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [recognized, setRecognized] = useState('')
  const [note, setNote] = useState<{ kind: 'ok' | 'warn'; text: string } | null>(null)

  const apply = (source: string, from: 'text' | 'photo') => {
    const d = parseExpiry(source)
    if (d) {
      onChange(toISO(d))
      setNote({ kind: 'ok', text: `Годен до ${fmtDate(toISO(d))}${from === 'photo' ? ' — проверьте, что распознано верно' : ''}` })
    } else {
      setNote({ kind: 'warn', text: from === 'photo'
        ? 'Дату на фото не нашли. Снимите крупнее только строку со сроком или впишите её текстом.'
        : 'Не понял дату. Напишите, например, 05.2027 или 31.05.2027.' })
    }
    return d
  }

  // Главное поле — обычный текст с цифровой клавиатурой. Раньше был <input type="date">,
  // а он на части телефонов (и в установленном приложении) не открывает ни клавиатуру, ни календарь.
  const [typed, setTyped] = useState<string | null>(null)
  const onTyped = (t: string) => {
    setTyped(t)
    if (!t.trim()) { onChange(null); setNote(null); return }
    const d = parseTyped(t)
    if (d) { onChange(toISO(d)); setNote(null) }
    else setNote(t.replace(/\D/g, '').length >= 4 ? { kind: 'warn', text: 'Не понял дату. Например: 05.2027, 31.05.2027 или 092027.' } : null)
  }

  const onPhoto = async (file?: File) => {
    if (!file) return
    setMode('photo')
    setNote(null)
    setRecognized('')
    setPreview(URL.createObjectURL(file))
    setProgress(0)
    try {
      const t = await recognizeText(file, setProgress, text => !!parseExpiry(text))
      setRecognized(t.trim())
      if (!apply(t, 'photo')) { setText(''); }
    } catch {
      setNote({ kind: 'warn', text: 'Не удалось распознать фото. Впишите срок текстом.' })
    } finally {
      setProgress(null)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="field">
      <span>Годен до</span>
      <input className="input" type="text" inputMode="decimal" autoComplete="off" aria-label="Годен до" placeholder="ММ.ГГГГ или ДД.ММ.ГГГГ"
        value={typed ?? (value ? isoToDots(value) : '')}
        onChange={e => onTyped(e.target.value)} onBlur={() => { if (typed !== null && (!typed.trim() || parseTyped(typed))) setTyped(null) }} />
      <div className="row wrap" style={{ gap: 8 }}>
        <button type="button" className="chip" onClick={() => fileRef.current?.click()} disabled={progress !== null}>
          <Camera size={15} />Сфотографировать срок
        </button>
        <button type="button" className={`chip ${mode === 'text' ? 'active' : ''}`} onClick={() => setMode(mode === 'text' ? 'none' : 'text')}>
          <Type size={15} />Ввести текстом
        </button>
      </div>
      <input ref={fileRef} type="file" accept="image/*" capture="environment" hidden onChange={e => onPhoto(e.target.files?.[0])} />

      {mode === 'text' && (
        <input className="input" autoFocus placeholder="Как на упаковке: 05.2027, EXP 05/27, май 2027" value={text}
          onChange={e => { setText(e.target.value); if (e.target.value.trim().length >= 4) apply(e.target.value, 'text'); else setNote(null) }} />
      )}

      {mode === 'photo' && preview && (
        <div className="row" style={{ alignItems: 'flex-start' }}>
          <img src={preview} alt="Фото срока годности" style={{ width: 88, height: 66, objectFit: 'cover', borderRadius: 10, flexShrink: 0 }} />
          <div className="grow small muted" style={{ whiteSpace: 'pre-wrap', maxHeight: 66, overflow: 'hidden' }}>
            {progress !== null ? `Распознаём… ${Math.round(progress * 100)}%` : recognized ? `Распознано: ${recognized}` : ''}
          </div>
        </div>
      )}

      {note && <div className={`alert ${note.kind === 'ok' ? 'ok' : 'warn'} small`}>{note.text}</div>}
      {!note && hint && <span className="hint">{hint}</span>}
    </div>
  )
}
