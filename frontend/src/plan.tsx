import { useQuery } from '@tanstack/react-query'
import { Lock, Sparkles } from 'lucide-react'
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, LimitName, Plan, PlusFeature, setPlusRequiredHandler } from './api'
import { useAuth } from './auth'
import { Sheet } from './components/ui'
import { plural } from './format'

/** Названия функций на случай, когда тариф ещё не загрузился. Совпадают с FEATURES в backend/app/plans.py. */
export const FEATURE_TITLES: Record<PlusFeature, string> = {
  reminders: 'Напоминания в Telegram и на почту',
  full_history: 'Вся история приёма',
  export_pdf: 'Экспорт в PDF и Excel для врача',
  cabinets: 'Несколько своих аптечек',
  no_limits: 'Без лимитов',
}

const LIMIT_WORDS: Record<LimitName, [string, string, string]> = {
  members: ['участник', 'участника', 'участников'],
  medicines: ['лекарство', 'лекарства', 'лекарств'],
  own_families: ['своя аптечка', 'своих аптечки', 'своих аптечек'],
  history_days: ['день истории', 'дня истории', 'дней истории'],
}
export const limitWord = (name: LimitName, n: number) => plural(n, ...LIMIT_WORDS[name])
// После «из N» — родительный падеж: «из 21 лекарства», «из 60 лекарств».
const OF_WORDS: Record<'members' | 'medicines', [string, string]> = {
  members: ['участника', 'участников'],
  medicines: ['лекарства', 'лекарств'],
}
const ofWord = (name: 'members' | 'medicines', n: number) => (n % 10 === 1 && n % 100 !== 11 ? OF_WORDS[name][0] : OF_WORDS[name][1])

/** Тариф открытой семьи. После добавления лекарства или участника: qc.invalidateQueries({ queryKey: ['plan'] }). */
export function usePlan() {
  const { familyId } = useAuth()
  const q = useQuery({
    queryKey: ['plan', familyId],
    queryFn: () => api<Plan>(`/families/${familyId}/plan`),
    enabled: !!familyId,
  })
  const plan = q.data
  // Пока тариф не загрузился, ничего не запираем: окончательно всё равно решает сервер.
  const hasPlus = plan?.has_plus ?? true
  return {
    plan,
    hasPlus,
    loading: q.isLoading,
    available: (feature: PlusFeature) => plan?.features.find(f => f.key === feature)?.available ?? hasPlus,
    limit: (name: LimitName): number | null => plan?.limits[name] ?? null,
    usage: (name: 'members' | 'medicines'): number => plan?.usage[name] ?? 0,
  }
}

const PlusCtx = createContext<(feature: PlusFeature) => void>(() => {})

/** Шторка «доступно в Плюсе». Открывается сама на любой ответ 402 и вручную через usePlusSheet(). */
export function PlusProvider({ children }: { children: ReactNode }) {
  const [feature, setFeature] = useState<PlusFeature | null>(null)
  const open = useCallback((f: PlusFeature) => setFeature(f), [])
  useEffect(() => {
    setPlusRequiredHandler(open)
    return () => setPlusRequiredHandler(() => {})
  }, [open])
  return (
    <PlusCtx.Provider value={open}>
      {children}
      {feature && <PlusSheet feature={feature} onClose={() => setFeature(null)} />}
    </PlusCtx.Provider>
  )
}

export const usePlusSheet = () => useContext(PlusCtx)

/** (feature, action) => выполнить action, если функция доступна, иначе показать шторку. */
export function useRequirePlus() {
  const { available } = usePlan()
  const open = usePlusSheet()
  return (feature: PlusFeature, action: () => void) => (available(feature) ? action() : open(feature))
}

function PlusSheet({ feature, onClose }: { feature: PlusFeature; onClose: () => void }) {
  const { plan } = usePlan()
  const f = plan?.features.find(x => x.key === feature)
  return (
    <Sheet title="Доступно в Капсулке Плюс" onClose={onClose}>
      <div className="stack">
        <div className="plus-feature">
          <Sparkles size={22} />
          <div>
            <b>{f?.title ?? FEATURE_TITLES[feature]}</b>
            {f && <p className="muted small">{f.description}</p>}
          </div>
        </div>
        <p className="muted small">Плюс подключается сразу для всей семьи. Оплата появится скоро, а пока Плюс включает администратор.</p>
        <Link to="/plus" className="btn primary block" onClick={onClose}><Sparkles size={18} />Что даёт Плюс</Link>
      </div>
    </Sheet>
  )
}

/** Замочек рядом с кнопкой платной функции. Если функция доступна, ничего не рисует
 *  (или значок «Плюс» при showBadge, когда у семьи оплачен Плюс). */
export function PlusLock({ feature, showBadge = false }: { feature: PlusFeature; showBadge?: boolean }) {
  const { plan, available } = usePlan()
  const open = usePlusSheet()
  if (available(feature)) {
    return showBadge && plan?.plus_active ? <span className="badge plus"><Sparkles size={12} />Плюс</span> : null
  }
  return (
    <button type="button" className="plus-lock" title="Доступно в Плюсе" aria-label={`Доступно в Плюсе: ${FEATURE_TITLES[feature]}`}
      onClick={e => { e.preventDefault(); e.stopPropagation(); open(feature) }}>
      <Lock size={14} />
    </button>
  )
}

/** «58 из 60 лекарств»: лимит видно заранее, а не ошибкой. Без лимита ничего не рисует. */
export function LimitCounter({ name }: { name: 'members' | 'medicines' }) {
  const { limit, usage } = usePlan()
  const max = limit(name)
  if (max === null) return null
  const used = usage(name)
  return (
    <span className={`limit-counter${used >= max ? ' full' : ''}`}>
      {used} из {max} {ofWord(name, max)}
    </span>
  )
}

/** Короткая подпись тарифа семьи: «Плюс до 12.10.2026», «Бесплатная версия». */
export function planLabel(plan: Plan | undefined): string {
  if (!plan) return ''
  if (plan.plus_active) {
    return plan.plus_until ? `Плюс до ${new Date(plan.plus_until).toLocaleDateString('ru-RU')}` : 'Плюс бессрочно'
  }
  return plan.billing_enabled ? 'Бесплатная версия' : 'Все функции открыты'
}

