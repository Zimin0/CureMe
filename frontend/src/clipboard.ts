/** Копирует текст в буфер. Возвращает true, если получилось.
 *  Сначала современный Clipboard API (нужен HTTPS и жест пользователя),
 *  при отказе (старый Safari, WebView, http) запасной путь через временный textarea и execCommand. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch { /* падаем на запасной вариант */ }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;font-size:16px'  // 16px: iOS не приближает экран
    document.body.appendChild(ta)
    ta.focus()
    ta.select()
    ta.setSelectionRange(0, text.length)
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}
