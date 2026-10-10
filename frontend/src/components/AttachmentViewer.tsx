import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { IllnessDocument } from '../api'
import { AuthImage } from './AuthImage'
import { Sheet } from './ui'

/** Просмотр вложений записи: фото листаются свайпом, стрелками на экране или клавишами «влево» и «вправо». */
export function AttachmentViewer({ docs, start = 0, onClose }: { docs: IllnessDocument[]; start?: number; onClose: () => void }) {
  const track = useRef<HTMLDivElement>(null)
  const [index, setIndex] = useState(start)

  const go = (i: number) => {
    const el = track.current
    if (!el) return
    const next = Math.max(0, Math.min(docs.length - 1, i))
    el.scrollTo?.({ left: next * el.clientWidth, behavior: 'smooth' })
    setIndex(next)
  }
  useEffect(() => { track.current?.scrollTo?.({ left: start * (track.current?.clientWidth ?? 0) }) }, [start])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') go(index - 1)
      if (e.key === 'ArrowRight') go(index + 1)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  return (
    <Sheet title={`Вложения (${index + 1} из ${docs.length})`} onClose={onClose}>
      <div className="att-wrap">
        <div
          ref={track} className="att-track"
          onScroll={e => { const el = e.currentTarget; setIndex(Math.round(el.scrollLeft / (el.clientWidth || 1))) }}
        >
          {docs.map((d, i) => (
            <div className="att-slide" key={d.id} aria-label={`Фото ${i + 1} из ${docs.length}`}>
              <AuthImage className="photo-full" url={d.url} alt={`Фото документа ${i + 1}`} />
            </div>
          ))}
        </div>
        {docs.length > 1 && (
          <>
            <button type="button" className="icon-btn att-nav prev" onClick={() => go(index - 1)} disabled={index === 0} aria-label="Предыдущее фото"><ChevronLeft size={20} /></button>
            <button type="button" className="icon-btn att-nav next" onClick={() => go(index + 1)} disabled={index === docs.length - 1} aria-label="Следующее фото"><ChevronRight size={20} /></button>
          </>
        )}
      </div>
    </Sheet>
  )
}
