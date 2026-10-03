// Типы повторяют схемы бэкенда (backend/app/schemas.py).
export type Role = 'owner' | 'member'
export type StockStatus = 'ok' | 'low' | 'out' | 'expiring' | 'expired'

/** active — аптечка работает; frozen — после окончания Плюса: смотреть и выгружать можно, менять нельзя (R14). */
export type CabinetStatus = 'active' | 'frozen'
export interface FamilyBrief { id: number; name: string; role: Role; status?: CabinetStatus }
/** Плюс семьи заканчивается (ending) или закончился и идёт срок выбора состава (ended, R13). date: конец Плюса или последний день выбора. */
export interface PlusEnding { state: 'ending' | 'ended'; date: string; is_owner: boolean; people_limit: number }
export interface Me { id: number; email: string; name: string; is_admin: boolean; consent_needed?: boolean; access_blocked?: boolean; email_verified?: boolean; verification_needed?: boolean; families: FamilyBrief[]; owner_transfer_waiting?: boolean; own_families_left?: number | null; plus_active?: boolean; plus_ending?: PlusEnding | null; next_change_at?: string | null }
/** Ответ переноса лекарств между аптечками и разделения аптечки (R17, R18). */
export interface MoveResult { moved: number; merged: number; to_family_id: number }
export interface Member { user_id: number; name: string; email: string; role: Role; joined_at: string }
/** Незавершённая передача владения (R23). offer: владелец предлагает участнику; request: участник просит «Хочу оплачивать». */
export interface OwnerTransfer { kind: 'offer' | 'request'; from_user_id: number | null; from_name: string; to_user_id: number | null; to_name: string; expires_at: string; can_answer: boolean; can_withdraw: boolean }
export interface Family { id: number; name: string; status?: CabinetStatus; invite_code: string | null; invite_expires_at?: string | null; role: Role; members: Member[]; owner_transfer?: OwnerTransfer | null; next_transfer_at?: string | null }
/** Публичные сведения о приглашении. full — в бесплатной семье уже предел участников, вступить нельзя. */
export interface InviteInfo { family_name: string; owner_name: string; full: boolean }
export interface Category { id: number; name: string; icon: string; color: string; medicine_count: number }

export interface AdminStats { users: number; admins: number; families: number; medicines: number; categories: number }
export interface AdminUser { id: number; email: string; name: string; is_admin: boolean; email_verified: boolean; created_at: string; families: FamilyBrief[]; plan: PlanName; plus_until: string | null; plus_active: boolean; auto_renew?: boolean; household_id?: number | null; is_owner?: boolean }
export interface AdminFamily { id: number; name: string; created_at: string; medicine_count: number; members: Member[]; plan: PlanName; plus_until: string | null; plus_active: boolean; owner_id?: number | null; owner_name?: string | null }

// --- тарифы: backend/app/plans.py ---
export type PlanName = 'free' | 'plus'
/** Функции Плюса. Ключи совпадают с FEATURES на бэкенде. */
export type PlusFeature = 'reminders' | 'full_history' | 'export_pdf' | 'cabinets' | 'schedule' | 'search_all' | 'no_limits'
export type LimitName = 'members' | 'medicines' | 'own_families' | 'history_days'
export interface PlanFeature { key: PlusFeature; title: string; description: string; available: boolean }
export interface Plan {
  plan: PlanName
  plus_until: string | null
  plus_active: boolean       // Плюс оплачен и не истёк
  billing_enabled: boolean   // платная версия включена администратором
  price_month?: number | null  // стоимость Плюса для аккаунта, ₽ (настраивает админ); null — не показывать
  price_year?: number | null
  owner_name?: string | null  // чей Плюс: владелец семьи
  has_plus: boolean          // семье доступно всё из Плюса
  limits: Record<LimitName, number | null>  // null — без ограничений
  free_limits: Record<LimitName, number>
  usage: { members: number; medicines: number }
  features: PlanFeature[]
}

export interface Stock {
  total: number
  expired_quantity: number
  package_count: number
  nearest_expiry: string | null
  days_left: number | null
  status: StockStatus
}

export interface Package {
  id: number
  quantity: number
  expiry_date: string | null
  opened_at: string | null
  serial: string | null
  batch: string | null
  location: string | null
  added_at: string
  expired: boolean
  days_left: number | null
}

