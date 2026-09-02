/**
 * Top status bar showing live feed stats and system mode.
 */
export default function LiveStatsBar({ feedStatus, stats, mode, onModeToggle }) {
  const isRunning = feedStatus === 'running'

  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800/50 bg-slate-950/80">
      {/* Left: Feed status */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-400 animate-pulse' : 'bg-slate-600'}`} />
          <span className="font-mono text-xs text-slate-400">
            {isRunning ? 'FEED ACTIVE' : 'FEED IDLE'}
          </span>
        </div>
        {stats && isRunning && (
          <>
            <span className="text-slate-800">│</span>
            <span className="font-mono text-xs text-slate-500">
              <span className="text-cyan-400">{stats.alerts_generated}</span>/{stats.total_planned} alerts
            </span>
            <span className="text-slate-800">│</span>
            <span className="font-mono text-xs text-slate-500">
              <span className="text-red-400">{stats.poison_injected}</span> poison
            </span>
            <span className="text-slate-800">│</span>
            <span className="font-mono text-xs text-slate-500">
              <span className="text-yellow-400">{stats.firewall_caught}</span> caught
            </span>
          </>
        )}
      </div>

      {/* Right: Mode toggle */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-xs text-slate-600">MODE:</span>
        <button
          onClick={onModeToggle}
          className={`px-2.5 py-0.5 rounded font-mono text-xs border transition-all ${
            mode === 'agentic'
              ? 'border-emerald-500/30 text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20'
              : 'border-yellow-500/30 text-yellow-400 bg-yellow-500/10 hover:bg-yellow-500/20'
          }`}
        >
          {mode === 'agentic' ? 'AGENTIC' : 'APPROVAL'}
        </button>
      </div>
    </div>
  )
}
