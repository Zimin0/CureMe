/**
 * Куда вести человека после входа (адрес из ?next=). Только на страницы этого же сайта.
 *
 * Без проверки ссылка вида /login?next=/\evil.example/ после настоящего входа на нашем сайте отправляла бы
 * на чужой (open redirect): React Router принимает «/\» за начало чужого адреса и делает полный переход.
 * Подходит только путь, который браузер разберёт как адрес нашего же сайта.
 */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith('/') || raw.includes('\\')) return '/'
  try {
    // Браузер выбрасывает табы и переводы строк из адреса: «/<таб>/evil.example» превращается в «//evil.example».
    if (new URL(raw, window.location.origin).origin !== window.location.origin) return '/'
  } catch {
    return '/'
  }
  return raw
}
