import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startLiveFeed } from '../utils/api'

const clients = [
  { name: 'UBL', sector: 'financial', description: 'United Bank Limited' },
  { name: 'Indus Hospital', sector: 'healthcare', description: 'Indus Hospital & Health Network' },
  { name: 'SMIU', sector: 'education', description: 'Sindh Madressatul Islam University' },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(null)
  const [error, setError] = useState(null)

  const handleTrack = async (client) => {
    setLoading(client.name)
    setError(null)
    try {
      await startLiveFeed()
      navigate(`/orchestration/${client.name.toLowerCase()}`)
    } catch (err) {
      setError(err.message)
      setLoading(null)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900">Autonomous SOC Analyst</h1>
          <p className="text-gray-600 mt-2">Select a client to monitor their security environment</p>
        </header>

        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-800">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {clients.map((client) => (
            <div
              key={client.name}
              className="bg-white rounded-lg shadow-md p-6 border border-gray-200 hover:shadow-lg transition-shadow"
            >
              <h2 className="text-xl font-semibold text-gray-900 mb-2">{client.name}</h2>
              <p className="text-sm text-gray-600 mb-4">{client.description}</p>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
                  {client.sector}
                </span>
                <button
                  onClick={() => handleTrack(client)}
                  disabled={loading === client.name}
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                >
                  {loading === client.name ? 'Starting...' : 'Track'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
