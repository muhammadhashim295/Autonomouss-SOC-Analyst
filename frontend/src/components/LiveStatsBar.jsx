/**
 * Top status bar showing live feed stats, active threats, and global agent mode toggle.
 */
export default function LiveStatsBar({ feedStatus, stats, mode, onModeToggle }) {
  const isRunning = feedStatus === 'running'

  return (
    <div className="glass-header px-6 py-2.5 flex items-center justify-between z-30">
      {/* Left: Feed & Threat Metrics */}
      <div className="flex items-center gap-5">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center">
            <div className={`w-2.5 h-2.5 rounded-full ${isRunning ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            {isRunning && (
              <div className="absolute w-4 h-4 rounded-full bg-emerald-400/40 animate-ping" />
            )}
          </div>
          <span className="font-mono text-xs font-semibold uppercase tracking-wider text-slate-300">
            {isRunning ? (
              <span className="text-emerald-400 text-glow-green">LIVE CLOUDFLARE THREAT FEED</span>
            ) : (
              <span className="text-slate-500">FEED STANDBY</span>
            )}
          </span>
        </div>

        {stats && isRunning && (
          <div className="flex items-center gap-4 text-xs font-mono bg-slate-950/60 px-3 py-1 rounded-lg border border-slate-800/80">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Live alerts:</span>
              <span className="text-cyan-400 font-semibold">{stats.alerts_generated}</span>
            </div>

            <span className="text-slate-700">│</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Source:</span>
              <span className="text-emerald-400 font-semibold">Cloudflare AI</span>
            </div>

            <span className="text-slate-700">│</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Cadence:</span>
              <span className="text-cyan-400 font-semibold">{stats.interval_seconds || 3}s</span>
            </div>

            <span className="text-slate-700">│</span>

            <div className="flex items-center gap-1.5">
              <span className="text-slate-500">Firewall Flagged:</span>
              <span className="text-amber-400 font-semibold text-glow-amber">{stats.firewall_caught}</span>
            </div>
          </div>
        )}
      </div>

      {/* Center: System Identity */}
      <div className="flex items-center gap-3">
        <span className="hidden xl:inline text-[11px] font-mono text-slate-500 uppercase tracking-widest">
          Autonomous Cyber SOC Platform
        </span>
      </div>


      {/* Right: Global Agent Mode Switch */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-slate-400 font-medium">OPERATIONAL MODE:</span>
        <button
          onClick={onModeToggle}
          title="Click to toggle between autonomous execution (Agentic) and human analyst review (Approval)"
          className={`group relative px-3 py-1 rounded-lg font-mono text-xs font-semibold border transition-all duration-300 flex items-center gap-2 cursor-pointer ${
            mode === 'agentic'
              ? 'border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 glow-green'
              : 'border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 glow-amber'
          }`}
        >
          <span className={`w-2 h-2 rounded-full ${
            mode === 'agentic' ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-pulse'
          }`} />
          <span>{mode === 'agentic' ? '⚡ AGENTIC MODE' : '🛡 APPROVAL MODE'}</span>
        </button>
      </div>
    </div>
  )
}

