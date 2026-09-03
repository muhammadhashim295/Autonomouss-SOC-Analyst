/**
 * Alert Queue item card.
 * Renders source alert ID, classification, severity badge, firewall flag indicator,
 * and live processing stage indicator.
 */
export default function AlertCard({ alert, isSelected, isStreaming, firewallFlagged, streamStage, onClick }) {
  const statusColor = {
    pending: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    in_review: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30 animate-pulse',
    closed: 'text-emerald-400/80 bg-emerald-900/20 border-emerald-800/40',
  }

  const stageLabels = {
    liveEnv: 'Ingesting',
    investigation: 'Memory RAG',
    enrichment: '4-Skill Enrich',
    firewall: 'Firewall Check',
    primary: 'Primary Triage',
    secondary: 'Secondary Cross-Check',
    action: 'Impact Gating',
    db: 'Case Persisted',
  }

  // Derive alert severity from alert_type
  const getSeverity = (type) => {
    if (['data_exfiltration', 'lateral_movement', 'malware_detected', 'privilege_escalation'].includes(type)) {
      return { label: 'CRITICAL', color: 'text-red-400 bg-red-500/15 border-red-500/30' }
    }
    if (['brute_force_login', 'phishing_email', 'suspicious_process_execution'].includes(type)) {
      return { label: 'HIGH', color: 'text-amber-400 bg-amber-500/15 border-amber-500/30' }
    }
    return { label: 'MEDIUM', color: 'text-cyan-400 bg-cyan-500/15 border-cyan-500/30' }
  }

  const severity = getSeverity(alert.alert_type)

  return (
    <div
      onClick={onClick}
      className={`p-3 rounded-xl border cursor-pointer transition-all duration-300 relative overflow-hidden group ${
        isSelected
          ? 'border-emerald-500/60 bg-emerald-950/25 glow-green'
          : isStreaming
          ? 'border-cyan-500/40 bg-cyan-950/20'
          : 'border-slate-800/60 bg-slate-900/40 hover:border-slate-700 hover:bg-slate-900/80'
      }`}
    >
      {/* Active selection glow bar on left */}
      {isSelected && (
        <div className="absolute top-0 bottom-0 left-0 w-1 bg-emerald-400 glow-green" />
      )}

      {/* Top Line: Source Alert ID & Status */}
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="font-mono text-xs font-semibold text-slate-200 truncate flex-1 group-hover:text-cyan-300 transition-colors">
          {alert.source_alert_id || alert.id?.slice(0, 10)}
        </span>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {firewallFlagged && (
            <span
              className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold text-red-400 bg-red-500/20 border border-red-500/40 glow-red animate-pulse"
              title="Log-poisoning firewall flagged injection attempt"
            >
              ⚠ POISON
            </span>
          )}

          <span className={`text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase ${statusColor[alert.status] || statusColor.pending}`}>
            {alert.status?.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Middle Line: Alert Type & Severity */}
      <div className="flex items-center justify-between gap-2 text-xs font-mono">
        <span className="text-slate-400 truncate flex-1" title={alert.alert_type}>
          {alert.alert_type?.replace(/_/g, ' ')}
        </span>
        <span className={`text-[9px] font-semibold px-1.5 py-0.2 rounded border ${severity.color}`}>
          {severity.label}
        </span>
      </div>

      {/* Pipeline stage indicator for streaming alerts */}
      {streamStage && (
        <div className="flex items-center gap-2 mt-2 pt-2 border-t border-slate-800/40">
          <div className="relative flex items-center justify-center">
            <div className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
            <div className="absolute w-3 h-3 rounded-full bg-cyan-400/50 animate-ping" />
          </div>
          <span className="text-[11px] font-mono text-cyan-300 font-medium">
            {stageLabels[streamStage] || streamStage}
          </span>
        </div>
      )}
    </div>
  )
}
