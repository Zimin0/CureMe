import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { sendVisit, track } from './stats'
import { server } from './test/server'

describe('собственная статистика', () => {
  beforeEach(() => { sessionStorage.clear() })

  it('заход считается один раз за сессию и шлёт только путь, источник и utm', async () => {
    const bodies: unknown[] = []
    server.use(http.post('/api/stats/visit', async ({ request }) => { bodies.push(await request.json()); return new HttpResponse(null, { status: 204 }) }))
    window.history.pushState({}, '', '/plus?utm_source=tg_mama&invite=SECRET')
    sendVisit(); sendVisit()
    await new Promise(r => setTimeout(r, 50))
    expect(bodies).toEqual([{ path: '/plus', ref: null, utm: 'tg_mama' }])
    expect(JSON.stringify(bodies)).not.toContain('SECRET')
  })

  it('«Не отслеживать» отключает отправку', async () => {
    let n = 0
    server.use(http.post('/api/stats/goal', () => { n++; return new HttpResponse(null, { status: 204 }) }))
    Object.defineProperty(navigator, 'doNotTrack', { value: '1', configurable: true })
    track('pay_click')
    await new Promise(r => setTimeout(r, 50))
    expect(n).toBe(0)
    Object.defineProperty(navigator, 'doNotTrack', { value: null, configurable: true })
    track('pay_click')
    await new Promise(r => setTimeout(r, 50))
    expect(n).toBe(1)
  })
})
