import { screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { expect, it } from 'vitest'
import { server } from '../test/server'
import { ME, renderApp } from '../test/utils'

const family = (id: number, name: string) => ({ id, name, invite_code: 'ABCD1234', role: 'owner', members: [] })

function mockFamilies() {
  server.use(
    http.get('/api/families/:id', ({ params }) => HttpResponse.json(family(Number(params.id), 'Семья Никита'))),
    http.get('/api/families/:id/categories', () => HttpResponse.json([])),
    http.get('/api/families/:id/medicines', () => HttpResponse.json([])),
  )
}

it('новая аптечка создаётся со страницы «Семья» и сразу открывается', async () => {
  mockFamilies()
  let me = { ...ME, own_families_left: null }
  const { user } = renderApp('/family', { me })
  // Отвечаем на /auth/me актуальным списком: после создания его перечитывают.
  server.use(
    http.get('/api/auth/me', () => HttpResponse.json(me)),
    http.post('/api/families', async ({ request }) => {
      const { name } = await request.json() as { name: string }
      me = { ...me, families: [...me.families, { id: 8, name, role: 'owner' }] }
      return HttpResponse.json(family(8, name), { status: 201 })
    }),
  )
  await user.click(await screen.findByRole('button', { name: 'Новая аптечка' }))
  await user.type(screen.getByPlaceholderText('Дача'), 'Дача')
  await user.click(screen.getByRole('button', { name: 'Создать' }))
  expect(await screen.findByRole('button', { name: /Дача/, pressed: true })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Семья Никита/, pressed: false })).toBeInTheDocument()
})

it('в бесплатной версии вторая своя аптечка под замком', async () => {
  mockFamilies()
  let created = false
  server.use(http.post('/api/families', () => { created = true; return HttpResponse.json({}, { status: 201 }) }))
  const { user } = renderApp('/family', { me: { ...ME, own_families_left: 0 } })
  expect(await screen.findByText(/В бесплатной версии одна своя аптечка/)).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: 'Новая аптечка' })[0]).toBeDisabled()
  await user.click(within(screen.getByRole('note')).getByRole('button', { name: 'Новая аптечка' }))
  expect(await screen.findByRole('dialog', { name: 'Доступно в Капсулке Плюс' })).toBeInTheDocument()
  expect(screen.getByText('Несколько своих аптечек')).toBeInTheDocument()
  expect(created).toBe(false)
})

it('при Плюсе потолок своих аптечек показан без предложения купить Плюс', async () => {
  mockFamilies()
  renderApp('/family', { me: { ...ME, own_families_left: 0, plus_active: true } })
  expect(await screen.findByText(/не больше 5 своих аптечек/)).toBeInTheDocument()
  expect(screen.queryByText(/в Капсулке Плюс/)).not.toBeInTheDocument()
})

it('на странице «Аптечка» есть переключатель, когда аптечек несколько', async () => {
  mockFamilies()
  const me = { ...ME, families: [...ME.families, { id: 8, name: 'Дача', role: 'member' as const }] }
  const { user } = renderApp('/medicines', { me })
  const select = await screen.findByRole('combobox', { name: 'Открытая аптечка' })
  await user.selectOptions(select, 'Дача')
  expect(select).toHaveValue('8')
})
