/**
 * Alert queue item card.
 * Shows alert type, source ID, status, and firewall flag indicator.
 */
export default function AlertCard({ alert, isSelected, isStreaming, firewallFlagged, onClick }) {
  const statusColor = {
    pending: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30',
    in_review: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30',
    closed: 'text-slate-400 bg-slate-800/50 border-slate-700/30',
  }

  return (
    <div
      onClick={onClick}
      className={`px-3 py-2.5 rounded-lg border cursor-pointer transition-all duration-200 ${
        isSelected
          ? 'border-emerald-500/50 bg-emerald-950/20 glow-green'
          : isStreaming
          ? 'border-cyan-500/30 bg-cyan-950/10 animate-pulse-glow'
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
    </div>
  )
}
