import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startLiveFeed } from '../utils/api'

const clients = [
  { name: 'UBL', sector: 'FINANCIAL', description: 'United Bank Limited', code: 'UBL-SEC' },
  { name: 'Indus Hospital', sector: 'HEALTHCARE', description: 'Indus Hospital & Health Network', code: 'IHHN-SEC' },
  { name: 'SMIU', sector: 'EDUCATION', description: 'Sindh Madressatul Islam University', code: 'SMIU-SEC' },
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
      navigate(`/orchestration/${client.name.toLowerCase().replace(/\s+/g, '-')}`)
    } catch (err) {
      setError(err.message)
      setLoading(null)
    }
  }

  return (
    <div className="min-h-screen bg-[#050705] flex flex-col items-center justify-center p-8">
      {/* Header */}
      <div className="text-center mb-12 animate-fade-in">
        <h1 className="text-3xl font-bold text-white mb-2">
          Autonomous <span className="text-emerald-400 text-glow-green">SOC</span> Analyst
        </h1>
        <p className="text-slate-500 font-mono text-sm">Select a client to begin live monitoring</p>
      </div>

      {error && (
        <div className="mb-6 px-4 py-2 border border-red-500/30 bg-red-500/10 rounded-lg text-red-400 text-sm font-mono">
          {error}
        </div>
      )}

      {/* Client Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-5xl w-full">
        {clients.map((client, i) => (
          <div
            key={client.name}
            className="animate-slide-in"
            style={{ animationDelay: `${i * 0.1}s` }}
          >
            <div className="rounded-lg border border-slate-800/50 bg-slate-950/50 p-6 hover:border-emerald-500/30 hover:bg-slate-900/30 transition-all duration-300 group">
              {/* Sector Badge */}
              <div className="flex items-center justify-between mb-4">
                <span className="px-2 py-0.5 rounded text-xs font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
                  {client.sector}
                </span>
                <span className="text-xs font-mono text-slate-700">{client.code}</span>
              </div>

              {/* Client Name */}
              <h2 className="text-xl font-semibold text-white mb-1">{client.name}</h2>
              <p className="text-sm text-slate-500 mb-6">{client.description}</p>

              {/* Status Indicator */}
              <div className="flex items-center gap-2 mb-4">
                <div className="w-2 h-2 rounded-full bg-emerald-500/50" />
                <span className="text-xs font-mono text-slate-600">System Online</span>
              </div>

              {/* Track Button */}
              <button
                onClick={() => handleTrack(client)}
                disabled={loading === client.name}
                className={`w-full py-2.5 rounded-lg font-mono text-sm border transition-all duration-300 ${
                  loading === client.name
                    ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400 cursor-wait'
                    : 'border-emerald-500/30 bg-emerald-500/5 text-emerald-400 hover:bg-emerald-500/15 hover:border-emerald-500/50 hover:glow-green cursor-pointer'
                }`}
              >
                {loading === client.name ? (
                  <span className="flex items-center justify-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Initializing...
                  </span>
                ) : (
                  'TRACK →'
                )}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-12 text-center">
        <p className="text-xs font-mono text-slate-700">
          Autonomous SOC Analyst Framework — Alibaba Cloud AI Hackathon 2026
        </p>
      </div>
    </div>
  )
}
