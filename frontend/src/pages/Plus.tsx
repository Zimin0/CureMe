import { Check, Lock, Sparkles } from 'lucide-react'
import { LimitName } from '../api'
import { PageLoader } from '../components/ui'
import { limitWord, planLabel, usePlan } from '../plan'

// Что сравниваем на странице: лимит бесплатной версии → «без ограничений» в Плюсе.
const COMPARE: { name: LimitName; label: string }[] = [
  { name: 'members', label: 'Участников в семье' },
  { name: 'medicines', label: 'Лекарств в аптечке' },
  { name: 'own_families', label: 'Своих аптечек' },
  { name: 'history_days', label: 'История приёма' },
]

/** Страница «Капсулка Плюс»: что даёт подписка, чем отличается от бесплатной версии, тариф этой семьи. */
export function Plus() {
  const { plan, loading } = usePlan()
  if (loading || !plan) return <PageLoader />
  const free = plan.free_limits

  return (
    <div className="page stack" style={{ maxWidth: 720 }}>
      <div className="plus-hero">
        <Sparkles size={34} />
        <div>
          <h1>Капсулка Плюс</h1>
          <p>Одна подписка на всю семью: платит один, пользуются все участники аптечки.</p>
        </div>
      </div>

      <section className="card stack">
        <div className="row between">
          <h2>Ваша семья</h2>
          <span className={`badge ${plan.plus_active ? 'plus' : ''}`}>{planLabel(plan)}</span>
        </div>
        {!plan.billing_enabled && <p className="muted small">Платная версия пока не включена, поэтому все функции Плюса доступны бесплатно.</p>}
        {plan.billing_enabled && !plan.plus_active && (
          <p className="muted small">Оплата появится скоро. Пока Плюс для семьи включает администратор.</p>
        )}
      </section>

      <section className="card flush plus-list">
        <div style={{ padding: '18px 18px 6px' }}><h2>Что входит в Плюс</h2></div>
        {plan.features.map(f => (
          <div key={f.key} className="list-row">
            {f.available ? <Check size={18} /> : <Lock size={18} className="off" />}
            <div className="grow">
              <div style={{ fontWeight: 700 }}>{f.title}</div>
              <div className="small muted">{f.description}</div>
            </div>
          </div>
        ))}
      </section>

      <section className="card">
        <h2 style={{ marginBottom: 8 }}>Бесплатно и в Плюсе</h2>
        <table className="compare">
          <thead><tr><th></th><th>Бесплатно</th><th>Плюс</th></tr></thead>
          <tbody>
            {COMPARE.map(c => (
              <tr key={c.name}>
                <td>{c.label}</td>
                <td>{c.name === 'history_days' ? `${free[c.name]} ${limitWord(c.name, free[c.name])}` : `до ${free[c.name]}`}</td>
                <td className="plus-col">без ограничений</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small" style={{ marginTop: 12 }}>
          Сканирование упаковок, сроки годности, остатки, фото, подбор «Что есть дома от…» и приглашения родных всегда бесплатны.
        </p>
      </section>
    </div>
  )
}
