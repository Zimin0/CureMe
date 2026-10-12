/**
 * Яндекс Метрика с согласием посетителя.
 *
 * Счётчик подключается, только если на сайте задан CUREME_METRIKA_ID (приходит в /auth/access) И посетитель нажал
 * «Принять» в баннере. До согласия скрипт Яндекса не загружается, cookie не ставятся, адреса не отправляются.
 * Отказ или отзыв согласия удаляют cookie счётчика (_ym*) и останавливают отправку.
 *
 * Что уходит в Яндекс: только обезличенный адрес страницы из белого списка (без кодов приглашения, номеров и
 * названий лекарств) и названия целей из списка GOALS. Заголовок страницы, вебвизор, карту кликов и отслеживание
 * ссылок отключаем: в названии страницы и в кликах могут быть названия лекарств, то есть данные о здоровье.
 */
import { useQuery } from '@tanstack/react-query'
import { useEffect, useSyncExternalStore } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api } from './api'

const KEY = 'curemeAnalytics'
const EVENT = 'cureme-analytics-consent'

/** Цели Метрики. Название цели в Метрике = название здесь; параметров не передаём. */
export const GOALS = {
  register: 'register',            // создан аккаунт
  emailConfirmed: 'email_confirmed', // подтверждена почта (с этого момента идёт пробный Плюс)
  medicineAdded: 'medicine_added', // добавлено лекарство (активация)
  plusView: 'plus_view',           // открыта шторка или страница тарифа
  payClick: 'pay_click',           // нажата «Оплатить»
  paid: 'paid',                    // оплата прошла
} as const
export type Goal = (typeof GOALS)[keyof typeof GOALS]

type Consent = 'yes' | 'no' | null

export function getConsent(): Consent {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'yes' || v === 'no' ? v : null
  } catch { return null }
}

export function setConsent(v: 'yes' | 'no' | null) {
  try {
    if (v) localStorage.setItem(KEY, v)
    else localStorage.removeItem(KEY)
  } catch { /* хранилище недоступно: просто не запоминаем выбор */ }
  if (v !== 'yes') clearYmCookies()
  window.dispatchEvent(new Event(EVENT))
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb)
  return () => window.removeEventListener(EVENT, cb)
}
export function useConsent(): Consent {
  return useSyncExternalStore(subscribe, getConsent, () => null)
}

/** Удаляет cookie счётчика (_ym_*, _ymab_param) с текущего домена и его родительских. */
export function clearYmCookies() {
  const parts = location.hostname.split('.')
  const domains = ['']
  for (let i = 0; i < parts.length - 1; i++) domains.push(`; domain=.${parts.slice(i).join('.')}`)
  for (const c of document.cookie.split(';')) {
    const name = c.split('=')[0].trim()
    if (!/^_ym|^yandexuid$|^ymex$|^yabs-sid$|^i$/.test(name)) continue
    for (const d of domains) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/${d}`
  }
}

const PUBLIC_PAGES = new Set(['', 'login', 'register', 'plus', 'privacy', 'terms', 'consent', 'offer', 'consent-share', 'consent-telegram', 'consent-trusted', 'reset-password', 'join'])

/** Обезличенный адрес для Метрики: только первый сегмент, и только у публичных страниц. Остальное — «/app». */
export function safePath(pathname: string): string {
  const first = pathname.split('/')[1] ?? ''
  return PUBLIC_PAGES.has(first) ? `/${first}` : '/app'
}

type Ym = (id: number, method: string, ...args: unknown[]) => void
declare global { interface Window { ym?: Ym } }

let loadedId: string | null = null

function load(id: string) {
  if (loadedId) return
  loadedId = id
  const w = window as unknown as { ym: Ym & { a?: unknown[] } }
  w.ym = w.ym || function (...args: unknown[]) { (w.ym.a = w.ym.a || []).push(args) } as Ym & { a?: unknown[] }
  const s = document.createElement('script')
  s.async = true
  s.src = `https://mc.yandex.ru/metrika/tag.js`
  document.head.appendChild(s)
  w.ym(Number(id), 'init', {
    defer: true,              // первый просмотр отправляем сами, с обезличенным адресом
    clickmap: false, trackLinks: false, accurateTrackBounce: true, webvisor: false, ecommerce: false, trackHash: false,
  })
}

let currentId: string | null = null

/** Цель в Метрику. Без номера счётчика или без согласия ничего не делает. */
export function track(goal: Goal) {
  if (!currentId || getConsent() !== 'yes' || !window.ym) return
  window.ym(Number(currentId), 'reachGoal', goal)
}

function hit(id: string, pathname: string) {
  window.ym?.(Number(id), 'hit', `${location.origin}${safePath(pathname)}`, { title: '' })
}

/** Баннер согласия + отправка просмотров страниц. Ставится один раз внутри BrowserRouter. */
export function Analytics() {
  const q = useQuery({ queryKey: ['access'], queryFn: () => api<{ metrika_id?: string | null }>('/auth/access'), staleTime: 60_000 })
  const id = q.data?.metrika_id ?? null
  const consent = useConsent()
  const { pathname } = useLocation()
  currentId = id

  useEffect(() => {
    if (id && consent === 'yes') load(id)
  }, [id, consent])

  useEffect(() => {
    if (id && consent === 'yes') hit(id, pathname)
  }, [id, consent, pathname])

  if (!id || consent !== null) return null
  return (
    <div className="cookie-banner" role="dialog" aria-label="Файлы cookie">
      <p>
        Мы считаем посещения сайта сервисом Яндекс Метрика: для этого Яндекс ставит cookie и получает ваш IP-адрес и адреса открытых
        страниц (без названий лекарств и личных данных). Без вашего согласия мы этого не делаем.{' '}
        <Link to="/privacy#cookie">Подробнее в Политике</Link>
      </p>
      <div className="cookie-banner-actions">
        <button className="btn primary" onClick={() => setConsent('yes')}>Принять</button>
        <button className="btn" onClick={() => setConsent('no')}>Отклонить</button>
      </div>
    </div>
  )
}

/** Переключатель в Политике: показывается, только если на сайте есть счётчик. */
export function CookieSettings() {
  const q = useQuery({ queryKey: ['access'], queryFn: () => api<{ metrika_id?: string | null }>('/auth/access'), staleTime: 60_000 })
  const consent = useConsent()
  if (!q.data?.metrika_id) return null
  return (
    <p data-testid="cookie-settings">
      Ваш выбор сейчас: <b>{consent === 'yes' ? 'аналитика разрешена' : consent === 'no' ? 'аналитика отклонена' : 'выбор не сделан'}</b>.{' '}
      {consent === 'yes'
        ? <button className="btn" onClick={() => setConsent('no')}>Отозвать согласие</button>
        : <button className="btn" onClick={() => setConsent('yes')}>Разрешить аналитику</button>}
    </p>
  )
}
