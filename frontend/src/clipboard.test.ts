import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyText } from './clipboard'

const setClipboard = (v: unknown) => Object.defineProperty(navigator, 'clipboard', { value: v, configurable: true })

describe('copyText', () => {
  afterEach(() => { vi.restoreAllMocks(); setClipboard(undefined) })

  it('пишет через Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    setClipboard({ writeText })
    expect(await copyText('http://x/join/ABC')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('http://x/join/ABC')
  })

  it('если API отказал, копирует через textarea и execCommand', async () => {
    setClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) })
    const exec = vi.fn().mockReturnValue(true)
    document.execCommand = exec
    expect(await copyText('ссылка')).toBe(true)
    expect(exec).toHaveBeenCalledWith('copy')
    expect(document.querySelector('textarea')).toBeNull()  // временное поле убрано
  })

  it('без Clipboard API (http, старый браузер) тоже работает', async () => {
    document.execCommand = vi.fn().mockReturnValue(true)
    expect(await copyText('a')).toBe(true)
  })

  it('возвращает false, если копирование невозможно', async () => {
    document.execCommand = vi.fn().mockReturnValue(false)
    expect(await copyText('a')).toBe(false)
  })
})
