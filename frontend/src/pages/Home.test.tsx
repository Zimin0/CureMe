import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

it('плитки на главной ведут в аптечку с нужным фильтром', async () => {
  server.use(
    http.get('/api/families/7/overview', () => HttpResponse.json({
      total_medicines: 3, total_packages: 4, expired: [medicine({ id: 2, name: 'Аспирин' })], expiring: [], low: [],
      favorites: [], helps_me: [], expiring_soon_days: 30,
    })),
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json([])),
  )
  const { user } = renderApp('/')
  const tile = await screen.findByRole('link', { name: /Лекарств\s*3/ })
  expect(tile).toHaveAttribute('href', '/medicines')
  expect(screen.getByRole('link', { name: /Упаковок\s*4/ })).toHaveAttribute('href', '/medicines')
  expect(screen.getByRole('link', { name: /Скоро истекают/ })).toHaveAttribute('href', '/medicines?filter=attention')
  expect(screen.getByRole('link', { name: /Просрочено\s*1/ })).toHaveAttribute('href', '/medicines?filter=expired')

  await user.click(tile)
  expect(await screen.findByRole('heading', { name: 'Аптечка' })).toBeInTheDocument()
  expect(screen.getByTestId('location').textContent).toBe('/medicines')
})
