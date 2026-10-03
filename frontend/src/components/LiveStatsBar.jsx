/**
 * Top status bar showing live feed stats and pipeline status.
 */
export default function LiveStatsBar({ feedStatus, stats }) {
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
              <span className="text-emerald-400 text-glow-green">LIVE TELEMETRY THREAT FEED</span>
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
              <span className="text-emerald-400 font-semibold">Sovereign Sensor Stream</span>
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

      {/* Right: Pipeline Architecture */}
      <div className="flex items-center gap-2.5 px-3 py-1 rounded-lg bg-slate-950/60 border border-slate-800/80 font-mono text-xs">
        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        <span className="text-slate-300 font-semibold tracking-wider uppercase text-[11px]">Autonomous Dual-Agent Pipeline</span>
      </div>
    </div>
  )
}

