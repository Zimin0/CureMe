import { screen, waitFor, within } from '@testing-library/react'
import type { UserEvent } from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'
import type { ScanResult } from '../api'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

// Камера и wasm-декодер в jsdom не работают — компонент камеры заменяем пустышкой.
vi.mock('../components/Scanner', () => ({ Scanner: () => <div>камера</div> }))
// Сжатие фото через canvas в jsdom недоступно — отдаём файл как есть.
vi.mock('../image', () => ({ compressImage: async (f: File) => f }))

const PARSED = { kind: 'ean13', raw: '4605077018932', gtin: '04605077018932', serial: null, batch: null, expiry: null }

function scanReturns(result: Partial<ScanResult>) {
  let sent: unknown
  server.use(http.post('/api/families/7/scan', async ({ request }) => {
    sent = await request.json()
    return HttpResponse.json({ parsed: PARSED, display_code: '4605077018932', medicine: null, product: null, duplicate_package: false, ...result })
  }))
  return () => sent
}

async function enterCode(user: UserEvent, code = '4605077018932') {
  await user.type(await screen.findByPlaceholderText(/Цифры под штрихкодом/), code)
  await user.click(screen.getByRole('button', { name: 'Найти' }))
}

describe('сканирование: ручной ввод кода', () => {
  it('найденное в интернете лекарство сохраняется в аптечку', async () => {
    const sent = scanReturns({ product: { gtin: '04605077018932', name: 'Ларингобакт', title: 'Ларингобакт таблетки для рассасывания №30', form: 'Таблетки', dosage: '20 мг + 10 мг', active_ingredient: null, manufacturer: null, unit: 'таб', pack_size: 30, blister_size: 10, source: 'internet' } })
    let created: Record<string, unknown> = {}
    server.use(
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([])),
      http.post('/api/families/7/medicines', async ({ request }) => {
        created = await request.json() as Record<string, unknown>
        return HttpResponse.json({ ...medicine({ id: 42, name: 'Ларингобакт' }), packages: [] }, { status: 201 })
      }),
      http.get('/api/families/7/medicines/42', () => HttpResponse.json({ ...medicine({ id: 42, name: 'Ларингобакт' }), packages: [] })),
    )
    const { user } = renderApp('/scan')
    await enterCode(user)
    const dialog = await screen.findByRole('dialog', { name: 'Нашли лекарство' })
    expect(sent()).toEqual({ raw: '4605077018932' })
    expect(within(dialog).getByText('Ларингобакт таблетки для рассасывания №30')).toBeInTheDocument()
    expect(within(dialog).getByLabelText('Название')).toHaveValue('Ларингобакт')
    await user.click(within(dialog).getByRole('button', { name: 'Сохранить в аптечку' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/medicines/42'))
    expect(created).toMatchObject({ name: 'Ларингобакт', gtin: '4605077018932', unit: 'таб', blister_size: 10, packages: [{ quantity: 30 }] })
  })

  it('уже известное лекарство: добавляется упаковка, повтор упаковки подсвечен', async () => {
    scanReturns({ medicine: medicine({ id: 5, name: 'Нурофен' }), duplicate_package: true })
    const { user } = renderApp('/scan')
    await enterCode(user)
    const dialog = await screen.findByRole('dialog', { name: 'Уже есть в аптечке' })
    expect(within(dialog).getByText(/Эту самую упаковку уже сканировали/)).toBeInTheDocument()
    expect(within(dialog).getByText('Сейчас в аптечке: 20 таб')).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: 'Добавить упаковку' })).toBeInTheDocument()
  })

  it('нераспознанный код — ошибка и кнопка «Ещё раз»', async () => {
    server.use(http.post('/api/families/7/scan', () => HttpResponse.json({ detail: 'Не получилось распознать код товара.' }, { status: 422 })))
    const { user } = renderApp('/scan')
    await enterCode(user, '123')
    expect(await screen.findByText('Не получилось распознать код товара.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Ещё раз' }))
    expect(screen.queryByText('Не получилось распознать код товара.')).not.toBeInTheDocument()
  })

  it('фото, снятое в окне сканирования, не теряется после «Заполнить подробнее»', async () => {
    URL.createObjectURL = vi.fn(() => 'blob:scan-photo')
    URL.revokeObjectURL = vi.fn()
    scanReturns({ product: { gtin: '04605077018932', name: 'Ларингобакт', title: null, form: 'Таблетки', dosage: null, active_ingredient: null, manufacturer: null, unit: 'таб', pack_size: 30, blister_size: 10, source: 'internet' } })
    let uploaded = false
    server.use(
      http.get('/api/families/7/categories', () => HttpResponse.json([])),
      http.get('/api/families/7/medicines', () => HttpResponse.json([])),
      http.post('/api/families/7/medicines', () => HttpResponse.json({ ...medicine({ id: 42, name: 'Ларингобакт' }), packages: [] }, { status: 201 })),
      http.put('/api/families/7/medicines/42/photo', () => {
        uploaded = true
        return HttpResponse.json({ ...medicine({ id: 42, name: 'Ларингобакт', photo_url: '/uploads/42.jpg' }), packages: [] })
      }),
      http.get('/api/families/7/medicines/42', () => HttpResponse.json({ ...medicine({ id: 42, name: 'Ларингобакт' }), packages: [] })),
    )
    const { user, container } = renderApp('/scan')
    await enterCode(user)
    const dialog = await screen.findByRole('dialog', { name: 'Нашли лекарство' })
    const photo = new File(['jpeg'], 'pack.jpg', { type: 'image/jpeg' })
    await user.upload(container.ownerDocument.querySelector<HTMLInputElement>('input[type=file][capture]')!, photo)
    expect(await within(dialog).findByAltText('Фото лекарства')).toHaveAttribute('src', 'blob:scan-photo')

    await user.click(within(dialog).getByRole('button', { name: 'Заполнить подробнее' }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/medicines/new'))
    // Превью фото видно в полной форме
    expect(await screen.findByAltText('Фото лекарства')).toHaveAttribute('src', 'blob:scan-photo')

    await user.click(screen.getByRole('button', { name: /Добавить в аптечку|Сохранить/ }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/medicines/42'))
    expect(uploaded).toBe(true)
  })
})
