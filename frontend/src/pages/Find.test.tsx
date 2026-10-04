import { screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { medicine, renderApp } from '../test/utils'

const location = () => screen.getByTestId('location').textContent

it('подбор по болезни: чипсы, результаты, предупреждения', async () => {
  const queries: string[] = []
  server.use(
    http.get('/api/conditions', () => HttpResponse.json(['Головная боль', 'Кашель'])),
    http.get('/api/families/7/suggest', ({ request }) => {
      const q = new URL(request.url).searchParams.get('condition')!
      queries.push(q)
      return HttpResponse.json(q === 'Кашель'
        ? { query: q, results: [], disclaimer: 'Это не медицинский совет' }
        : {
            query: q, disclaimer: 'Это не медицинский совет', results: [
              { medicine: medicine({ id: 1, name: 'Нурофен' }), score: 18, reasons: ['Вам помогает', 'В показаниях: «головная боль»'], warnings: [] },
              { medicine: medicine({ id: 2, name: 'Цитрамон', stock: { ...medicine().stock, total: 0 } }), score: 2, reasons: ['В показаниях: «мигрень»'], warnings: ['Закончилось'] },
            ],
          })
    }),
  )
  const { user } = renderApp('/find')
  await user.click(await screen.findByRole('button', { name: 'Головная боль' }))
  expect(await screen.findByText('Нурофен')).toBeInTheDocument()
  expect(location()).toBe('/find?q=%D0%93%D0%BE%D0%BB%D0%BE%D0%B2%D0%BD%D0%B0%D1%8F+%D0%B1%D0%BE%D0%BB%D1%8C')
  expect(screen.getByText('♥ Вам помогает')).toBeInTheDocument()
  expect(screen.getByText('Закончилось')).toBeInTheDocument()
  expect(screen.getByText('Это не медицинский совет')).toBeInTheDocument()
  const links = screen.getAllByRole('link').filter(a => a.classList.contains('condition-result'))
  expect(links.map(a => a.getAttribute('href'))).toEqual(['/medicines/1', '/medicines/2'])

  await user.clear(screen.getByPlaceholderText('Например: болит голова'))
  await user.type(screen.getByPlaceholderText('Например: болит голова'), '  Кашель  {Enter}')
  expect(await screen.findByText('Для «Кашель» ничего не нашлось')).toBeInTheDocument()
  expect(queries).toEqual(['Головная боль', 'Кашель'])
})

it('слишком короткий запрос не отправляется', async () => {
  server.use(http.get('/api/conditions', () => HttpResponse.json([])))
  const { user } = renderApp('/find')
  await user.type(await screen.findByPlaceholderText('Например: болит голова'), 'a{Enter}')
  await waitFor(() => expect(location()).toBe('/find?q=a'))
  // обработчика /suggest нет: если бы запрос ушёл, MSW уронил бы тест
})

it('предупреждение: коротко на виду, остальное по «Подробнее»', async () => {
  server.use(http.get('/api/conditions', () => HttpResponse.json([])))
  const { user } = renderApp('/find')
  expect(await screen.findByText(/Капсулка не врач и не ставит диагноз/)).toBeInTheDocument()
  expect(screen.queryByText(/Перед приёмом прочитайте инструкцию/)).not.toBeInTheDocument()
  const more = screen.getByRole('button', { name: 'Подробнее' })
  expect(more).toHaveAttribute('aria-expanded', 'false')
  await user.click(more)
  expect(screen.getByText(/Перед приёмом прочитайте инструкцию/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Свернуть' })).toHaveAttribute('aria-expanded', 'true')
})
