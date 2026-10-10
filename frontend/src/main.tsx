import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import { AuthProvider } from './auth'
import { ToastProvider } from './components/ui'
import { PlusProvider } from './plan'
import '@fontsource-variable/manrope'
import '@fontsource-variable/comfortaa'
import './styles.css'

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: 1 } },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ToastProvider>
            <PlusProvider>
              <App />
            </PlusProvider>
          </ToastProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)

// Service worker сам ставит новую версию и перезагружает страницу (registerType: 'autoUpdate').
// Без этого вызова вкладка после выката открывала старую версию из кеша ещё один заход.
// Новую версию ищем при каждом возвращении на вкладку и раз в 10 минут: PWA на телефоне месяцами живёт в фоне.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (!registration) return
    const check = () => registration.update().catch(() => {})
    setInterval(check, 10 * 60 * 1000)
    document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && check())
  },
})