export interface MedicineFields {
  name: string
  category_ids: number[]  // до трёх, первая — основная
  form: string | null
  dosage: string | null
  active_ingredient: string | null
  manufacturer: string | null
  indications: string
  contraindications: string
  notes: string
  unit: string
  min_quantity: number | null
  blister_size: number | null
  gtin: string | null
}

export interface Medicine extends MedicineFields {
  id: number
  family_id?: number | null    // только в поиске по всем аптечкам (Плюс)
  family_name?: string | null
  categories: Category[]
  category: Category | null  // основная категория
  stock: Stock
  is_favorite: boolean
  helps_me: boolean
  personal_note: string
  helps_members: string[]
  photo_url: string | null
  created_at: string
  updated_at: string
}

/** Настройки напоминаний «скоро закончится» и «истекает срок» (backend: routers/notifications.py). */
export interface NotificationPrefs {
  available: boolean          // есть семья с Плюсом (или платная версия выключена)
  email: string
  email_possible: boolean     // на сайте настроена почта, адрес подтверждён
  telegram_possible: boolean  // на сайте настроен Telegram-бот
  telegram_bot: string | null
  email_enabled: boolean
  telegram_enabled: boolean
  telegram_connected: boolean
  telegram_name: string | null
  notify_low: boolean
  notify_expiry: boolean
  expiry_days: number
}

// --- расписание приёма: backend/app/routers/schedule.py ---
export interface ScheduleSlot { id: number; weekday: number; minute: number }  // weekday 0 — понедельник; minute — от полуночи по Москве
export interface Schedule {
  id: number
  medicine_id: number | null  // null — лекарство удалили из аптечки
  medicine_name: string
  unit: string
  amount: number
  start_date: string
  end_date: string | null
  every_weeks: number
  slots: ScheduleSlot[]
}
export interface Occurrence {
  schedule_id: number
  slot_id: number
  medicine_id: number | null
  medicine_name: string
  unit: string
  amount: number
  date: string
  minute: number
  taken: boolean
  taken_at: string | null
}

// --- уведомления по расписанию: backend/app/routers/schedule_notify.py ---
export type TrustedStatus = 'pending' | 'confirmed' | 'declined' | 'revoked'
export interface Trusted { name: string; email: string; status: TrustedStatus; confirmed_at: string | null }
export interface SchedulePrefs {
  available: boolean        // есть семья с Плюсом (или платная версия выключена)
  email: string
  email_possible: boolean   // на сайте настроена почта, адрес подтверждён
  enabled: boolean
  lead_minutes: number      // напомнить за сколько минут до приёма
  repeat_minutes: number    // напомнить снова через сколько минут после приёма, если он не отмечен
  escalate_enabled: boolean
  escalate_minutes: number  // письмо доверенному: через сколько минут после повторного напоминания
  share_medicine_name: boolean
  escalate_consent_at: string | null  // когда разрешено сообщать доверенному (null — не разрешено)
  escalate_consent_version?: string | null
  trusted: Trusted | null
}

export interface MedicineDetail extends Medicine { packages: Package[] }

/** Запись в истории приёма. Нажатия «Принял» за одну минуту уже сложены в одну запись. */
export interface Intake {
  id: number
  medicine_id: number | null  // null — лекарство удалили из аптечки
  medicine_name: string
  unit: string
  user_id: number
  user_name: string
  mine: boolean
  amount: number
  comment: string  // видно только автору
  taken_at: string
  last_at: string
}

/** Сколько записей истории скрыто без Плюса (history_since: null — видна вся история). */
export interface OlderHistory { history_since: string | null; hidden: number }

export interface PackageInput {
  quantity: number
  expiry_date?: string | null
  opened_at?: string | null
  serial?: string | null
  batch?: string | null
  location?: string | null
}

export interface Overview {
  total_medicines: number
  total_packages: number
  expired: Medicine[]
  expiring: Medicine[]
  low: Medicine[]
  favorites: Medicine[]
  helps_me: Medicine[]
  expiring_soon_days: number
}

export interface Suggestion { medicine: Medicine; score: number; reasons: string[]; warnings: string[] }
export interface SuggestResult { query: string; results: Suggestion[]; disclaimer: string }

