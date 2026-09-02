/**
 * Pipeline flow diagram — horizontal connected nodes.
 * Each node lights up as SSE events arrive.
 * Firewall node shows flag badge when the alert was flagged.
 */
export default function FlowDiagram({ stages, firewallFlags }) {
  const nodes = [
    { key: 'liveEnv', label: 'Live Environment', icon: '◉' },
    { key: 'investigation', label: 'Investigation', icon: '⚙' },
    { key: 'enrichment', label: 'Enrichment', icon: '⊕' },
    { key: 'firewall', label: 'Firewall', icon: '◈' },
    { key: 'primary', label: 'Primary Agent', icon: '▣' },
    { key: 'secondary', label: 'Secondary Agent', icon: '◫' },
    { key: 'action', label: 'Action', icon: '⚡' },
    { key: 'db', label: 'Case Filed', icon: '▪' },
  ]

  const getColor = (status) => {
    switch (status) {
      case 'active': return 'border-emerald-500/60 bg-emerald-500/10 glow-green'
      case 'complete': return 'border-emerald-700/40 bg-emerald-900/20'
      case 'error': return 'border-red-500/60 bg-red-500/10 glow-red'
      default: return 'border-slate-800/50 bg-slate-900/30'
    }
  }

  const getIconColor = (status) => {
    switch (status) {
      case 'active': return 'text-emerald-400 text-glow-green'
      case 'complete': return 'text-emerald-600'
      case 'error': return 'text-red-400'
      default: return 'text-slate-600'
    }
  }

  const getLineColor = (status) => {
    return status === 'active' || status === 'complete'
      ? 'bg-emerald-600/40'
      : 'bg-slate-800/50'
  }

  const hasFlags = firewallFlags && firewallFlags.length > 0
  const firewallStatus = hasFlags ? 'error' : stages.firewall

  return (
    <div className="rounded-lg border border-slate-800/50 bg-slate-950/50 p-4">
      <div className="flex items-center gap-2 mb-4">
        <span className="text-xs font-mono text-slate-500 uppercase tracking-wider">Pipeline Flow</span>
      </div>

      <div className="flex items-center justify-between gap-0 overflow-x-auto pb-2">
        {nodes.map((node, i) => {
          const status = node.key === 'firewall' ? firewallStatus : (stages[node.key] || 'pending')

          return (
            <div key={node.key} className="flex items-center flex-shrink-0">
              {/* Node */}
              <div className={`relative flex flex-col items-center px-3 py-2.5 rounded-lg border transition-all duration-500 min-w-[100px] ${getColor(status)}`}>
                <span className={`text-lg mb-1 transition-colors duration-500 ${getIconColor(status)}`}>
                  {node.icon}
                </span>
                <span className={`text-xs font-mono text-center leading-tight ${
                  status === 'active' ? 'text-emerald-300' :
                  status === 'complete' ? 'text-emerald-500/80' :
                  status === 'error' ? 'text-red-400' :
                  'text-slate-600'
                }`}>
                  {node.label}
                </span>

                {/* Firewall flag badge */}
                {node.key === 'firewall' && hasFlags && (
                  <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs font-mono rounded-full w-5 h-5 flex items-center justify-center glow-red">
                    {firewallFlags.length}
                  </span>
                )}

                {/* Active pulse */}
                {status === 'active' && (
                  <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                )}
              </div>

              {/* Connector line */}
              {i < nodes.length - 1 && (
                <div className={`w-6 h-0.5 mx-0.5 flex-shrink-0 transition-colors duration-500 ${
                  getLineColor(stages[nodes[i + 1].key] || 'pending')
                }`} />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
