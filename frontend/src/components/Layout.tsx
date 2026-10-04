import { useEffect } from 'react'
import { CalendarClock, History, House, LogOut, LucideIcon, Pill, ScanLine, Shield, Sparkles, Stethoscope, Users } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../auth'
import { planLabel, usePlan } from '../plan'
import { cabinetLabel, FrozenNotice, PlusEndingBanner } from './PlusEnding'
import { TermsNotice } from './TermsNotice'

// short — подпись в нижней панели на телефоне, если полная не помещается.
const LINKS: { to: string; label: string; short?: string; icon: LucideIcon; end?: boolean }[] = [
  { to: '/', label: 'Главная', icon: House, end: true },
  { to: '/medicines', label: 'Аптечка', icon: Pill },
  { to: '/scan', label: 'Сканировать', icon: ScanLine },
  { to: '/find', label: 'Найти', icon: Stethoscope },
  { to: '/family', label: 'Семья', icon: Users },
  { to: '/schedule', label: 'Расписание', short: 'Приём', icon: CalendarClock },
  { to: '/history', label: 'История приёма', short: 'История', icon: History },
]

export function Layout() {
  const { me, familyId, setFamilyId, signOut } = useAuth()
  const { plan } = usePlan()
  const isPlus = !!me?.plus_active
  // Сиреневая тема у тех, у кого есть Плюс (платный или пробный): класс на body переопределяет цвета в styles.css.
  useEffect(() => {
    document.body.classList.toggle('plus-theme', isPlus)
    return () => document.body.classList.remove('plus-theme')
  }, [isPlus])
  const showUpsell = !!plan && plan.billing_enabled && !plan.plus_active
  return (
    <div className="app">
      <aside className="sidebar">
        {LINKS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className="side-link">
            <Icon size={20} />{label}
          </NavLink>
        ))}
        {!showUpsell && (
          <NavLink to="/plus" className="side-link"><Sparkles size={20} />Плюс</NavLink>
        )}
        {me?.is_admin && (
          <NavLink to="/admin" className="side-link"><Shield size={20} />Админка</NavLink>
        )}
        <div className="spacer" />
        {showUpsell && (
          <NavLink to="/plus" className="btn primary side-plus"><Sparkles size={18} />Подключить Плюс</NavLink>
        )}
        {isPlus && plan?.plus_active && (
          <NavLink to="/plus" className="side-plus-card">
            <b><Sparkles size={16} /> Капсулка Плюс</b>
            <span>{planLabel(plan)}</span>
          </NavLink>
        )}
        {me && me.families.length > 1 && (
          <label className="family-switch small">
            <span className="muted">Аптечка семьи</span>
            <select value={familyId ?? ''} title={me.families.find(f => f.id === familyId)?.name} onChange={e => setFamilyId(Number(e.target.value))}>
              {me.families.map(f => <option key={f.id} value={f.id}>{cabinetLabel(f)}</option>)}
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

      <main className="main">
        <TermsNotice />
        {me?.owner_transfer_waiting && (
          <div className="alert info" role="status" style={{ marginBottom: 14 }}>
            <div className="grow">Вам нужно ответить на предложение о владении семьёй. <Link to="/family">Открыть «Семья»</Link></div>
          </div>
        )}
        <PlusEndingBanner />
        <FrozenNotice />
        <Outlet />
      </main>

      <nav className="bottom-nav seven" aria-label="Навигация">
        {LINKS.map(({ to, label, short, icon: Icon, end }) =>
          to === '/scan' ? (
            <NavLink key={to} to={to} className="scan-link" aria-label={label}>
              <span className="scan-fab"><Icon size={26} /></span>
            </NavLink>
          ) : (
            <NavLink key={to} to={to} end={end} aria-label={label}>
              <Icon size={22} />{short ?? label}
            </NavLink>
          ),
        )}
      </nav>
    </div>
  )
}
