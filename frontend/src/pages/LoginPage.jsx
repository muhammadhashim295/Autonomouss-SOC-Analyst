import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * LoginPage — Dedicated, Ultra-Clean Enterprise Authentication Portal for PAKSEC
 *
 * Minimalist, distraction-free cyber-dark login experience:
 * - Enterprise IAM credentials (email & password)
 * - Show/Hide password toggle
 * - Active session detection & status
 * - Subtle ambient glow & grid styling
 */
export default function LoginPage() {
  const navigate = useNavigate()
  const { login, currentUser, logout, error, setError } = useAuth()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const handleManualSubmit = async (e) => {
    e.preventDefault()
    const cleanEmail = email.trim()
    const cleanPassword = password.trim()
    if (!cleanEmail || !cleanPassword) return
    setSubmitting(true)
    setError(null)
    try {
      const user = await login(cleanEmail, cleanPassword)
      if (user?.role === 'client' && user?.org_code) {
        navigate(`/orchestration/${user.org_code.toLowerCase()}`)
      } else {
        navigate('/dashboard')
      }
    } catch (_) {
      // Error is set in AuthContext
    } finally {
      setSubmitting(false)
    }
  }

  const handleContinueSession = () => {
    if (currentUser?.role === 'client' && currentUser?.org_code) {
      navigate(`/orchestration/${currentUser.org_code.toLowerCase()}`)
    } else {
      navigate('/dashboard')
    }
  }

  return (
    <div className="min-h-screen bg-[#02050b] text-slate-100 font-sans flex flex-col justify-between relative overflow-x-hidden selection:bg-emerald-500/30 selection:text-emerald-300">
      
      {/* ── Background Subtle Tech Pattern & Ambient Glows ── */}
      <div 
        className="absolute inset-0 pointer-events-none opacity-40"
        style={{
          backgroundImage: 'radial-gradient(rgba(255, 255, 255, 0.08) 1px, transparent 1px)',
          backgroundSize: '28px 28px',
        }}
      />
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {/* Soft top-center emerald aura */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[650px] h-[500px] bg-gradient-to-b from-emerald-500/10 via-teal-500/5 to-transparent rounded-full blur-[140px]" />
        {/* Deep cyan subtle corner accent */}
        <div className="absolute bottom-10 right-10 w-[400px] h-[400px] bg-cyan-500/5 rounded-full blur-[120px]" />
      </div>

      {/* ── Top Header Bar ── */}
      <header className="max-w-7xl mx-auto w-full px-4 sm:px-8 py-6 flex items-center justify-between relative z-10">
        
        {/* Brand Logo Link */}
        <Link to="/" className="flex items-center gap-3 group">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-[0_0_15px_rgba(16,185,129,0.35)] group-hover:shadow-[0_0_24px_rgba(16,185,129,0.55)] transition-all">
            <span className="font-mono font-black text-white text-xs tracking-wider">PS</span>
          </div>
          <div className="flex flex-col">
            <span className="font-display font-extrabold text-base tracking-wider text-white group-hover:text-emerald-400 transition-colors">
              PAKSEC
            </span>
            <span className="text-[10px] font-mono text-slate-400 -mt-0.5 tracking-tight">
              Autonomous SOC Analyst
            </span>
          </div>
        </Link>

        {/* Return to Public Portal */}
        <div className="flex items-center gap-3">
          <Link
            to="/"
            className="text-xs font-mono text-slate-400 hover:text-white transition-colors flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900/60 hover:bg-slate-800"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span>Public Portal</span>
          </Link>
        </div>
      </header>

      {/* ── Centered Clean Login Container ── */}
      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 relative z-10 my-auto">
        <div className="w-full max-w-[440px] bg-[#070c18]/90 backdrop-blur-2xl border border-white/10 rounded-3xl shadow-[0_20px_70px_rgba(0,0,0,0.85),0_0_40px_rgba(16,185,129,0.06)] p-6 sm:p-8 relative overflow-hidden">
          
          {/* Subtle Top Gradient Accent */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-emerald-400 to-transparent" />

          {/* Heading Icon & Title */}
          <div className="text-center mb-7 space-y-2">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.2)] mb-1">
              <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white font-display tracking-tight">
              Enterprise Enclave Access
            </h1>
            
            <p className="text-xs text-slate-400 font-sans max-w-xs mx-auto">
              Enter your enterprise credentials to access your secure enclave.
            </p>
          </div>

          {/* Error Alert Banner */}
          {error && (
            <div className="mb-5 p-3 rounded-xl bg-red-950/40 border border-red-500/40 text-red-300 text-xs font-mono flex items-center justify-between">
              <div className="flex items-center gap-2">
                <svg className="w-4 h-4 text-red-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>{error}</span>
              </div>
              <button
                onClick={() => setError(null)}
                className="text-red-400 hover:text-white ml-2 cursor-pointer text-sm"
              >
                ✕
              </button>
            </div>
          )}

          {/* Active Session Notification (if already logged in) */}
          {currentUser && (
            <div className="mb-6 p-3.5 rounded-2xl bg-emerald-500/10 border border-emerald-500/30 text-xs font-mono space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span className="text-slate-300 font-semibold">Active Session:</span>
                </div>
                <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {currentUser.role === 'admin' ? 'SUPER ADMIN' : currentUser.org_code || 'CLIENT'}
                </span>
              </div>
              <div className="text-slate-400 truncate">
                Signed in as <span className="text-white font-semibold">{currentUser.email}</span>
              </div>
              <div className="flex items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={handleContinueSession}
                  className="flex-1 py-1.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-[11px] transition-colors flex items-center justify-center gap-1 cursor-pointer"
                >
                  <span>Go to Command Center</span>
                  <span>→</span>
                </button>
                <button
                  type="button"
                  onClick={logout}
                  className="py-1.5 px-3 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-red-400 text-[11px] transition-colors cursor-pointer"
                >
                  Sign Out
                </button>
              </div>
            </div>
          )}

          {/* ── Enterprise Credentials Form ── */}
          <form onSubmit={handleManualSubmit} className="space-y-4">
            
            {/* Email Field */}
            <div className="space-y-1.5">
              <label className="block text-[11px] font-mono text-slate-400">
                ENTERPRISE EMAIL
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
                  </svg>
                </div>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="analyst@ubl.com.pk"
                  required
                  className="w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-800 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/40 transition-all placeholder:text-slate-600"
                />
              </div>
            </div>

            {/* Password Field */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="block text-[11px] font-mono text-slate-400">
                  PASSWORD
                </label>
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="text-[10px] font-mono text-slate-400 hover:text-white transition-colors cursor-pointer flex items-center gap-1"
                >
                  {showPassword ? (
                    <>
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18" />
                      </svg>
                      <span>Hide</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                      </svg>
                      <span>Show</span>
                    </>
                  )}
                </button>
              </div>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-slate-500">
                  <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full pl-10 pr-3.5 py-2.5 bg-slate-900/90 border border-slate-800 rounded-xl text-white font-mono text-xs focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/40 transition-all placeholder:text-slate-600"
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting || !email || !password}
              className="w-full mt-3 py-3 rounded-xl font-semibold text-xs text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 transition-all duration-300 shadow-[0_0_18px_rgba(16,185,129,0.3)] hover:shadow-[0_0_26px_rgba(16,185,129,0.5)] disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer font-mono"
            >
              {submitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>AUTHENTICATING...</span>
                </>
              ) : (
                <>
                  <span>SIGN IN</span>
                  <span>→</span>
                </>
              )}
            </button>

          </form>

        </div>
      </main>

      {/* ── Minimalist Clean Footer ── */}
      <footer className="max-w-7xl mx-auto w-full px-4 sm:px-8 py-5 border-t border-white/5 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono text-slate-400 relative z-10">
        <div className="flex items-center gap-2">
          <span>© 2026 PAKSEC</span>
          <span className="text-slate-800">|</span>
          <span className="text-slate-400">Connecting the Dots Before They Cost You</span>
        </div>

        <div className="flex items-center gap-4 text-[11px]">
          <Link to="/" className="hover:text-white transition-colors">
            Public Overview
          </Link>
        </div>
      </footer>

    </div>
  )
}
