/**
 * Alert queue item card.
 * Shows alert type, source ID, status, firewall flag indicator,
 * and current pipeline stage for streaming alerts.
 */
export default function AlertCard({ alert, isSelected, isStreaming, firewallFlagged, streamStage, onClick }) {
  const statusColor = {
    pending: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
    in_review: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
    closed: 'text-slate-400 bg-slate-800/50 border-slate-700/30',
  }

  const stageLabels = {
    liveEnv: 'Starting',
    investigation: 'Memory',
    enrichment: 'Enriching',
    firewall: 'Firewall',
    primary: 'Primary Agent',
    secondary: 'Secondary Agent',
    action: 'Action',
    db: 'Complete',
  }

  return (
    <div
      onClick={onClick}
      className={`px-3 py-2.5 rounded-lg border cursor-pointer transition-all duration-200 ${
        isSelected
          ? 'border-emerald-500/50 bg-emerald-950/20 glow-green'
          : isStreaming
          ? 'border-cyan-500/30 bg-cyan-950/10'
          : 'border-slate-800/50 bg-slate-900/30 hover:border-slate-700/50 hover:bg-slate-900/50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs text-slate-300 truncate flex-1">
          {alert.source_alert_id || alert.id?.slice(0, 8)}
        </span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {firewallFlagged && (
            <span className="w-2 h-2 rounded-full bg-red-500 glow-red" title="Firewall flagged" />
          )}
          {isSelected && (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          )}
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded border ${statusColor[alert.status] || statusColor.pending}`}>
            {alert.status}
          </span>
        </div>
      </div>
      <div className="text-xs text-slate-500 font-mono mt-1 truncate">{alert.alert_type}</div>

      {/* Pipeline stage indicator for streaming alerts */}
      {streamStage && (
        <div className="flex items-center gap-1.5 mt-1.5">
          <div className="w-1 h-1 rounded-full bg-cyan-400 animate-pulse" />
          <span className="text-xs font-mono text-cyan-400/80">{stageLabels[streamStage] || streamStage}</span>
        </div>
      )}
    </div>
  )
}
