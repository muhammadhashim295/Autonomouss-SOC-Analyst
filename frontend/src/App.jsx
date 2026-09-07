import { Routes, Route } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import Dashboard from './pages/Dashboard'
import Orchestration from './pages/Orchestration'
import { AuthProvider } from './context/AuthContext'
import LoginModal from './components/LoginModal'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/orchestration/:client" element={<Orchestration />} />
      </Routes>
      <LoginModal />
    </AuthProvider>
  )
}

export default App
