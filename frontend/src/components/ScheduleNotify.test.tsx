import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import type { SchedulePrefs } from '../api'
import { server } from '../test/server'
import { renderWithProviders } from '../test/utils'
import { ScheduleNotify } from './ScheduleNotify'

function prefs(over: Partial<SchedulePrefs> = {}): SchedulePrefs {
  return {
    available: true, email: 'nikita@example.com', email_possible: true, enabled: false, lead_minutes: 10, repeat_minutes: 10,
    escalate_enabled: false, escalate_minutes: 10, share_medicine_name: false, escalate_consent_at: null, trusted: null, ...over,
  }
}

function backend(start: SchedulePrefs) {
  const state = { current: start, puts: [] as unknown[], invites: [] as unknown[] }
  server.use(
    http.get('/api/schedule-notifications', () => HttpResponse.json(state.current)),
    http.put('/api/schedule-notifications', async ({ request }) => {
      const body = await request.json() as Partial<SchedulePrefs>
      state.puts.push(body)
      state.current = { ...state.current, ...body }
      return HttpResponse.json(state.current)
    }),
    http.post('/api/schedule-notifications/trusted', async ({ request }) => {
      const body = await request.json() as { name: string; email: string }
      state.invites.push(body)
      state.current = { ...state.current, trusted: { name: body.name, email: body.email, status: 'pending', confirmed_at: null } }
      return HttpResponse.json(state.current)
    }),
  )
  return state
}

it('включает письма себе и меняет минуты кнопкой', async () => {
  const s = backend(prefs())
  const { user } = renderWithProviders(<ScheduleNotify />)
  expect(screen.queryByText('Напомнить за')).toBeNull()  // пока выключено, настроек нет
  await user.click(await screen.findByLabelText(/Напоминать мне на почту nikita@example.com/))
  expect(s.puts).toEqual([{ enabled: true }])
  const lead = await screen.findByRole('group', { name: 'Напомнить за' })
  await user.click(within(lead).getByRole('button', { name: '30 мин' }))
  await waitFor(() => expect(s.puts.at(-1)).toEqual({ lead_minutes: 30 }))
})

it('приглашает доверенного только с подтверждением, а сообщать ему можно после согласия', async () => {
  const s = backend(prefs({ enabled: true }))
  const { user } = renderWithProviders(<ScheduleNotify />)
  const send = await screen.findByRole('button', { name: 'Отправить приглашение' })
  await user.type(screen.getByLabelText('Как его зовут'), 'Мама')
  await user.type(screen.getByLabelText('Его почта'), 'mama@example.com')
  expect(send).toBeDisabled()  // без подтверждения, что человек согласен, отправить нельзя
  await user.click(screen.getByLabelText(/Я сообщил\(а\) этому человеку/))
  await user.click(send)
  expect(await screen.findByText('Ждём согласия')).toBeInTheDocument()
  expect(s.invites).toEqual([{ name: 'Мама', email: 'mama@example.com', attest: true }])
  expect(screen.getByLabelText(/Сообщать ему/)).toBeDisabled()  // пока он не согласился

  s.current = { ...s.current, trusted: { ...s.current.trusted!, status: 'confirmed', confirmed_at: '2026-10-01T10:00:00Z' } }
  await user.click(await screen.findByLabelText(/Я разрешаю Капсулке сообщать/))
  await waitFor(() => expect(screen.getByLabelText(/Сообщать ему/)).toBeEnabled(), { timeout: 7000 })
  await user.click(screen.getByLabelText(/Сообщать ему/))
  await waitFor(() => expect(s.puts.at(-1)).toEqual({ escalate_enabled: true, escalate_consent: true }))
}, 15_000)

it('без Плюса показывает замочек и не показывает настройки почты', async () => {
  backend(prefs({ available: false }))
  renderWithProviders(<ScheduleNotify />)
  expect(await screen.findByText('Узнать про Плюс')).toHaveAttribute('href', '/plus')
  expect(screen.queryByLabelText(/Напоминать мне на почту/)).not.toBeInTheDocument()
})
