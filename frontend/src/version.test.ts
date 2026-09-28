import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { expect, test } from 'vitest'
import { APP_VERSION, versionLabel } from './version'

test('версия берётся из файла VERSION', () => {
  const file = readFileSync(resolve(__dirname, '../../VERSION'), 'utf8').trim()
  expect(APP_VERSION).toBe(file)
  expect(APP_VERSION).toMatch(/^\d+\.\d+\.\d+$/)
})

test('подпись с коммитом и без', () => {
  expect(versionLabel('1.2.3', 'abc1234')).toBe('Версия 1.2.3 · abc1234')
  expect(versionLabel('1.2.3', '')).toBe('Версия 1.2.3')
})
