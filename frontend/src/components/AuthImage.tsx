import { useEffect, useState } from 'react'
import { fetchFile } from '../api'

/** Картинка, которую сервер отдаёт только по токену входа (фото документов): обычный <img src> токен не передаст. */
export function AuthImage({ url, alt, className }: { url: string; alt: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let objectUrl = ''
    let alive = true
    setSrc(null)
    setFailed(false)
    fetchFile(url.replace(/^\/api/, ''), 'document.jpg')
      .then(f => { if (alive) { objectUrl = URL.createObjectURL(f); setSrc(objectUrl) } })
      .catch(() => alive && setFailed(true))
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [url])
  if (failed) return <span className={`${className ?? ''} auth-image-failed`} role="img" aria-label={alt}>Фото недоступно</span>
  if (!src) return <span className={`${className ?? ''} auth-image-wait`} aria-hidden="true" />
  return <img className={className} src={src} alt={alt} />
}
