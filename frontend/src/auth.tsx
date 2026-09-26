import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, getToken, Me, setToken, setUnauthorizedHandler } from './api'

interface AuthState {
  me: Me | null
  loading: boolean
  familyId: number | null
  setFamilyId: (id: number) => void
  signIn: (token: string, me: Me) => void
  signOut: () => void
  refresh: () => Promise<unknown>
}

const Ctx = createContext<AuthState | null>(null)
const FAMILY_KEY = 'cureme.family'

function readFamily(): number | null {
  try { const v = localStorage.getItem(FAMILY_KEY); return v ? Number(v) : null } catch { return null }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [token, setTok] = useState(getToken())
  const [preferred, setPreferred] = useState<number | null>(readFamily())

  const meQuery = useQuery({
    queryKey: ['me', token],
    queryFn: () => api<Me>('/auth/me'),
    enabled: !!token,
    retry: false,
    staleTime: 60_000,
  })

  const signOut = useCallback(() => {
    setToken(null)
    setTok(null)
    qc.clear()
  }, [qc])

  useEffect(() => { setUnauthorizedHandler(signOut) }, [signOut])

  const signIn = useCallback((t: string, me: Me) => {
    setToken(t)
    qc.setQueryData(['me', t], me)
    setTok(t)
  }, [qc])

  const me = token ? meQuery.data ?? null : null
  const familyId = useMemo(() => {
    if (!me || me.families.length === 0) return null
    return me.families.some(f => f.id === preferred) ? preferred : me.families[0].id
  }, [me, preferred])

  const setFamilyId = useCallback((id: number) => {
    try { localStorage.setItem(FAMILY_KEY, String(id)) } catch { /* ничего */ }
    setPreferred(id)
  }, [])

  const value: AuthState = {
    me,
    loading: !!token && meQuery.isLoading,
    familyId,
    setFamilyId,
    signIn,
    signOut,
    refresh: () => meQuery.refetch(),
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth outside AuthProvider')
  return v
}

/** Путь API внутри текущей семьи: fam('/medicines') → /families/3/medicines */
export function useFamilyPath() {
  const { familyId } = useAuth()
  return (p: string) => `/families/${familyId}${p}`
}
