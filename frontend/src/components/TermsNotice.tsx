import { Info, X } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { NEW_TERMS_DATE, NEW_TERMS_FROM } from '../legal'

const KEY = 'cureme.terms-notice.2026-10-13'

function seen(): boolean {
  try { return localStorage.getItem(KEY) === '1' } catch { return false }
}

/**
 * Предупреждение об изменении Пользовательского соглашения (п. 11.3: существенные изменения доводятся до
 * пользователей через интерфейс). Показывается до вступления новой редакции в силу, пока человек не нажмёт «Понятно».
 */
export function TermsNotice({ now = new Date() }: { now?: Date }) {
  const [hidden, setHidden] = useState(seen)
  if (hidden || now >= new Date(NEW_TERMS_FROM)) return null
  const close = () => {
    try { localStorage.setItem(KEY, '1') } catch { /* ничего */ }
    setHidden(true)
  }
  return (
    <div className="alert info" role="status" style={{ marginBottom: 14 }}>
      <Info size={18} style={{ flex: 'none', marginTop: 2 }} />
      <div className="grow">
        С {NEW_TERMS_DATE} вступает в силу новая редакция <Link to="/terms">Пользовательского соглашения</Link>:
        тариф Плюс действует на всю семью, в бесплатной семье до 3 человек. Если у вас в семье уже больше, ничего не изменится.
      </div>
      <button className="icon-btn" onClick={close} aria-label="Понятно, скрыть" title="Понятно"><X size={18} /></button>
    </div>
  )
}
