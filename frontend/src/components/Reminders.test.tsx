import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import type { NotificationPrefs } from '../api'
import { server } from '../test/server'
import { renderWithProviders } from '../test/utils'
import { Reminders } from './Reminders'

function prefs(over: Partial<NotificationPrefs> = {}): NotificationPrefs {
  return {
    available: true, email: 'nikita@example.com', email_possible: true, telegram_possible: true, telegram_bot: 'kapsulka_bot',
    email_enabled: false, telegram_enabled: false, telegram_connected: false, telegram_name: null,
    notify_low: true, notify_expiry: true, expiry_days: 30, ...over,
  }
}

it('включает почту и подключает Telegram по ссылке на бота', async () => {
  const puts: unknown[] = []
  let current = prefs()
  server.use(
    http.get('/api/notifications', () => HttpResponse.json(current)),
    http.put('/api/notifications', async ({ request }) => {
      const body = await request.json() as Partial<NotificationPrefs>
      puts.push(body)
      current = { ...current, ...body }
      return HttpResponse.json(current)
    }),
    http.post('/api/notifications/telegram/link', () => HttpResponse.json({ url: 'https://t.me/kapsulka_bot?start=abc', ttl_minutes: 60 })),
  )
  const { user } = renderWithProviders(<Reminders />)
  await user.click(await screen.findByLabelText(/На почту nikita@example.com/))
  expect(puts).toEqual([{ email_enabled: true }])
  expect(await screen.findByText('Прислать пробное напоминание')).toBeInTheDocument()

  expect(screen.getByText('Подключить Telegram')).toBeDisabled()  // сначала согласие на передачу в Telegram
  await user.click(screen.getByLabelText(/передачу данных напоминаний в Telegram/))
  await user.click(screen.getByText('Подключить Telegram'))
  const open = await screen.findByText('Открыть Telegram')
  expect(open.closest('a')).toHaveAttribute('href', 'https://t.me/kapsulka_bot?start=abc')

  // Человек нажал «Запустить» в боте — страница сама увидит привязку.
  current = { ...current, telegram_connected: true, telegram_enabled: true, telegram_name: '@nikita' }
  expect(await screen.findByText(/В Telegram @nikita/, {}, { timeout: 5000 })).toBeInTheDocument()
})

it('без Плюса показывает замочек и не даёт включить', async () => {
  server.use(http.get('/api/notifications', () => HttpResponse.json(prefs({ available: false }))))
  renderWithProviders(<Reminders />)
  expect(await screen.findByText('Узнать про Плюс')).toHaveAttribute('href', '/plus')
  expect(screen.getByTestId('plus-banner')).toBeInTheDocument()
  // В бесплатной версии настроек нет совсем: только описание и баннер Плюса.
  expect(screen.queryByText('Куда')).not.toBeInTheDocument()
  expect(screen.queryByText('О чём')).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('если на сайте нет почты и бота — объясняет это', async () => {
  server.use(http.get('/api/notifications', () => HttpResponse.json(prefs({ email_possible: false, telegram_possible: false }))))
  renderWithProviders(<Reminders />)
  expect(await screen.findByText('Отправка писем на сайте пока не настроена')).toBeInTheDocument()
  expect(screen.queryByText(/Telegram/)).not.toBeInTheDocument()  // Telegram выключен в админке: о нём ни слова
  expect(screen.queryByText('Подключить Telegram')).not.toBeInTheDocument()
  expect(screen.queryByLabelText(/передачу данных напоминаний в Telegram/)).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByLabelText(/На почту/)).toBeDisabled())
})
