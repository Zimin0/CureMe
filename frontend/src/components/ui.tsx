import { X } from 'lucide-react'
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react'
import type { Category, Stock } from '../api'
import { STATUS_LABEL } from '../format'

export function Spinner() { return <div className="spinner" aria-label="Загрузка" /> }
export function PageLoader() { return <div className="center"><Spinner /></div> }

export function Empty({ icon, title, text, action }: { icon: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <div className="big">{icon}</div>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
      {action}
    </div>
  )
}

export function StatusBadge({ stock }: { stock: Stock }) {
  return <span className={`badge ${stock.status}`}>{STATUS_LABEL[stock.status]}</span>
}

export function MedIcon({ category, size }: { category: Category | null; size?: number }) {
  const color = category?.color ?? '#687076'
  return (
    <div className="med-icon" style={{ background: `color-mix(in srgb, ${color} 15%, transparent)`, width: size, height: size }}>
      {category?.icon ?? '💊'}
    </div>
  )
}

export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={e => e.target === e.currentTarget && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title}>
        <div className="row between" style={{ marginBottom: 16 }}>
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Закрыть"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  )
}

type Toast = { id: number; text: string; kind: 'ok' | 'error' }
const ToastCtx = createContext<(text: string, kind?: Toast['kind']) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<Toast | null>(null)
  const show = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    const id = Date.now()
    setToast({ id, text, kind })
    setTimeout(() => setToast(t => (t?.id === id ? null : t)), 3200)
  }, [])
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && <div className="toast-wrap"><div className={`toast ${toast.kind}`} role="status">{toast.text}</div></div>}
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)
