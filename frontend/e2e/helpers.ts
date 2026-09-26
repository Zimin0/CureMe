import { expect, type APIRequestContext, type Page } from '@playwright/test'

let n = 0
export const uniqueEmail = (who = 'user') => `${who}-${Date.now()}-${process.pid}-${n++}@example.com`

export interface Account { email: string; password: string; token: string; familyId: number; name: string }

/** Быстрая регистрация через API — для тестов, где сама регистрация не главное. */
export async function registerApi(request: APIRequestContext, name = 'Никита', invite?: string): Promise<Account> {
  const email = uniqueEmail()
  const res = await request.post('/api/auth/register', { data: { email, name, password: 'secret123', invite_code: invite ?? null } })
  expect(res.status()).toBe(201)
  const body = await res.json()
  return { email, password: 'secret123', token: body.access_token, familyId: body.user.families[0].id, name }
}

/** Открывает приложение уже вошедшим (токен кладём в localStorage до загрузки страницы). */
export async function loginAs(page: Page, acc: Account, path = '/') {
  await page.addInitScript(t => localStorage.setItem('cureme.token', t), acc.token)
  await page.goto(path)
}

export async function addMedicineApi(request: APIRequestContext, acc: Account, body: Record<string, unknown>) {
  const res = await request.post(`/api/families/${acc.familyId}/medicines`, {
    data: body, headers: { Authorization: `Bearer ${acc.token}` },
  })
  expect(res.status()).toBe(201)
  return res.json()
}

export function inDays(days: number) {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toLocaleDateString('sv-SE')
}

/** Случайный, но правильный EAN-13 (с контрольной цифрой): у каждого теста свой товар. */
export function randomEan13() {
  const body = '460' + String(Math.floor(Math.random() * 1e9)).padStart(9, '0')
  const sum = [...body].reverse().reduce((acc, d, i) => acc + Number(d) * (i % 2 === 0 ? 3 : 1), 0)
  return body + ((10 - (sum % 10)) % 10)
}

/** Администратор (его почта задана в CUREME_ADMIN_EMAILS в server.sh). Аккаунт общий для всех тестов. */
export async function adminApi(request: APIRequestContext): Promise<Account> {
  const email = 'e2e-admin@example.com', password = 'secret123'
  await request.post('/api/auth/register', { data: { email, name: 'Админ', password } })  // 409, если уже есть
  const res = await request.post('/api/auth/login', { data: { email, password } })
  expect(res.status()).toBe(200)
  const body = await res.json()
  return { email, password, token: body.access_token, familyId: body.user.families[0]?.id, name: 'Админ' }
}
