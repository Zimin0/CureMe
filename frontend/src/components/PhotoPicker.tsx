import { Camera, Image, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { compressImage } from '../image'

/**
 * Выбор фото лекарства. Ничего не загружает сам: отдаёт наверх сжатый Blob
 * (или null, если фото убрали), а сохраняет его форма вместе с лекарством.
 */
export function PhotoPicker({ current, onChange }: { current: string | null; onChange: (b: Blob | null) => void }) {
  const input = useRef<HTMLInputElement>(null)
  // capture открывает сразу камеру телефона; на компьютере браузер его игнорирует и показывает выбор файла
  const camera = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(current)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => () => { if (preview?.startsWith('blob:')) URL.revokeObjectURL(preview) }, [preview])

  const pick = async (file?: File) => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const blob = await compressImage(file)
      setPreview(URL.createObjectURL(blob))
      onChange(blob)
    } catch {
      setError('Не получилось открыть это фото')
    } finally {
      setBusy(false)
      if (input.current) input.current.value = ''
      if (camera.current) camera.current.value = ''
    }
  }

  return (
    <div className="photo-picker">
      <button type="button" className="photo-slot" onClick={() => camera.current?.click()} disabled={busy} aria-label="Выбрать фото">
        {preview ? <img src={preview} alt="Фото лекарства" /> : <Camera size={26} />}
      </button>
      <div className="stack" style={{ gap: 6 }}>
        <button type="button" className="btn sm" onClick={() => camera.current?.click()} disabled={busy}>
          <Camera size={16} />{busy ? 'Обрабатываем…' : preview ? 'Переснять' : 'Сфотографировать'}
        </button>
        <button type="button" className="btn sm ghost" onClick={() => input.current?.click()} disabled={busy}>
          <Image size={16} />Из галереи
        </button>
        {preview && (
          <button type="button" className="btn sm ghost" onClick={() => { setPreview(null); onChange(null) }}><Trash2 size={15} />Убрать</button>
        )}
        {error && <span className="small" style={{ color: 'var(--danger)' }}>{error}</span>}
      </div>
      <input ref={input} type="file" accept="image/*" hidden onChange={e => pick(e.target.files?.[0])} />
      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={e => pick(e.target.files?.[0])} />
    </div>
  )
}
