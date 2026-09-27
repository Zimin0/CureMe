import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

/**
 * Поддельный бэкенд для компонентных тестов (Mock Service Worker).
 * Тест сам описывает ответы через server.use(http.get('/api/...', ...)).
 * Любой запрос без описанного ответа роняет тест — так не пропустим лишний вызов API.
 */
export const server = setupServer(
  // по умолчанию сайт открыт; тесты закрытого режима подменяют ответ
  http.get('/api/auth/access', () => HttpResponse.json({ closed: false })),
)
