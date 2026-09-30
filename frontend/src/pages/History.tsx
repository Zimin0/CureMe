import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Lock, Search, X } from 'lucide-react'
import { useDeferredValue } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, Family, Intake, OlderHistory } from '../api'
import { useAuth, useFamilyPath } from '../auth'
import { IntakeList } from '../components/IntakeList'
import { Empty, PageLoader } from '../components/ui'

const PAGE = 50

/** Начало дня в часовом поясе пользователя: '2026-09-29' → ISO-время полуночи. */
function dayStart(day: string, plusDays = 0) {
  const [y, m, d] = day.split('-').map(Number)
  return new Date(y, m - 1, d + plusDays).toISOString()
}

export function History() {
  const fam = useFamilyPath()
  const { me, familyId } = useAuth()
  const [params, setParams] = useSearchParams()
  const medicine = params.get('medicine') ?? ''
  const who = params.get('who') ?? ''  // '' — вся семья, 'me' — только мои, иначе id участника
  const text = params.get('q') ?? ''
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const dq = useDeferredValue(text.trim())

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    v ? next.set(k, v) : next.delete(k)
    setParams(next, { replace: true })
  }

  const family = useQuery({ queryKey: ['family', familyId], queryFn: () => api<Family>(fam('')) })
  const others = family.data?.members.filter(m => m.user_id !== me?.id) ?? []

  const qs = new URLSearchParams({ limit: String(PAGE) })
  if (medicine) qs.set('medicine_id', medicine)
  if (who === 'me') qs.set('mine', 'true')
  else if (who) qs.set('user_id', who)
  if (dq) qs.set('q', dq)
  if (from) qs.set('since', dayStart(from))
  if (to) qs.set('until', dayStart(to, 1))  // «по» включительно
  const filtered = !!(medicine || who || dq || from || to)
  const q = useInfiniteQuery({
    queryKey: ['intakes', fam(''), qs.toString()],
    initialPageParam: '',
    queryFn: ({ pageParam }) => {
      const page = new URLSearchParams(qs)
      if (pageParam) page.set('before', pageParam)
      return api<Intake[]>(fam(`/intakes?${page}`))
    },
    getNextPageParam: last => (last.length === PAGE ? last.at(-1)!.taken_at : undefined),
    placeholderData: prev => prev,
  })
  // Без Плюса видны последние 30 дней; более ранние записи скрыты, но не удалены.
  const olderQs = medicine ? `?medicine_id=${medicine}` : ''
  const older = useQuery({
    queryKey: ['intakes-older', fam(''), olderQs],
    queryFn: () => api<OlderHistory>(fam(`/intakes/older${olderQs}`)),
  })
  const items = q.data?.pages.flat() ?? []
  const locked = !q.hasNextPage && !!older.data?.hidden && (
    <div className="plus-note" role="note">
      <Lock size={16} />
      <span>Более ранняя история доступна в Капсулке Плюс. Записи не удалены: они появятся, как только семья подключит Плюс.</span>
    </div>
  )
  const medName = medicine ? items.find(i => String(i.medicine_id) === medicine)?.medicine_name : null

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>История приёма</h1>
          <p className="sub">Кто, когда и сколько принял. Нажатия за одну минуту сложены в одну запись.</p>
        </div>
      </div>

      <label className="search">
        <Search size={18} />
        <input className="input" type="search" placeholder="Лекарство или свой комментарий…" aria-label="Поиск по истории"
          value={text} onChange={e => set('q', e.target.value)} />
      </label>

      <div className="stack" style={{ gap: 10 }}>
        <div className="chips" role="group" aria-label="Кто принимал">
          <button type="button" className={`chip ${who ? '' : 'active'}`} onClick={() => set('who', '')}>Вся семья</button>
          <button type="button" className={`chip ${who === 'me' ? 'active' : ''}`} onClick={() => set('who', 'me')}>Только мои</button>
          {others.map(m => (
            <button key={m.user_id} type="button" className={`chip ${who === String(m.user_id) ? 'active' : ''}`}
              onClick={() => set('who', String(m.user_id))}>{m.name}</button>
          ))}
        </div>
        <div className="row wrap history-dates">
          <label>С <input className="input" type="date" aria-label="С даты" value={from} max={to || undefined} onChange={e => set('from', e.target.value)} /></label>
          <label>по <input className="input" type="date" aria-label="По дату" value={to} min={from || undefined} onChange={e => set('to', e.target.value)} /></label>
          {medicine && (
            <button type="button" className="chip active" onClick={() => set('medicine', '')} aria-label="Показать все лекарства">
              {medName ?? 'Одно лекарство'} <X size={14} />
            </button>
          )}
          {filtered && (
            <button type="button" className="btn ghost sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>Сбросить</button>
          )}
        </div>
      </div>

      {q.isLoading ? <PageLoader /> : items.length === 0 ? (
        <div className="card">
          {filtered ? (
            <Empty icon="🔎" title="Ничего не нашлось" text="Попробуйте изменить поиск или период." />
          ) : (
            <Empty icon="🗓️" title="Пока пусто"
              text="Нажмите «Принял(а)» на странице лекарства, и приём появится здесь."
              action={<Link className="btn" to="/medicines">К аптечке</Link>} />
          )}
          {locked}
        </div>
      ) : (
        <section className="card">
          <IntakeList items={items} showMedicine />
          {q.hasNextPage && (
            <button className="btn ghost block" style={{ marginTop: 12 }} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>
              Показать ещё
            </button>
          )}
          {locked}
        </section>
      )}
    </div>
  )
}
