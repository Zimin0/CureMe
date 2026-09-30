import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { renderApp } from '../test/utils'

it('доверенный соглашается по ссылке, а потом может отписаться', async () => {
  const calls: string[] = []
  let status = 'pending'
  server.use(
    http.post('/api/trusted/lookup', async ({ request }) => {
      expect(await request.json()).toEqual({ token: '7.abc' })
      return HttpResponse.json({ user_name: 'Никита', status })
    }),
    http.post('/api/trusted/confirm', () => { calls.push('confirm'); status = 'confirmed'; return HttpResponse.json({ user_name: 'Никита', status }) }),
    http.post('/api/trusted/decline', () => { calls.push('decline'); status = 'revoked'; return HttpResponse.json({ user_name: 'Никита', status }) }),
  )
  const { user } = renderApp('/trusted#7.abc', { loggedIn: false })
  expect(await screen.findByText(/указал\(а\) вас доверенным человеком/)).toBeInTheDocument()
  expect(screen.getByText(/только для этих писем/)).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: /Согласен\(на\) получать письма/ }))
  expect(await screen.findByText('Вы согласились')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Отписаться' }))
  expect(await screen.findByText('Вы отписались')).toBeInTheDocument()
  await waitFor(() => expect(calls).toEqual(['confirm', 'decline']))
})

it('отказ и неверная ссылка', async () => {
  server.use(
    http.post('/api/trusted/lookup', () => HttpResponse.json({ user_name: 'Никита', status: 'pending' })),
    http.post('/api/trusted/decline', () => HttpResponse.json({ user_name: 'Никита', status: 'declined' })),
  )
  const first = renderApp('/trusted#1.x', { loggedIn: false })
  await first.user.click(await screen.findByRole('button', { name: /Не согласен/ }))
  expect(await screen.findByText('Вы отказались')).toBeInTheDocument()
  first.unmount()

  server.use(http.post('/api/trusted/lookup', () => HttpResponse.json({ detail: 'Ссылка недействительна: возможно, её отозвали' }, { status: 404 })))
  renderApp('/trusted#bad', { loggedIn: false })
  expect(await screen.findByText(/Ссылка недействительна/)).toBeInTheDocument()
})
