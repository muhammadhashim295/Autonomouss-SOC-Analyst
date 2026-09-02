import { Routes, Route } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Orchestration from './pages/Orchestration'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/orchestration/:client" element={<Orchestration />} />
    </Routes>
  )
}

export default App
