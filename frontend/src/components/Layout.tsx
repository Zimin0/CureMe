import { FileDown, House, LogOut, Pill, ScanLine, Shield, Stethoscope, Users } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'

const LINKS = [
  { to: '/', label: 'Главная', icon: House, end: true },
  { to: '/medicines', label: 'Аптечка', icon: Pill },
  { to: '/scan', label: 'Сканировать', icon: ScanLine },
  { to: '/find', label: 'Подобрать', icon: Stethoscope },
  { to: '/family', label: 'Семья', icon: Users },
  { to: '/export', label: 'Экспорт', icon: FileDown },
]

export function Layout() {
  const { me, familyId, setFamilyId, signOut } = useAuth()
  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand"><img src="/icon.svg" alt="" />Капсулка</div>
        {LINKS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="side-link">
            <Icon size={20} />{label}
          </NavLink>
        ))}
        {me?.is_admin && (
          <NavLink to="/admin" className="side-link"><Shield size={20} />Админка</NavLink>
        )}
        <div className="spacer" />
        {me && me.families.length > 1 && (
          <label className="family-switch small">
            <span className="muted">Аптечка семьи</span>
            <select value={familyId ?? ''} onChange={e => setFamilyId(Number(e.target.value))}>
              {me.families.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
          </label>
        )}
        <div className="row" style={{ padding: '10px 6px' }}>
          <div className="grow">
            <div style={{ fontWeight: 700 }} className="ellipsis">{me?.name}</div>
            <div className="faint small ellipsis">{me?.email}</div>
          </div>
          <button className="icon-btn" onClick={signOut} title="Выйти" aria-label="Выйти"><LogOut size={18} /></button>
        </div>
      </aside>

      <main className="main"><Outlet /></main>

      <nav className="bottom-nav six" aria-label="Навигация">
        {LINKS.map(({ to, label, icon: Icon, end }) =>
          to === '/scan' ? (
            <NavLink key={to} to={to} className="scan-link" aria-label={label}>
              <span className="scan-fab"><Icon size={26} /></span>
            </NavLink>
          ) : (
            <NavLink key={to} to={to} end={end}>
              <Icon size={22} />{label}
            </NavLink>
          ),
        )}
      </nav>
    </div>
  )
}
