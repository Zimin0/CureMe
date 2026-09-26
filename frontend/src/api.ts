// Типы повторяют схемы бэкенда (backend/app/schemas.py).
export type Role = 'owner' | 'member'
export type StockStatus = 'ok' | 'low' | 'out' | 'expiring' | 'expired'

export interface FamilyBrief { id: number; name: string; role: Role }
export interface Me { id: number; email: string; name: string; families: FamilyBrief[] }
export interface Member { user_id: number; name: string; email: string; role: Role; joined_at: string }
export interface Family { id: number; name: string; invite_code: string; role: Role; members: Member[] }
export interface Category { id: number; name: string; icon: string; color: string; medicine_count: number }

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
  category_id: number | null
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
  category: Category | null
  stock: Stock
  is_favorite: boolean
  helps_me: boolean
  personal_note: string
  helps_members: string[]
  created_at: string
  updated_at: string
}

export interface MedicineDetail extends Medicine { packages: Package[] }

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
  constructor(public status: number, message: string) { super(message) }
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn }

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
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail) ? 'Проверьте заполнение полей' : `Ошибка ${res.status}`
    throw new ApiError(res.status, msg)
  }
  return data as T
}
