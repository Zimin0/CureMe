import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminPayment, PayStatus } from '../api'
import { planFixture, server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const STATUS: PayStatus = {
  enabled: true, plus_active: false, plus_until: null, auto_renew: false, recurring_enabled: true, price_month: 199, price_year: 1990, payments: [],
}
const payStatus = (over: Partial<PayStatus> = {}) => http.get('/api/payments/me', () => HttpResponse.json({ ...STATUS, ...over }))
const billing = http.get('/api/families/7/plan', () => HttpResponse.json(planFixture({ has_plus: false, billing_enabled: true })))

const assign = vi.fn()
beforeEach(() => { vi.stubGlobal('location', { ...window.location, assign, origin: window.location.origin, pathname: '/plus', search: '' }) })
afterEach(() => { vi.unstubAllGlobals(); assign.mockClear() })

describe('оплата Плюса на странице /plus', () => {
  it('оплата выключена: блока оплаты нет', async () => {
    server.use(billing)
    renderApp('/plus')
    expect(await screen.findByText(/Оплата появится скоро/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Оплатить/ })).not.toBeInTheDocument()
  })

  it('автопродление по умолчанию выключено, оплата только после согласия с офертой', async () => {
    server.use(billing, payStatus())
    const { user } = renderApp('/plus')
    const pay = await screen.findByRole('button', { name: /Оплатить 199 ₽/ })
    const renew = screen.getByRole('checkbox', { name: /автоматически продлевать/ })
    const agree = screen.getByRole('checkbox', { name: /публичной офертой/ })
    expect(renew).not.toBeChecked()
    expect(agree).not.toBeChecked()
    expect(pay).toBeDisabled()
    expect(screen.getByText(/на наш сервер не передаются/)).toBeInTheDocument()
    expect(screen.queryByText(/Оплата появится скоро/)).not.toBeInTheDocument()
    await user.click(agree)
    expect(pay).toBeEnabled()
  })

  it('создаёт платёж с выбранным сроком и согласием и отправляет на страницу оплаты ЮKassa', async () => {
    let sent: unknown
    server.use(billing, payStatus(), http.post('/api/payments', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ payment_id: 5, confirmation_url: 'https://yookassa.ru/checkout/payments/v2/contract?orderId=x' }, { status: 201 })
    }))
    const { user } = renderApp('/plus')
    await user.click(await screen.findByRole('radio', { name: /1\D990 ₽ за год/ }))
    await user.click(screen.getByRole('checkbox', { name: /публичной офертой/ }))
    await user.click(screen.getByRole('checkbox', { name: /автоматически продлевать/ }))
    await user.click(screen.getByRole('button', { name: /Оплатить 1\D990 ₽/ }))
    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://yookassa.ru/checkout/payments/v2/contract?orderId=x'))
    expect(sent).toEqual({ period: 'year', auto_renew: true, agree: true })
  })

  it('пока ЮKassa не подключила автоплатежи, галочки автопродления нет и она не уходит на сервер', async () => {
    let sent: unknown
    server.use(billing, payStatus({ recurring_enabled: false }), http.post('/api/payments', async ({ request }) => {
      sent = await request.json()
      return HttpResponse.json({ payment_id: 6, confirmation_url: 'https://yookassa.ru/x' }, { status: 201 })
    }))
    const { user } = renderApp('/plus')
    await user.click(await screen.findByRole('checkbox', { name: /публичной офертой/ }))
    expect(screen.queryByRole('checkbox', { name: /автоматически продлевать/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Оплатить 199 ₽/ }))
    await waitFor(() => expect(sent).toEqual({ period: 'month', auto_renew: false, agree: true }))
  })

  it('незавершённые попытки оплаты в списке не показываются', async () => {
    const mk = (id: number, status: 'pending' | 'succeeded') => ({ id, period: 'month', amount: 199, status, recurring: false, created_at: '2026-10-03T10:00:00Z', paid_at: status === 'succeeded' ? '2026-10-03T10:01:00Z' : null, receipt_url: null } as const)
    server.use(billing, payStatus({ payments: [mk(3, 'pending'), mk(2, 'pending'), mk(1, 'succeeded')] }))
    renderApp('/plus')
    expect(await screen.findByText('Ваши оплаты')).toBeInTheDocument()
    expect(screen.queryByText('ожидает оплаты')).not.toBeInTheDocument()
    expect(screen.getByText('оплачено')).toBeInTheDocument()
  })

  it('кнопка «Отключить автопродление» отключает его', async () => {
    let called = false
    server.use(billing, payStatus({ auto_renew: true, plus_active: true, plus_until: '2026-11-03T10:00:00Z' }),
      http.post('/api/payments/auto-renew/off', () => {
        called = true
        return HttpResponse.json({ ...STATUS, auto_renew: false })
      }))
    const { user } = renderApp('/plus')
    await user.click(await screen.findByRole('button', { name: 'Отключить автопродление' }))
    await waitFor(() => expect(called).toBe(true))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Отключить автопродление' })).not.toBeInTheDocument())
  })

  it('после возврата с оплаты показывает, что Плюс включён, и ссылку на чек', async () => {
    const paid = { id: 5, period: 'month', amount: 199, status: 'succeeded', recurring: false, created_at: '2026-10-03T10:00:00Z', paid_at: '2026-10-03T10:01:00Z', receipt_url: 'https://lknpd.nalog.ru/x/print' } as const
    server.use(billing, payStatus({ payments: [paid], plus_active: true }))
    renderApp('/plus?paid=5')
    expect(await screen.findByText(/Оплата прошла, Плюс включён/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'чек' })).toHaveAttribute('href', 'https://lknpd.nalog.ru/x/print')
  })
})

