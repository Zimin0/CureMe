import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import { useAuth } from './auth'
import { Layout } from './components/Layout'
import { PageLoader } from './components/ui'
import { ClosedGate, ConsentGate, Join, Login, Register, VerifyEmail, VerifyGate } from './pages/Auth'
import { Consent, Privacy, TelegramConsent, Terms } from './pages/Legal'
import { Export } from './pages/Export'
import { Admin } from './pages/Admin'
import { Family } from './pages/Family'
import { Find } from './pages/Find'
import { History } from './pages/History'
import { Home } from './pages/Home'
import { MedicineDetail } from './pages/MedicineDetail'
import { MedicineForm } from './pages/MedicineForm'
import { Medicines } from './pages/Medicines'
import { Scan } from './pages/Scan'
import { Schedule } from './pages/Schedule'
import { NoFamily } from './pages/NoFamily'
import { Plus } from './pages/Plus'
import { versionLabel } from './version'

function Protected() {
  const { me, loading, familyId } = useAuth()
  const loc = useLocation()
  if (loading) return <PageLoader />
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (me.access_blocked) return <ClosedGate />
  if (me.consent_needed) return <ConsentGate />
  if (me.verification_needed) return <VerifyGate />
  if (!familyId) return <NoFamily />
  return <Layout />
}

/** Режим отладки (включается в админке): версия приложения вверху любой страницы. */
function DebugBar() {
  const q = useQuery({ queryKey: ['access'], queryFn: () => api<{ closed: boolean; debug?: boolean }>('/auth/access'), staleTime: 60_000 })
  if (!q.data?.debug) return null
  return <div className="debug-bar" data-testid="debug-bar">{versionLabel()}</div>
}

export default function App() {
  const { me } = useAuth()
  return (
    <>
    <DebugBar />
    <Routes>
      <Route path="/login" element={me ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={me ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/join/:code" element={<Join />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/consent" element={<Consent />} />
      <Route path="/terms" element={<Terms />} />
      <Route path="/consent-telegram" element={<TelegramConsent />} />
      <Route element={<Protected />}>
        <Route index element={<Home />} />
        <Route path="medicines" element={<Medicines />} />
        <Route path="medicines/new" element={<MedicineForm />} />
        <Route path="medicines/:id" element={<MedicineDetail />} />
        <Route path="medicines/:id/edit" element={<MedicineForm />} />
        <Route path="scan" element={<Scan />} />
        <Route path="find" element={<Find />} />
        <Route path="schedule" element={<Schedule />} />
        <Route path="history" element={<History />} />
        <Route path="family" element={<Family />} />
        <Route path="plus" element={<Plus />} />
        <Route path="export" element={<Export />} />
        <Route path="admin" element={<Admin />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  )
}
