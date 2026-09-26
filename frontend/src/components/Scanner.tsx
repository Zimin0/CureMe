import { prepareZXingModule, BarcodeDetector } from 'barcode-detector/ponyfill'
import wasmUrl from 'zxing-wasm/reader/zxing_reader.wasm?url'
import { Camera, Flashlight, ImageUp, SwitchCamera } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'

// wasm-модуль распознавания лежит в нашей же сборке — без внешних CDN и работает офлайн.
prepareZXingModule({
  overrides: { locateFile: (path: string, prefix: string) => (path.endsWith('.wasm') ? wasmUrl : prefix + path) },
})

const FORMATS = ['data_matrix', 'ean_13', 'ean_8', 'upc_a', 'code_128', 'qr_code'] as const
let detector: BarcodeDetector | null = null
function getDetector() {
  detector ??= new BarcodeDetector({ formats: [...FORMATS] })
  return detector
}

/** Распознаёт код на загруженной фотографии (для компьютера без камеры). */
export async function decodeImage(file: File): Promise<string | null> {
  const bitmap = await createImageBitmap(file)
  try {
    const found = await getDetector().detect(bitmap)
    return pickBest(found)
  } finally {
    bitmap.close()
  }
}

function pickBest(found: { format: string; rawValue: string }[]): string | null {
  if (!found.length) return null
  // DataMatrix несёт серийный номер и срок годности — он полезнее обычного штрихкода.
  return (found.find(f => f.format === 'data_matrix') ?? found[0]).rawValue
}

type TorchTrack = MediaStreamTrack & { applyConstraints(c: { advanced: { torch: boolean }[] }): Promise<void> }

export function Scanner({ onCode, paused }: { onCode: (raw: string) => void; paused?: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'starting' | 'live' | 'denied' | 'nocamera'>('idle')
  const [facing, setFacing] = useState<'environment' | 'user'>('environment')
  const [torch, setTorch] = useState(false)
  const [torchSupported, setTorchSupported] = useState(false)
  const [busy, setBusy] = useState(false)
  const [fileError, setFileError] = useState('')

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
  }, [])

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) { setState('nocamera'); return }
    setState('starting')
    stop()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false,
      })
      streamRef.current = stream
      const track = stream.getVideoTracks()[0]
      const caps = (track.getCapabilities?.() ?? {}) as { torch?: boolean }
      setTorchSupported(!!caps.torch)
      setTorch(false)
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
      }
      setState('live')
    } catch (e) {
      const name = (e as DOMException).name
      setState(name === 'NotAllowedError' || name === 'SecurityError' ? 'denied' : 'nocamera')
    }
  }, [facing, stop])

  useEffect(() => { start(); return stop }, [start, stop])

  // Цикл распознавания: несколько кадров в секунду, пока камера включена и не на паузе.
  useEffect(() => {
    if (state !== 'live' || paused) return
    let cancelled = false
    let timer: number
    const tick = async () => {
      const v = videoRef.current
      if (!cancelled && v && v.readyState >= 2) {
        try {
          const code = pickBest(await getDetector().detect(v))
          if (code && !cancelled) {
            navigator.vibrate?.(60)
            onCode(code)
            return
          }
        } catch { /* кадр не распознан — пробуем следующий */ }
      }
      if (!cancelled) timer = window.setTimeout(tick, 180)
    }
    tick()
    return () => { cancelled = true; clearTimeout(timer) }
  }, [state, paused, onCode])

  const toggleTorch = async () => {
    const track = streamRef.current?.getVideoTracks()[0] as TorchTrack | undefined
    if (!track) return
    try { await track.applyConstraints({ advanced: [{ torch: !torch }] }); setTorch(!torch) } catch { setTorchSupported(false) }
  }

  const onFile = async (file?: File) => {
    if (!file) return
    setBusy(true)
    setFileError('')
    try {
      const code = await decodeImage(file)
      if (code) onCode(code)
      else setFileError('На фото не нашлось кода. Снимите код крупнее и при хорошем свете.')
    } catch {
      setFileError('Не удалось открыть изображение')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  return (
    <div className="stack">
      <div className="scanner">
        <video ref={videoRef} playsInline muted />
        {state === 'live' && (
          <>
            <div className="frame"><i /></div>
            {!paused && <div className="laser" />}
            <div className="hint-top">Наведите камеру на квадратный код или штрихкод</div>
          </>
        )}
        {state !== 'live' && (
          <div className="placeholder">
            <div className="stack" style={{ alignItems: 'center' }}>
              <Camera size={40} />
              {state === 'starting' && <p>Включаем камеру…</p>}
              {state === 'denied' && <p>Нет доступа к камере. Разрешите его в настройках браузера или загрузите фото кода.</p>}
              {state === 'nocamera' && <p>Камера недоступна. Загрузите фото кода или введите цифры вручную.</p>}
              {(state === 'denied' || state === 'nocamera') && (
                <button className="btn sm" onClick={start}>Попробовать снова</button>
              )}
            </div>
          </div>
        )}
        <div className="controls">
          {torchSupported && (
            <button className="icon-btn" onClick={toggleTorch} aria-label="Фонарик" style={torch ? { background: '#fff', color: '#000' } : undefined}>
              <Flashlight size={22} />
            </button>
          )}
          <button className="icon-btn" onClick={() => setFacing(f => (f === 'environment' ? 'user' : 'environment'))} aria-label="Сменить камеру">
            <SwitchCamera size={22} />
          </button>
          <button className="icon-btn" onClick={() => fileRef.current?.click()} aria-label="Загрузить фото" disabled={busy}>
            <ImageUp size={22} />
          </button>
        </div>
      </div>
      <input ref={fileRef} type="file" accept="image/*" hidden onChange={e => onFile(e.target.files?.[0])} />
      {fileError && <div className="alert warn">{fileError}</div>}
    </div>
  )
}
