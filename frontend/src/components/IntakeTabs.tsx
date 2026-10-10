import { NavLink } from 'react-router-dom'

/** Вкладки «Расписание», «История» и «Болезни» на странице «Приём»: в нижнем меню телефона для истории нет отдельного пункта. */
export function IntakeTabs() {
  return (
    <nav className="intake-tabs segmented" aria-label="Приём">
      <NavLink to="/schedule" className={({ isActive }) => (isActive ? 'on' : '')}>Расписание</NavLink>
      <NavLink to="/history" className={({ isActive }) => (isActive ? 'on' : '')}>История</NavLink>
      <NavLink to="/illness" className={({ isActive }) => (isActive ? 'on' : '')}>Болезни</NavLink>
    </nav>
  )
}
