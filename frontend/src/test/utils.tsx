import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import type { ReactElement } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import type { Me, Medicine } from '../api'
import App from '../App'
import { AuthProvider } from '../auth'
import { ToastProvider } from '../components/ui'
import { server } from './server'

export const ME: Me = { id: 1, email: 'nikita@example.com', name: 'Никита', families: [{ id: 7, name: 'Семья Никита', role: 'owner' }] }

/** Показывает текущий адрес — удобно проверять навигацию. */
export function LocationProbe() {
  const loc = useLocation()
  return <div data-testid="location">{loc.pathname + loc.search}</div>
}

/** Рендерит элемент со всеми провайдерами приложения (запросы, роутер, авторизация, тосты). */
export function renderWithProviders(ui: ReactElement, { route = '/' } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const user = userEvent.setup()
  const result = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>
        <AuthProvider>
          <ToastProvider>
            {ui}
            <LocationProbe />
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, user, qc }
}

/** Всё приложение целиком, как в браузере. loggedIn — положить токен и отдать /auth/me. */
export function renderApp(route = '/', { loggedIn = true, me = ME } = {}) {
  if (loggedIn) {
    localStorage.setItem('cureme.token', 'test-token')
    server.use(http.get('/api/auth/me', () => HttpResponse.json(me)))
  }
  return renderWithProviders(<App />, { route })
}

export function medicine(over: Partial<Medicine> = {}): Medicine {
  return {
    id: 1, name: 'Нурофен', category_id: null, form: 'Таблетки', dosage: '200 мг', active_ingredient: 'ибупрофен',
    manufacturer: null, indications: 'головная боль', contraindications: '', notes: '', unit: 'таб',
    min_quantity: null, blister_size: 10, gtin: null, category: null,
    stock: { total: 20, expired_quantity: 0, package_count: 1, nearest_expiry: '2027-05-31', days_left: 400, status: 'ok' },
    is_favorite: false, helps_me: false, personal_note: '', helps_members: [], photo_url: null,
    created_at: '2026-09-26T10:00:00Z', updated_at: '2026-09-26T10:00:00Z',
    ...over,
  }
}
