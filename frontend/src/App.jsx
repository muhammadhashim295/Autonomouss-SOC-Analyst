import { Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import Dashboard from './pages/Dashboard'
import Orchestration from './pages/Orchestration'
import LoginPage from './pages/LoginPage'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider } from './context/AuthContext'
import LoginModal from './components/LoginModal'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute requireAdmin>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/orchestration"
          element={
            <ProtectedRoute>
              <Orchestration />
            </ProtectedRoute>
          }
        />
        <Route
          path="/orchestration/:client"
          element={
            <ProtectedRoute>
              <Orchestration />
            </ProtectedRoute>
          }
        />
        {/* Fallback unknown routes to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <LoginModal />
    </AuthProvider>
  )
}

export default App
