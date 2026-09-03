import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { startLiveFeed } from '../utils/api'

const clients = [
  {
    name: 'UBL Digital Bank',
    shortName: 'UBL',
    sector: 'FINANCIAL SECTOR',
    description: 'United Bank Limited — SBP Regulated Core Banking Infrastructure',
    code: 'UBL-FIN-SEC01',
    assets: '1,420 Endpoints • 4 DCs',
    compliance: 'State Bank Compliance Enforced',
    status: 'ACTIVE MONITORING',
  },
  {
    name: 'Indus Health Network',
    shortName: 'Indus Hospital',
    sector: 'HEALTHCARE SECTOR',
    description: 'Indus Hospital & Health Network — Patient Data & EMR Infrastructure',
    code: 'IHHN-HLT-SEC02',
    assets: '850 Endpoints • EMR Core',
    compliance: 'HIPAA & Local Health Regulations',
    status: 'ACTIVE MONITORING',
  },
  {
    name: 'Sindh Madressatul Islam',
    shortName: 'SMIU',
    sector: 'EDUCATION SECTOR',
    description: 'Sindh Madressatul Islam University — Academic Research & Student Portal',
    code: 'SMIU-EDU-SEC03',
    assets: '520 Endpoints • Cloud LMS',
    compliance: 'HEC IT Security Standards',
    status: 'ACTIVE MONITORING',
  },
]

export default function Dashboard() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(null)
  const [error, setError] = useState(null)

  const handleTrack = async (client) => {
    setLoading(client.shortName)
    setError(null)
    try {
      await startLiveFeed()
      navigate(`/orchestration/${client.shortName.toLowerCase().replace(/\s+/g, '-')}`)
    } catch (err) {
      setError(err.message)
      setLoading(null)
    }
  }

  return (
    <div className="min-h-screen bg-[#04070d] cyber-grid-bg flex flex-col items-center justify-center p-6 relative overflow-hidden">
      
      {/* Background Ambient Glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[350px] bg-emerald-500/10 blur-[140px] pointer-events-none rounded-full" />
      <div className="absolute bottom-10 right-10 w-[400px] h-[300px] bg-cyan-500/10 blur-[120px] pointer-events-none rounded-full" />

      {/* Header Badge & Title */}
      <div className="text-center max-w-3xl mb-12 animate-slide-in relative z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-xs font-mono mb-4 glow-green">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>Alibaba Cloud AI Hackathon 2026</span>
        </div>

        <h1 className="font-display text-4xl md:text-5xl font-extrabold text-white tracking-tight mb-3">
          Autonomous <span className="text-emerald-400 text-glow-green">SOC Analyst</span> Command Center
        </h1>
        <p className="text-slate-400 font-mono text-sm max-w-xl mx-auto leading-relaxed">
          Explainable two-tier multi-agent framework with log-poisoning defense, per-agent IAM scoping, and hard human-in-the-loop escalation rules.
        </p>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="mb-8 px-5 py-3 border border-red-500/40 bg-red-500/15 rounded-xl text-red-400 text-xs font-mono glow-red max-w-xl w-full flex items-center justify-between">
          <span>⚠ {error}</span>
          <button onClick={() => setError(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* Client Command Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 max-w-6xl w-full relative z-10">
        {clients.map((client, i) => (
          <div
            key={client.shortName}
            className="animate-slide-up"
            style={{ animationDelay: `${i * 0.12}s` }}
          >
            <div className="glass-panel glass-panel-hover rounded-2xl p-6 flex flex-col justify-between h-full relative overflow-hidden group">
              
              {/* Top Bar: Sector & Code */}
              <div>
                <div className="flex items-center justify-between gap-2 mb-4">
                  <span className="px-2.5 py-0.5 rounded-md text-[11px] font-mono font-semibold text-emerald-400 bg-emerald-500/15 border border-emerald-500/30">
                    {client.sector}
                  </span>
                  <span className="text-[11px] font-mono text-slate-500">{client.code}</span>
                </div>

                {/* Title & Description */}
                <h2 className="font-display text-2xl font-bold text-white mb-2 group-hover:text-emerald-300 transition-colors">
                  {client.name}
                </h2>
                <p className="text-xs text-slate-400 font-mono leading-relaxed mb-6">
                  {client.description}
                </p>
              </div>

              {/* Status & Action Footer */}
              <div>
                <div className="space-y-2 py-3 border-t border-b border-slate-800/80 mb-6 text-xs font-mono">
                  <div className="flex justify-between text-slate-400">
                    <span>Monitored Scope:</span>
                    <span className="text-cyan-400 font-semibold">{client.assets}</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Governance:</span>
                    <span className="text-slate-300">{client.compliance}</span>
                  </div>
                  <div className="flex justify-between items-center text-slate-400 pt-1">
                    <span>Status:</span>
                    <span className="flex items-center gap-1.5 text-emerald-400 font-semibold">
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                      {client.status}
                    </span>
                  </div>
                </div>

                {/* Track Button */}
                <button
                  onClick={() => handleTrack(client)}
                  disabled={loading === client.shortName}
                  className={`w-full py-3 rounded-xl font-mono text-xs font-bold border transition-all duration-300 flex items-center justify-center gap-2 cursor-pointer ${
                    loading === client.shortName
                      ? 'border-emerald-500/40 bg-emerald-500/20 text-emerald-300 cursor-wait'
                      : 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/25 hover:border-emerald-400 glow-green'
                  }`}
                >
                  {loading === client.shortName ? (
                    <>
                      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
                      INITIALIZING COMMAND FEED...
                    </>
                  ) : (
                    <>
                      <span>LAUNCH COMMAND CENTER</span>
                      <span className="group-hover:translate-x-1 transition-transform">→</span>
                    </>
                  )}
                </button>
              </div>

            </div>
          </div>
        ))}
      </div>

      {/* Operational Highlights Footer */}
      <div className="mt-12 text-center relative z-10">
        <div className="flex flex-wrap justify-center items-center gap-6 text-xs font-mono text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="text-emerald-400">✓</span> Log-Poisoning Firewall Active
          </span>
          <span className="text-slate-700">•</span>
          <span className="flex items-center gap-1.5">
            <span className="text-emerald-400">✓</span> Enforced IAM Permission Scopes
          </span>
          <span className="text-slate-700">•</span>
          <span className="flex items-center gap-1.5">
            <span className="text-emerald-400">✓</span> RAG Memory Learning (+5 Correction Boost)
          </span>
        </div>
      </div>

    </div>
  )
}
