import { useInfiniteQuery } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, Intake } from '../api'
import { useFamilyPath } from '../auth'
import { IntakeList } from '../components/IntakeList'
import { Empty, PageLoader } from '../components/ui'

const PAGE = 50

export function History() {
  const fam = useFamilyPath()
  const [params, setParams] = useSearchParams()
  const medicine = params.get('medicine') ?? ''
  const mine = params.get('mine') === '1'

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    v ? next.set(k, v) : next.delete(k)
    setParams(next, { replace: true })
  }

  const qs = new URLSearchParams({ limit: String(PAGE) })
  if (medicine) qs.set('medicine_id', medicine)
  if (mine) qs.set('mine', 'true')
  const q = useInfiniteQuery({
    queryKey: ['intakes', fam(''), qs.toString()],
    initialPageParam: '',
    queryFn: ({ pageParam }) => {
      const page = new URLSearchParams(qs)
      if (pageParam) page.set('before', pageParam)
      return api<Intake[]>(fam(`/intakes?${page}`))
    },
    getNextPageParam: last => (last.length === PAGE ? last.at(-1)!.taken_at : undefined),
  })
  const items = q.data?.pages.flat() ?? []
  const medName = medicine ? items.find(i => String(i.medicine_id) === medicine)?.medicine_name : null

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>История приёма</h1>
          <p className="sub">Кто, когда и сколько принял. Нажатия за одну минуту сложены в одну запись.</p>
        </div>
      </div>

      <div className="row wrap" style={{ gap: 10 }}>
        <div className="segmented" style={{ minWidth: 220 }}>
          <button type="button" className={mine ? '' : 'on'} onClick={() => set('mine', '')}>Вся семья</button>
          <button type="button" className={mine ? 'on' : ''} onClick={() => set('mine', '1')}>Только мои</button>
        </div>
        {medicine && (
          <button type="button" className="chip active" onClick={() => set('medicine', '')} aria-label="Показать все лекарства">
            {medName ?? 'Одно лекарство'} <X size={14} />
          </button>
        )}
      </div>

      {q.isLoading ? <PageLoader /> : items.length === 0 ? (
        <div className="card">
          <Empty icon="🗓️" title="Пока пусто"
            text="Нажмите «Принял(а)» на странице лекарства, и приём появится здесь."
            action={<Link className="btn" to="/medicines">К аптечке</Link>} />
        </div>
      ) : (
        <section className="card">
          <IntakeList items={items} showMedicine />
          {q.hasNextPage && (
            <button className="btn ghost block" style={{ marginTop: 12 }} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>
              Показать ещё
            </button>
          )}
        </section>
      )}
    </div>
  )
}
