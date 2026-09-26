import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { useAuth } from './auth'
import { Layout } from './components/Layout'
import { PageLoader } from './components/ui'
import { Join, Login, Register } from './pages/Auth'
import { Family } from './pages/Family'
import { Find } from './pages/Find'
import { Home } from './pages/Home'
import { MedicineDetail } from './pages/MedicineDetail'
import { MedicineForm } from './pages/MedicineForm'
import { Medicines } from './pages/Medicines'
import { Scan } from './pages/Scan'
import { NoFamily } from './pages/NoFamily'

function Protected() {
  const { me, loading, familyId } = useAuth()
  const loc = useLocation()
  if (loading) return <PageLoader />
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />
  if (!familyId) return <NoFamily />
  return <Layout />
}

export default function App() {
  const { me } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={me ? <Navigate to="/" replace /> : <Login />} />
      <Route path="/register" element={me ? <Navigate to="/" replace /> : <Register />} />
      <Route path="/join/:code" element={<Join />} />
      <Route element={<Protected />}>
        <Route index element={<Home />} />
        <Route path="medicines" element={<Medicines />} />
        <Route path="medicines/new" element={<MedicineForm />} />
        <Route path="medicines/:id" element={<MedicineDetail />} />
        <Route path="medicines/:id/edit" element={<MedicineForm />} />
        <Route path="scan" element={<Scan />} />
        <Route path="find" element={<Find />} />
        <Route path="family" element={<Family />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
