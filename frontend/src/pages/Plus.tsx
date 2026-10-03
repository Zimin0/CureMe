import { useQuery } from '@tanstack/react-query'
import { Check, Lock, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api, LimitName } from '../api'
import { PayBox, usePayStatus } from '../components/PayBox'
import { PayTerms } from '../components/PayTerms'
import { SellerInfo } from '../components/SellerInfo'
import { PageLoader } from '../components/ui'
import { limitWord, planLabel, PRICE_NOTE, priceText, usePlan } from '../plan'

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
  const pay = usePayStatus()
  if (loading || !plan) return <PageLoader />
  const free = plan.free_limits

  return (
    <div className="page stack" style={{ maxWidth: 720 }}>
      <div className="plus-hero">
        <Sparkles size={34} />
        <div>
          <h1>Капсулка Плюс</h1>
          <p>Одна подписка на аккаунт владельца: платит один, Плюс действует на все его аптечки, и пользуются все их участники. Функции Плюса (например, напоминания) в аптечке работают по тарифу её главного владельца.</p>
        </div>
      </div>

      <section className="card stack">
        <div className="row between">
          <h2>Ваша семья</h2>
          <span className={`badge ${plan.plus_active ? 'plus' : ''}`}>{planLabel(plan)}</span>
        </div>
        {priceText(plan) && (
          <>
            <p>Стоимость Плюса: <b>{priceText(plan)}</b>.</p>
            <p className="muted small">{PRICE_NOTE}</p>
          </>
        )}
        {!plan.billing_enabled && <p className="muted small">Платная версия пока не включена, поэтому все функции Плюса доступны бесплатно.</p>}
        {plan.billing_enabled && !plan.plus_active && !pay.data?.enabled && (
          <p className="muted small">Оплата появится скоро. Пока Плюс включает администратор.</p>
        )}
      </section>

      <PayBox />

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

      <PayTerms />
      <SellerInfo />
    </div>
  )
}

type Access = { billing_enabled?: boolean; listed_price_month?: number | null; listed_price_year?: number | null }

// Лимиты бесплатной версии и функции Плюса для гостей (вошедшие видят те же данные с сервера, см. backend/app/plans.py).
const GUEST_FREE: { label: string; free: string }[] = [
  { label: 'Участников в семье', free: 'до 4' },
  { label: 'Лекарств в аптечке', free: 'до 60' },
  { label: 'Своих аптечек', free: 'до 1' },
  { label: 'История приёма', free: '30 дней' },
]
const GUEST_FEATURES = [
  ['Расписание приёма', 'Назначения врача по часам и дням, отметка приёма в один тап.'],
  ['Напоминания на почту', 'Письмо, когда лекарство заканчивается или подходит срок годности.'],
  ['Вся история приёма', 'Без ограничения в 30 дней.'],
  ['Экспорт в PDF и Excel для врача', 'Список лекарств и история, чтобы показать на приёме.'],
  ['Несколько своих аптечек', 'До пяти: дача, машина, родные.'],
  ['Без лимитов бесплатной версии', 'Больше участников и лекарств в аптечке.'],
]

/** Публичная страница тарифа для гостей: цена, функции, условия оплаты, реквизиты. Открыта без входа (нужна и ЮKassa при проверке сайта). */
export function PlusPublic() {
  const access = useQuery({ queryKey: ['access'], queryFn: () => api<Access>('/auth/access'), staleTime: 60_000 })
  if (access.isLoading) return <PageLoader />
  const m = access.data?.listed_price_month, y = access.data?.listed_price_year
  const rub = (n: number) => `${n.toLocaleString('ru-RU')} ₽`
  const price = [m && `${rub(m)} в месяц`, y && `${rub(y)} в год`].filter(Boolean).join(' или ')

  return (
    <div className="page stack" style={{ maxWidth: 720, margin: '0 auto', padding: '16px' }}>
      <div className="plus-hero">
        <Sparkles size={34} />
        <div>
          <h1>Капсулка Плюс</h1>
          <p>Подписка для домашней аптечки: одна на аккаунт владельца, действует на все его аптечки и всех их участников.</p>
        </div>
      </div>

      <section className="card stack">
        <h2>Стоимость</h2>
        {price ? <p><b>{price}</b> за аккаунт.</p> : <p>Стоимость будет указана здесь до открытия оплаты.</p>}
        <p className="muted small">
          {access.data?.billing_enabled
            ? 'Оплата проходит на странице ЮKassa после оформления подписки в аккаунте.'
            : 'Оплата пока недоступна: цена указана для сведения и не является публичной офертой. Все функции сейчас открыты бесплатно.'}
        </p>
      </section>

      <section className="card flush plus-list">
        <div style={{ padding: '18px 18px 6px' }}><h2>Что входит в Плюс</h2></div>
        {GUEST_FEATURES.map(([title, text]) => (
          <div key={title} className="list-row">
            <Check size={18} />
            <div className="grow"><div style={{ fontWeight: 700 }}>{title}</div><div className="small muted">{text}</div></div>
          </div>
        ))}
      </section>

      <section className="card">
        <h2 style={{ marginBottom: 8 }}>Бесплатно и в Плюсе</h2>
        <table className="compare">
          <thead><tr><th></th><th>Бесплатно</th><th>Плюс</th></tr></thead>
          <tbody>
            {GUEST_FREE.map(r => <tr key={r.label}><td>{r.label}</td><td>{r.free}</td><td className="plus-col">без ограничений</td></tr>)}
          </tbody>
        </table>
        <p className="muted small" style={{ marginTop: 12 }}>
          Сканирование упаковок, сроки годности, остатки, фото, подбор «Что есть дома от…» и приглашения родных всегда бесплатны.
        </p>
      </section>

      <PayTerms />
      <SellerInfo />

      <Link to="/register" className="btn primary block">Попробовать бесплатно</Link>
    </div>
  )
}
