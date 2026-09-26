import { Heart, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Medicine } from '../api'
import { daysText, fmtQty, subtitle } from '../format'
import { MedIcon, StatusBadge } from './ui'

export function MedicineCard({ m }: { m: Medicine }) {
  const s = m.stock
  return (
    <Link to={`/medicines/${m.id}`} className="med-card">
      <MedIcon category={m.category} />
      <div className="grow">
        <div className="row" style={{ gap: 6 }}>
          <span className="name ellipsis">{m.name}</span>
          {m.helps_me && <Heart size={15} fill="var(--danger)" color="var(--danger)" aria-label="Помогает мне" />}
          {m.is_favorite && <Star size={15} fill="#f5a623" color="#f5a623" aria-label="В избранном" />}
        </div>
        <div className="meta ellipsis">{subtitle(m) || m.category?.name || 'Без категории'}</div>
        <div className="tags">
          {s.status !== 'ok' && <StatusBadge stock={s} />}
          {s.days_left !== null && s.status !== 'expired' && (
            <span className={`badge ${s.days_left <= 30 ? 'expiring' : ''}`}>{daysText(s.days_left)}</span>
          )}
        </div>
      </div>
      <div className="side">
        <div className="qty">{fmtQty(s.total)}<small>{m.unit}</small></div>
        {s.package_count > 1 && <span className="faint small">{s.package_count} уп.</span>}
      </div>
    </Link>
  )
}
