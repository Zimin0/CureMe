import { Heart, Star } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { Medicine } from '../api'
import { useAuth } from '../auth'
import { daysText, fmtQty, subtitle } from '../format'
import { MiniPlace } from './ShelfMap'
import { MedIcon, StatusBadge } from './ui'

/** showCabinet — в поиске по всем аптечкам: подписываем, из какой аптечка карточка, и по клику открываем её. */
export function MedicineCard({ m, showCabinet = false, hidePlace = false }: { m: Medicine; showCabinet?: boolean; hidePlace?: boolean }) {
  return showCabinet ? <CabinetCard m={m} /> : <Card m={m} hidePlace={hidePlace} />
}

function CabinetCard({ m }: { m: Medicine }) {
  const { familyId, setFamilyId } = useAuth()
  return <Card m={m} cabinet onOpen={() => { if (m.family_id && m.family_id !== familyId) setFamilyId(m.family_id) }} />
}

/** Один тег за раз: просрочено, потом закончилось, потом дни до срока, потом «заканчивается». */
function CardTag({ m }: { m: Medicine }) {
  const s = m.stock
  if (s.status === 'expired') return <span className="badge expired">Истёк срок годности</span>
  if (s.status === 'out') return <span className="badge out">Закончилось</span>
  if (s.days_left !== null) return <span className={`badge ${s.days_left <= 30 ? 'expiring' : ''}`}>{daysText(s.days_left)}</span>
  if (s.status === 'low') return <StatusBadge stock={s} />
  return null
}

function Card({ m, cabinet = false, hidePlace = false, onOpen }: { m: Medicine; cabinet?: boolean; hidePlace?: boolean; onOpen?: () => void }) {
  const s = m.stock
  return (
    <Link to={`/medicines/${m.id}`} className="med-card" onClick={onOpen}>
      <MedIcon category={m.category} photo={m.photo_url} />
      <div className="grow">
        <div className="row" style={{ gap: 6 }}>
          <span className="name ellipsis">{m.name}</span>
          {m.helps_me && <Heart size={15} fill="var(--danger)" color="var(--danger)" aria-label="Помогает мне" />}
          {m.is_favorite && <Star size={15} fill="#f5a623" color="#f5a623" aria-label="В избранном" />}
        </div>
        <div className="meta ellipsis">{subtitle(m) || m.categories.map(c => c.name).join(', ') || 'Без категории'}</div>
        <div className="tags">
          {cabinet && m.family_name && <span className="badge accent">{m.family_name}</span>}
          <CardTag m={m} />
        </div>
        {!cabinet && !hidePlace && <MiniPlace m={m} />}
      </div>
      <div className="side">
        <div className="qty">{fmtQty(s.total)}<small>{m.unit}</small></div>
        {s.package_count > 1 && <span className="faint small">{s.package_count} уп.</span>}
      </div>
    </Link>
  )
}
