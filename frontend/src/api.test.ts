import { http, HttpResponse } from 'msw'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, fetchText, getToken, setToken, setUnauthorizedHandler, uploadFile } from './api'
import { server } from './test/server'

afterEach(() => setUnauthorizedHandler(() => {}))

describe('api()', () => {
  it('GET по умолчанию, с токеном в заголовке', async () => {
    setToken('abc')
    let seen: Request | undefined
    server.use(http.get('/api/ping', ({ request }) => { seen = request; return HttpResponse.json({ ok: 1 }) }))
    await expect(api('/ping')).resolves.toEqual({ ok: 1 })
    expect(seen!.headers.get('authorization')).toBe('Bearer abc')
    expect(seen!.headers.get('content-type')).toBeNull()
  })

  it('без токена заголовка Authorization нет', async () => {
    let auth: string | null = 'x'
    server.use(http.get('/api/ping', ({ request }) => { auth = request.headers.get('authorization'); return HttpResponse.json(1) }))
    await api('/ping')
    expect(auth).toBeNull()
  })

  it('тело превращает запрос в POST с JSON', async () => {
    server.use(http.post('/api/items', async ({ request }) => HttpResponse.json({
      got: await request.json(), type: request.headers.get('content-type'),
    })))
    await expect(api('/items', { body: { a: 1 } })).resolves.toEqual({ got: { a: 1 }, type: 'application/json' })
  })

  it('метод можно задать явно', async () => {
    server.use(http.patch('/api/items/1', () => HttpResponse.json({ patched: true })))
    await expect(api('/items/1', { method: 'PATCH', body: {} })).resolves.toEqual({ patched: true })
  })

  it('204 — пустой ответ', async () => {
    server.use(http.delete('/api/items/1', () => new HttpResponse(null, { status: 204 })))
    await expect(api('/items/1', { method: 'DELETE' })).resolves.toBeUndefined()
  })

  it.each([
    [{ detail: 'Аккаунт с такой почтой уже есть' }, 409, 'Аккаунт с такой почтой уже есть'],
    [{ detail: [{ loc: ['body', 'name'], msg: 'too short' }] }, 422, 'Проверьте заполнение полей'],
    [{ detail: [{ loc: ['body', 'password'], msg: 'Value error, Пароль слишком длинный' }] }, 422, 'Пароль слишком длинный'],
    [null, 500, 'Ошибка 500'],
  ])('ошибка сервера → ApiError с понятным текстом (%j)', async (body, status, message) => {
    server.use(http.get('/api/fail', () => (body ? HttpResponse.json(body, { status }) : new HttpResponse('boom', { status }))))
    const err = await api('/fail').catch(e => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status, message })
  })

  it('нет сети → статус 0', async () => {
    server.use(http.get('/api/ping', () => HttpResponse.error()))
    await expect(api('/ping')).rejects.toMatchObject({ status: 0, message: expect.stringContaining('Нет связи') })
  })

  it('401 при наличии токена разлогинивает, без токена — нет', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    server.use(http.get('/api/me', () => HttpResponse.json({ detail: 'Нужно войти' }, { status: 401 })))
    await api('/me').catch(() => {})
    expect(handler).not.toHaveBeenCalled()
    setToken('expired')
    await api('/me').catch(() => {})
    expect(handler).toHaveBeenCalledOnce()
  })
})

describe('токен', () => {
  it('сохраняется и удаляется', () => {
    setToken('t1')
    expect(getToken()).toBe('t1')
    setToken(null)
    expect(getToken()).toBeNull()
  })

  it('не падает, если localStorage недоступен (приватный режим)', () => {
    const spy = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
    expect(getToken()).toBeNull()
    spy.mockRestore()
  })
})

describe('файлы', () => {
  it('uploadFile шлёт multipart с токеном', async () => {
    // FormData из jsdom не понимает fetch из Node, поэтому здесь подменяем сам fetch (spy)
    // и проверяем, с чем его вызвали.
    setToken('abc')
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ ok: true })))
    const res = await uploadFile('/photo', new Blob(['12345'], { type: 'image/jpeg' }), 'p.jpg')
    expect(res).toEqual({ ok: true })
    const [url, init] = spy.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/photo')
    expect(init.method).toBe('PUT')
    expect(init.headers).toEqual({ Authorization: 'Bearer abc' })  // Content-Type с boundary ставит браузер
    const file = (init.body as FormData).get('file') as File
    expect(file.name).toBe('p.jpg')
    expect(file.size).toBe(5)
    spy.mockRestore()
  })

  it('uploadFile пробрасывает ошибку сервера', async () => {
    server.use(http.put('/api/photo', () => HttpResponse.json({ detail: 'Нужна картинка JPG, PNG или WebP' }, { status: 415 })))
    await expect(uploadFile('/photo', new Blob(['x']))).rejects.toMatchObject({ status: 415, message: 'Нужна картинка JPG, PNG или WebP' })
  })

  it('fetchText возвращает текст', async () => {
    server.use(http.get('/api/export.txt', () => HttpResponse.text('Нурофен — 200 мг\n')))
    await expect(fetchText('/export.txt')).resolves.toBe('Нурофен — 200 мг\n')
  })

  it('fetchText на 401 разлогинивает', async () => {
    const handler = vi.fn()
    setUnauthorizedHandler(handler)
    server.use(http.get('/api/export.txt', () => HttpResponse.json({ detail: 'x' }, { status: 401 })))
    await expect(fetchText('/export.txt')).rejects.toBeInstanceOf(ApiError)
    expect(handler).toHaveBeenCalled()
  })
})
