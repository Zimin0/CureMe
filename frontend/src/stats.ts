/**
 * Собственная статистика сайта. На сервер уходят только агрегированные числа: адрес публичной страницы
 * (без кодов), домен источника и метка utm_source. Ни cookie, ни идентификатора посетителя, ни сторонних
 * сервисов, поэтому согласие на аналитику не нужно (Политика, п. 8). Сбой отправки молча игнорируем.
 */
import { api } from './api'

const SENT = 'curemeVisitSent'

/** Один заход на сессию вкладки. Режим «Не отслеживать» в браузере уважаем. */
export function sendVisit() {
  if (navigator.doNotTrack === '1') return
  try {
    if (sessionStorage.getItem(SENT)) return
    sessionStorage.setItem(SENT, '1')
  } catch { return }  // без хранилища считали бы каждую страницу заходом
  const utm = new URLSearchParams(location.search).get('utm_source')
  api('/stats/visit', { body: { path: location.pathname, ref: document.referrer || null, utm } }).catch(() => {})
}

/** Цели, которых нет в базе. Остальное (регистрации, оплаты) сервер считает по своим таблицам. */
export type Goal = 'plus_view' | 'pay_click'

export function track(goal: Goal) {
  if (navigator.doNotTrack === '1') return
  api('/stats/goal', { body: { goal } }).catch(() => {})
}