export interface ParsedCode {
  kind: string
  raw: string
  gtin: string | null
  serial: string | null
  batch: string | null
  expiry: string | null
}
export interface ProductInfo {
  gtin: string
  name: string
  title: string | null
  form: string | null
  dosage: string | null
  active_ingredient: string | null
  manufacturer: string | null
  unit: string | null
  pack_size: number | null
  blister_size: number | null
  source: 'user' | 'internet' | 'openfoodfacts'
}
export interface ScanResult {
  parsed: ParsedCode
  display_code: string | null
  medicine: Medicine | null
  product: ProductInfo | null
  duplicate_package: boolean
}

const TOKEN_KEY = 'cureme.token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(token: string | null) {
  try { token ? localStorage.setItem(TOKEN_KEY, token) : localStorage.removeItem(TOKEN_KEY) } catch { /* приватный режим */ }
}

export class ApiError extends Error {
  /** plusFeature — какая функция Плюса нужна (ответ 402 с заголовком X-Plus-Feature). */
  constructor(public status: number, message: string, public plusFeature: PlusFeature | null = null) { super(message) }
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn }
// Ответ 402: функция доступна только в Плюсе. PlusProvider открывает шторку.
let onPlusRequired: (feature: PlusFeature) => void = () => {}
export function setPlusRequiredHandler(fn: (feature: PlusFeature) => void) { onPlusRequired = fn }

function plusFeatureOf(res: Response): PlusFeature | null {
  if (res.status !== 402) return null
  const feature = (res.headers.get('X-Plus-Feature') ?? 'no_limits') as PlusFeature
  onPlusRequired(feature)
  return feature
}

export async function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method: options.method ?? (options.body !== undefined ? 'POST' : 'GET'),
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch {
    throw new ApiError(0, 'Нет связи с сервером. Проверьте интернет.')
  }
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    if (res.status === 401 && token) onUnauthorized()
    const detail = data?.detail
    // Наши собственные проверки (например, «Пароль слишком длинный») приходят как «Value error, …»
    const own = Array.isArray(detail) && typeof detail[0]?.msg === 'string' && detail[0].msg.startsWith('Value error, ')
      ? detail[0].msg.slice('Value error, '.length) : null
    const msg = typeof detail === 'string'
      ? detail
      : own ?? (Array.isArray(detail) ? 'Проверьте заполнение полей' : `Ошибка ${res.status}`)
    throw new ApiError(res.status, msg, plusFeatureOf(res))
  }
  return data as T
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function failure(res: Response): Promise<never> {
  const data = await res.json().catch(() => null)
  if (res.status === 401) onUnauthorized()
  throw new ApiError(res.status, typeof data?.detail === 'string' ? data.detail : `Ошибка ${res.status}`, plusFeatureOf(res))
}

/** Загрузка файла формой multipart (браузер сам выставит Content-Type с boundary). */
export async function uploadFile<T>(path: string, file: Blob, filename = 'photo.jpg'): Promise<T> {
  const form = new FormData()
  form.append('file', file, filename)
  const res = await fetch(`/api${path}`, { method: 'PUT', headers: authHeaders(), body: form })
  if (!res.ok) return failure(res)
  return res.json()
}

/** Файл с сервера целиком (PDF, Excel) и его латинское имя из Content-Disposition. */
export async function fetchFile(path: string, fallbackName: string): Promise<File> {
  const res = await fetch(`/api${path}`, { headers: authHeaders() })
  if (!res.ok) return failure(res)
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallbackName
  const blob = await res.blob()
  return new File([blob], name, { type: blob.type || res.headers.get('Content-Type') || '' })
}

/** Скачивание файла, для которого нужен токен: обычная ссылка его не передаст. */
export async function fetchText(path: string): Promise<string> {
  const res = await fetch(`/api${path}`, { headers: authHeaders() })
  if (!res.ok) return failure(res)
  return res.text()
}

// --- оплата Плюса (ЮKassa) ---
export type PaymentBrief = {
  id: number; period: 'month' | 'year'; amount: number; status: 'pending' | 'succeeded' | 'canceled' | 'refunded'
  recurring: boolean; created_at: string; paid_at: string | null; receipt_url: string | null
}
export type PayStatus = {
  enabled: boolean; plus_active: boolean; plus_until: string | null; auto_renew: boolean; recurring_enabled?: boolean
  can_pay: boolean; is_owner: boolean; owner_name: string | null  // платит только владелец семьи
  price_month: number | null; price_year: number | null; payments: PaymentBrief[]
}
export type AdminPayment = PaymentBrief & {
  email: string; user_id: number | null; user_name: string | null; receipt_sent_at: string | null
}
