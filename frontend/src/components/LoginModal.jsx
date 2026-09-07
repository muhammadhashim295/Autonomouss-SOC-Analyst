import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth, PRESET_ACCOUNTS } from '../context/AuthContext'
import { getBaseUrl, setCustomBackendUrl, testBackendHealth } from '../utils/api'

export default function LoginModal() {
  const { isLoginModalOpen, setIsLoginModalOpen, login, quickSwitch, currentUser, logout, error, setError } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // Backend URL configuration
  const [backendUrl, setBackendUrl] = useState(getBaseUrl())
  const [inputUrl, setInputUrl] = useState(getBaseUrl())
  const [isConfigOpen, setIsConfigOpen] = useState(
    !getBaseUrl() && typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'
  )
  const [testingHealth, setTestingHealth] = useState(false)
  const [healthFeedback, setHealthFeedback] = useState(null)

  useEffect(() => {
    const current = getBaseUrl()
    if (!current || current.includes('your-backend')) {
      const live = 'https://autonomouss-soc-analyst.onrender.com'
      setCustomBackendUrl(live)
      setBackendUrl(live)
      setInputUrl(live)
    } else {
      setBackendUrl(current)
      setInputUrl(current)
    }
  }, [isLoginModalOpen])

  if (!isLoginModalOpen) return null

  const handleManualSubmit = async (e) => {
    e.preventDefault()
    if (!email || !password) return
    setSubmitting(true)
    try {
      await login(email, password)
      setIsLoginModalOpen(false)
      navigate('/dashboard')
    } catch (err) {
      // error handled in context
    } finally {
      setSubmitting(false)
    }
  }

  const handleQuickSwitch = async (key) => {
    setSubmitting(true)
    setError(null)
    try {
      await quickSwitch(key)
      setIsLoginModalOpen(false)
      navigate('/dashboard')
    } catch (err) {
      // error handled in context
    } finally {
      setSubmitting(false)
    }
  }

  const handleSaveBackendUrl = async (overrideUrl = null) => {
    setTestingHealth(true)
    setHealthFeedback(null)
    try {
      const raw = (typeof overrideUrl === 'string' ? overrideUrl : inputUrl).trim()
      let clean = raw.replace(/\/$/, '')
      if (!clean.startsWith('http://') && !clean.startsWith('https://')) {
        clean = `https://${clean}`
      }
      if (clean.endsWith('.onrender.')) {
        clean += 'com'
      } else if (clean.endsWith('.onrender')) {
        clean += '.com'
      }
      setInputUrl(clean)
      const health = await testBackendHealth(clean)
      setCustomBackendUrl(clean)
      setBackendUrl(clean)
      setHealthFeedback({
        type: 'success',
        text: `Connected! Backend online (${health.alerts_count || 0} alerts in database)`,
      })
      setTimeout(() => {
        setIsConfigOpen(false)
        setHealthFeedback(null)
      }, 1500)
    } catch (err) {
      setHealthFeedback({
        type: 'error',
        text: `Connection failed: ${err.message}`,
      })
    } finally {
      setTestingHealth(false)
    }
  }

  const handleResetBackendUrl = () => {
    const live = 'https://autonomouss-soc-analyst.onrender.com'
    setCustomBackendUrl(live)
    setInputUrl(live)
    setBackendUrl(live)
    setHealthFeedback({ type: 'info', text: 'Reset to live Render backend.' })
    setTimeout(() => setHealthFeedback(null), 2000)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
      <div className="relative w-full max-w-lg bg-[#070d18] border border-slate-700/80 rounded-2xl shadow-2xl p-6 overflow-hidden max-h-[95vh] overflow-y-auto">
        {/* Glow Header */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-emerald-500 via-cyan-500 to-purple-500" />

        {/* Modal Close Button */}
        <button
          onClick={() => setIsLoginModalOpen(false)}
          className="absolute top-4 right-4 text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
        >
          ✕
        </button>

        {/* Modal Title */}
        <div className="mb-4">
          <div className="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 mb-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            IAM & TENANT AUTHENTICATION
          </div>
          <h2 className="text-xl font-display font-bold text-white tracking-wide">
            Autonomous SOC Access Control
          </h2>
          <p className="text-xs text-slate-400 font-mono mt-1">
            Authenticate to test strict Postgres Row Level Security (RLS) isolation between client organizations.
          </p>
        </div>

        {/* Backend Target Bar */}
        <div className="mb-4 p-2.5 bg-slate-900/90 border border-slate-700/60 rounded-xl">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-[11px] font-mono truncate">
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${backendUrl ? 'bg-emerald-400 shadow-[0_0_8px_#34d399]' : 'bg-amber-400 animate-pulse'}`} />
              <span className="text-slate-400">Backend API:</span>
              <span className="text-emerald-300 font-semibold truncate max-w-[190px]" title={backendUrl || 'Vite Proxy (localhost)'}>
                {backendUrl || '(Vite Proxy - Localhost)'}
              </span>
            </div>
            <button
              type="button"
              onClick={() => setIsConfigOpen(!isConfigOpen)}
              className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 underline cursor-pointer ml-2 flex-shrink-0"
            >
              {isConfigOpen ? 'Hide' : 'Configure URL'}
            </button>
          </div>

          {isConfigOpen && (
            <div className="mt-2.5 pt-2.5 border-t border-slate-800 space-y-2">
              <p className="text-[10px] font-mono text-slate-400">
                Enter your deployed backend URL (e.g. Render/Railway). Saved directly in your browser with zero rebuilds required:
              </p>
              <div className="flex gap-1.5">
                <input
                  type="text"
                  value={inputUrl}
                  onChange={(e) => setInputUrl(e.target.value)}
                  placeholder="https://your-soc-backend.onrender.com"
                  className="flex-1 px-2.5 py-1.5 bg-slate-950 border border-slate-700 rounded-lg text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
                <button
                  type="button"
                  onClick={handleSaveBackendUrl}
                  disabled={testingHealth || !inputUrl}
                  className="px-3 py-1.5 bg-cyan-500/20 border border-cyan-500/40 hover:bg-cyan-500/30 text-cyan-300 rounded-lg text-xs font-mono font-semibold transition disabled:opacity-50 cursor-pointer"
                >
                  {testingHealth ? 'Testing...' : 'Connect'}
                </button>
                <button
                  type="button"
                  onClick={handleResetBackendUrl}
                  className="px-2 py-1.5 bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-mono transition cursor-pointer"
                  title="Reset to default"
                >
                  ↺
                </button>
              </div>
              <div className="flex items-center gap-2 pt-0.5">
                <span className="text-[10px] font-mono text-slate-500">Quick set:</span>
                <button
                  type="button"
                  onClick={() => handleSaveBackendUrl('https://autonomouss-soc-analyst.onrender.com')}
                  className="text-[10px] font-mono text-emerald-400 hover:text-emerald-300 underline cursor-pointer"
                >
                  ⚡ Use Verified Backend (autonomouss-soc-analyst.onrender.com)
                </button>
              </div>
              {healthFeedback && (
                <div className={`text-[10px] font-mono px-2 py-1 rounded ${
                  healthFeedback.type === 'success' ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-500/30' :
                  healthFeedback.type === 'error' ? 'bg-red-950/60 text-red-300 border border-red-500/30' :
                  'bg-slate-800 text-slate-300'
                }`}>
                  {healthFeedback.text}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error Alert */}
        {error && (
          <div className="mb-4 p-3 bg-red-950/40 border border-red-500/40 rounded-xl text-red-300 text-xs font-mono flex items-center justify-between">
            <span>⚠ {error}</span>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-white ml-2">✕</button>
          </div>
        )}

        {/* Current Active Session Bar */}
        {currentUser && (
          <div className="mb-6 p-3 bg-slate-900/80 border border-emerald-500/30 rounded-xl flex items-center justify-between">
            <div className="text-xs font-mono">
              <span className="text-slate-400">Current Session: </span>
              <span className="text-emerald-300 font-bold">{currentUser.email}</span>
              <span className="ml-2 px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 uppercase">
                {currentUser.role}
              </span>
            </div>
            <button
              onClick={logout}
              className="text-xs font-mono text-slate-400 hover:text-red-400 underline cursor-pointer"
            >
              Sign Out
            </button>
          </div>
        )}

        {/* Quick Demo Switcher */}
        <div className="mb-6">
          <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <span>⚡ Instant Demo Switcher (1-Click)</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {PRESET_ACCOUNTS.map((acc) => {
              const isActive = currentUser?.email === acc.email
              return (
                <button
                  key={acc.key}
                  disabled={submitting}
                  onClick={() => handleQuickSwitch(acc.key)}
                  className={`p-2.5 rounded-xl border text-left transition-all flex flex-col justify-between cursor-pointer ${
                    isActive
                      ? 'border-emerald-500 bg-emerald-500/15 shadow-[0_0_15px_rgba(16,185,129,0.2)]'
                      : 'border-slate-800 bg-slate-900/50 hover:bg-slate-800/80 hover:border-slate-600'
                  }`}
                >
                  <div className="flex items-center justify-between w-full mb-1">
                    <span className="text-xs font-display font-semibold text-white truncate">
                      {acc.name}
                    </span>
                    <span
                      className={`text-[9px] font-mono px-1 rounded uppercase ${
                        acc.role === 'admin'
                          ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                          : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                      }`}
                    >
                      {acc.role}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-slate-400 truncate">
                    {acc.email}
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Divider */}
        <div className="relative flex py-2 items-center mb-4">
          <div className="flex-grow border-t border-slate-800"></div>
          <span className="flex-shrink mx-3 text-slate-600 font-mono text-[10px] uppercase tracking-widest">
            or custom credentials
          </span>
          <div className="flex-grow border-t border-slate-800"></div>
        </div>

        {/* Manual Credentials Form */}
        <form onSubmit={handleManualSubmit} className="space-y-3">
          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">
              EMAIL ADDRESS
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="e.g. analyst@ubl.com.pk"
              className="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-emerald-500"
            />
          </div>
          <div>
            <label className="block text-[11px] font-mono text-slate-400 mb-1">
              PASSWORD
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="w-full px-3 py-2 bg-slate-900/90 border border-slate-700 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-emerald-500"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !email || !password}
            className="w-full mt-2 py-2.5 rounded-xl font-mono text-xs font-bold text-emerald-300 bg-emerald-500/20 border border-emerald-500/40 hover:bg-emerald-500/30 transition disabled:opacity-50 cursor-pointer"
          >
            {submitting ? 'AUTHENTICATING...' : 'SIGN IN WITH POSTGREST IAM'}
          </button>
        </form>

        {/* Enterprise Notice - No Signup Option */}
        <div className="mt-4 pt-3 border-t border-slate-800/80 text-center">
          <p className="text-[10px] font-mono text-slate-500 flex items-center justify-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-amber-400" />
            Restricted Enterprise Access • Accounts provisioned by SOC Administrator • Self-service registration disabled
          </p>
        </div>
      </div>
    </div>
  )
}
