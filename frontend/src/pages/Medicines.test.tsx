import { screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

const CATS = [
  { id: 1, name: 'Обезболивающие', icon: '🩹', color: '#e5484d', medicine_count: 2 },
  { id: 2, name: 'Витамины', icon: '🍊', color: '#f5a623', medicine_count: 0 },
]

it('фильтры и поиск уходят в запрос и в адрес страницы', async () => {
  const seen: string[] = []
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json(CATS)),
    http.get('/api/families/7/medicines', ({ request }) => {
      const qs = new URL(request.url).searchParams
      seen.push(qs.toString())
      return HttpResponse.json(qs.get('q') === 'zzz' ? [] : [medicine({ id: 1, name: 'Нурофен' }), medicine({ id: 2, name: 'Пенталгин' })])
    }),
  )
  const { user } = renderApp('/medicines')
  expect(await screen.findByText('2 в списке')).toBeInTheDocument()
  // категории без лекарств не показываем
  expect(screen.getByRole('button', { name: /Обезболивающие/ })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Витамины/ })).not.toBeInTheDocument()

  await user.click(screen.getByRole('button', { name: 'Заканчиваются' }))
  await user.click(screen.getByRole('button', { name: /Обезболивающие/ }))
  await waitFor(() => expect(seen.at(-1)).toBe('filter=low&category_id=1'))
  expect(screen.getByTestId('location').textContent).toBe('/medicines?filter=low&category=1')

  await user.type(screen.getByRole('searchbox'), 'zzz')
  expect(await screen.findByText('Ничего не нашлось')).toBeInTheDocument()
})

it('пустая аптечка предлагает добавить лекарство', async () => {
  server.use(
    http.get('/api/families/7/categories', () => HttpResponse.json([])),
    http.get('/api/families/7/medicines', () => HttpResponse.json([])),
  )
  renderApp('/medicines')
  const empty = (await screen.findByText('Аптечка пустая')).closest('.empty') as HTMLElement
  expect(within(empty).getByRole('link', { name: 'Сканировать' })).toHaveAttribute('href', '/scan')
  expect(within(empty).getByRole('link', { name: 'Вручную' })).toHaveAttribute('href', '/medicines/new')
})
