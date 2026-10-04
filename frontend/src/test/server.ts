import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import type { Plan } from '../api'

const FEATURES: Plan['features'] = [
  { key: 'reminders', title: 'Напоминания в Telegram и на почту', description: 'Напомним, когда лекарство заканчивается.', available: true },
  { key: 'full_history', title: 'Вся история приёма', description: 'Бесплатно видны последние 30 дней.', available: true },
  { key: 'export_pdf', title: 'Экспорт в PDF и Excel для врача', description: 'Файл для врача.', available: true },
  { key: 'cabinets', title: 'Несколько своих аптечек', description: 'Бесплатно — одна своя.', available: true },
  { key: 'schedule', title: 'Расписание приёма', description: 'Добавляйте назначения в расписание.', available: true },
  { key: 'shelf_plan', title: 'Где лежит лекарство', description: 'Схема аптечки и метки на ней.', available: true },
  { key: 'search_all', title: 'Поиск по всем аптечкам', description: 'Ищите сразу во всех аптечках семьи.', available: true },
  { key: 'no_limits', title: 'Без лимитов', description: 'Бесплатно — до 4 участников и 60 лекарств.', available: true },
]
const FREE_LIMITS = { members: 4, medicines: 60, own_families: 1, history_days: 30 }

/** Тариф семьи для тестов: по умолчанию платная версия выключена и всё открыто. */
export function planFixture(over: Partial<Plan> = {}): Plan {
  const has = over.has_plus ?? true
  return {
    plan: 'free', plus_until: null, plus_active: false, billing_enabled: false, has_plus: has,
    limits: has ? { members: null, medicines: null, own_families: null, history_days: null } : FREE_LIMITS,
    free_limits: FREE_LIMITS, usage: { members: 1, medicines: 0 },
    features: FEATURES.map(f => ({ ...f, available: has })),
    ...over,
  }
}
const PLAN_OPEN = planFixture()

/**
 * Поддельный бэкенд для компонентных тестов (Mock Service Worker).
 * Тест сам описывает ответы через server.use(http.get('/api/...', ...)).
 * Любой запрос без описанного ответа роняет тест — так не пропустим лишний вызов API.
 */
export const server = setupServer(
  // по умолчанию сайт открыт; тесты закрытого режима подменяют ответ
  http.get('/api/auth/access', () => HttpResponse.json({ closed: false })),
  // по умолчанию платная версия выключена и всё доступно; тесты Плюса подменяют ответ (planFixture из utils)
  http.get('/api/families/:id/plan', () => HttpResponse.json(PLAN_OPEN)),
  // оплата выключена; тесты оплаты подменяют ответ
  http.get('/api/payments/me', () => HttpResponse.json({
    enabled: false, plus_active: false, plus_until: null, auto_renew: false, price_month: null, price_year: null, payments: [],
    can_pay: false, is_owner: true, owner_name: 'Анна',
  })),
)
