import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CalendarClock, Heart, History, PackageOpen, Pill, Plus, ScanLine, Stethoscope } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, Medicine, Overview } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { MedicineCard } from '../components/MedicineCard'
import { Empty, MedIcon, PageLoader } from '../components/ui'
import { daysText, fmtQty } from '../format'
import { useMedicineLimitGuard } from '../limits'

function greeting() {
  const h = new Date().getHours()
  return h < 6 ? 'Доброй ночи' : h < 12 ? 'Доброе утро' : h < 18 ? 'Добрый день' : 'Добрый вечер'
}

function AttentionRow({ m, kind }: { m: Medicine; kind: 'expired' | 'expiring' | 'low' }) {
  const s = m.stock
  const text =
    kind === 'expired' ? `Просрочено: ${fmtQty(s.expired_quantity)} ${m.unit}` :
    kind === 'expiring' ? daysText(s.days_left ?? 0) :
    s.total <= 0 ? 'Закончилось' : `Осталось ${fmtQty(s.total)} ${m.unit}`
  return (
    <Link to={`/medicines/${m.id}`} className="list-row">
      <MedIcon category={m.category} size={40} photo={m.photo_url} />
      <div className="grow">
        <div style={{ fontWeight: 700 }} className="ellipsis">{m.name}</div>
        <div className="small muted">{text}</div>
      </div>
      <span className={`badge ${kind === 'low' ? (s.total <= 0 ? 'out' : 'low') : kind}`}>
        {kind === 'expired' ? 'Выбросить' : kind === 'expiring' ? 'Скоро' : 'Купить'}
      </span>
    </Link>
  )
}

export function Home() {
  const { me } = useAuth()
  const fam = useFamilyPath()
  const guard = useMedicineLimitGuard()
  const { data, isLoading } = useQuery({ queryKey: ['overview', fam('')], queryFn: () => api<Overview>(fam('/overview')) })
  if (isLoading || !data) return <PageLoader />

  const attention = data.expired.length + data.expiring.length + data.low.length
  const personal = [...data.helps_me, ...data.favorites.filter(f => !data.helps_me.some(h => h.id === f.id))]

  return (
    <div className="page">
      <section className="hero">
        <img className="hero-logo" src="/icon.svg" alt="Капсулка" />
        <h1>{greeting()}, {me?.name}</h1>
        <p>
          {data.total_medicines === 0
            ? 'Аптечка пока пустая. Отсканируйте код на упаковке, и лекарство добавится за пару секунд.'
            : attention === 0
              ? 'В аптечке всё в порядке: ничего не просрочено и ничего не заканчивается.'
              : `Требуют внимания: ${attention}. Проверьте список ниже.`}
        </p>
        <div className="actions">
          <Link to="/scan" className="btn white"><ScanLine size={18} />Сканировать</Link>
          <Link to="/find" className="btn"><Stethoscope size={18} />Что есть от…</Link>
          <Link to="/medicines/new" className="btn" onClick={guard}><Plus size={18} />Вручную</Link>
          <Link to="/history" className="btn"><History size={18} />История приёма</Link>
        </div>
      </section>

      <div className="stats">
        <Link to="/medicines" className="stat"><span className="label"><Pill size={15} />Лекарств</span><span className="value">{data.total_medicines}</span></Link>
        <Link to="/medicines" className="stat"><span className="label"><PackageOpen size={15} />Упаковок</span><span className="value">{data.total_packages}</span></Link>
        <Link to="/medicines?filter=attention" className={`stat ${data.expiring.length ? 'warning' : ''}`}><span className="label"><CalendarClock size={15} />Скоро истекают</span><span className="value">{data.expiring.length}</span></Link>
        <Link to="/medicines?filter=expired" className={`stat ${data.expired.length ? 'danger' : ''}`}><span className="label"><AlertTriangle size={15} />Просрочено</span><span className="value">{data.expired.length}</span></Link>
      </div>

      <div className="two-col">
        <section>
          <div className="section-title"><h2>Требует внимания</h2>{attention > 0 && <Link to="/medicines?filter=attention">Все</Link>}</div>
          <div className="card flush">
            {attention === 0 ? (
              <Empty icon="✅" title="Всё в порядке" text={`Сроки в пределах ${data.expiring_soon_days} дней и запасы под контролем.`} />
            ) : (
              <>
                {data.expired.map(m => <AttentionRow key={`e${m.id}`} m={m} kind="expired" />)}
                {data.expiring.map(m => <AttentionRow key={`s${m.id}`} m={m} kind="expiring" />)}
                {data.low.map(m => <AttentionRow key={`l${m.id}`} m={m} kind="low" />)}
              </>
            )}
          </div>
        </section>

        <section>
          <div className="section-title"><h2>Мои лекарства</h2>{personal.length > 0 && <Link to="/medicines?filter=helps_me">Все</Link>}</div>
          {personal.length === 0 ? (
            <div className="card">
              <Empty icon={<Heart size={36} color="var(--danger)" />} title="Отметьте, что помогает именно вам"
                text="Нажмите ♥ на карточке лекарства. Эти лекарства будут первыми в подборе по болезни." />
            </div>
          ) : (
            <div className="med-list" style={{ gridTemplateColumns: '1fr' }}>
              {personal.slice(0, 6).map(m => <MedicineCard key={m.id} m={m} hidePlace />)}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