const ADMIN = { ...ME, is_admin: true }
const PAYMENT: AdminPayment = {
  id: 11, period: 'month', amount: 199, status: 'succeeded', recurring: false, created_at: '2026-10-03T10:00:00Z',
  paid_at: '2026-10-03T10:01:00Z', receipt_url: null, email: 'buyer@example.com', user_id: 2, user_name: 'Покупатель', receipt_sent_at: null,
}

describe('админ-страница «Оплаты и чеки»', () => {
  it('обычного пользователя не пускает', async () => {
    renderApp('/admin/payments')
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/'))
  })

  it('показывает оплаты без чека и отправляет ссылку покупателю', async () => {
    let body: unknown
    server.use(
      http.get('/api/admin/payments', () => HttpResponse.json([PAYMENT, { ...PAYMENT, id: 10, receipt_url: 'https://x.example/a', receipt_sent_at: '2026-10-02T10:00:00Z' }])),
      http.put('/api/admin/payments/11/receipt', async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({ ...PAYMENT, receipt_url: 'https://lknpd.nalog.ru/x/print', receipt_sent_at: '2026-10-03T12:00:00Z' })
      }),
    )
    const { user } = renderApp('/admin/payments', { me: ADMIN })
    expect(await screen.findByText(/buyer@example.com/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Нужен чек \(1\)/ })).toBeInTheDocument()
    expect(screen.getByText(/Подписка Капсулка Плюс на 1 месяц, 199 ₽/)).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Отправить покупателю' })).toHaveLength(1)
    const send = screen.getByRole('button', { name: 'Отправить покупателю' })
    expect(send).toBeDisabled()
    await user.type(screen.getByLabelText('Ссылка на чек, оплата 11'), 'https://lknpd.nalog.ru/x/print')
    await user.click(send)
    await waitFor(() => expect(body).toEqual({ url: 'https://lknpd.nalog.ru/x/print', send_email: true }))
  })

  it('вкладка «Все оплаты» показывает и оформленные', async () => {
    server.use(http.get('/api/admin/payments', () => HttpResponse.json([{ ...PAYMENT, receipt_url: 'https://x.example/a', receipt_sent_at: '2026-10-02T10:00:00Z' }])))
    const { user } = renderApp('/admin/payments', { me: ADMIN })
    expect(await screen.findByText('Чеков к оформлению нет')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /Все оплаты/ }))
    expect(await screen.findByText(/Чек отправлен покупателю/)).toBeInTheDocument()
  })
})
