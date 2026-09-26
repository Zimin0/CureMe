import { setupServer } from 'msw/node'

/**
 * Поддельный бэкенд для компонентных тестов (Mock Service Worker).
 * Тест сам описывает ответы через server.use(http.get('/api/...', ...)).
 * Любой запрос без описанного ответа роняет тест — так не пропустим лишний вызов API.
 */
export const server = setupServer()
