import { MouseEvent } from 'react'
import { usePlan, usePlusSheet } from './plan'

/** Лимит бесплатной версии уже набран: новое добавить нельзя (уже добавленное остаётся). */
export function useLimitReached(name: 'members' | 'medicines'): boolean {
  const { limit, usage } = usePlan()
  const max = limit(name)
  return max !== null && usage(name) >= max
}

/** onClick для ссылок «Добавить лекарство»: при набранном лимите вместо перехода к форме открывает шторку Плюса. */
export function useMedicineLimitGuard() {
  const full = useLimitReached('medicines')
  const open = usePlusSheet()
  return (e: MouseEvent) => {
    if (!full) return
    e.preventDefault()
    open('no_limits')
  }
}
