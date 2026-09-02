/**
 * Stage detail panels — shows Investigation, Enrichment, and Firewall
 * data with structured when/where/why/how reasoning.
 *
 * Renders below the flow diagram for the currently focused alert.
 * Only visible once the respective stage has data.
 */
export default function StageDetail({ stages, enrichmentData, memoryData, firewallFlags, alert }) {
  const hasInvestigation = stages.investigation === 'complete' && memoryData?.length > 0
  const hasEnrichment = stages.enrichment === 'complete' && enrichmentData
  const hasFirewall = stages.firewall === 'complete'

  if (!hasInvestigation && !hasEnrichment && !hasFirewall) return null

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
      {/* ── Investigation / Memory ── */}
      {hasInvestigation && (
        <Panel title="Investigation" icon="⚙" accent="cyan">
          <InfoRow label="WHEN" value={alert?.received_at
            ? new Date(alert.received_at).toLocaleString() : '—'} color="cyan" />
          <InfoRow label="ALERT TYPE" value={alert?.alert_type} color="cyan" />
          <div className="mt-2">
            <div className="text-xs font-mono text-cyan-500 mb-1.5">Similar Cases Retrieved</div>
            {memoryData.map((c, i) => (
              <div key={i} className="text-xs font-mono text-slate-400 ml-2 py-0.5">
                • {typeof c === 'string' ? c : c.id?.slice(0, 8) || JSON.stringify(c).slice(0, 40)}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* ── Enrichment ── */}
      {hasEnrichment && (
        <Panel title="Enrichment" icon="⊕" accent="emerald">
          {/* OTX Threat Intel */}
          {enrichmentData.otx_enrichment && (
            <DetailBlock label="WHERE — Threat Intel (OTX)">
              <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap leading-relaxed">
                {typeof enrichmentData.otx_enrichment === 'string'
                  ? enrichmentData.otx_enrichment
                  : JSON.stringify(enrichmentData.otx_enrichment, null, 2)}
              </pre>
            </DetailBlock>
          )}

          {/* MITRE ATT&CK Mapping */}
          {enrichmentData.attack_mapping && (
            <DetailBlock label="HOW — MITRE ATT&CK Mapping">
              <pre className="text-xs font-mono text-emerald-400/80 whitespace-pre-wrap leading-relaxed">
                {typeof enrichmentData.attack_mapping === 'string'
                  ? enrichmentData.attack_mapping
                  : JSON.stringify(enrichmentData.attack_mapping, null, 2)}
              </pre>
            </DetailBlock>
          )}

          {/* Log Correlation */}
          {enrichmentData.log_correlation && (
            <DetailBlock label="WHY — Log Correlation">
              <pre className="text-xs font-mono text-slate-400 whitespace-pre-wrap leading-relaxed">
                {typeof enrichmentData.log_correlation === 'string'
                  ? enrichmentData.log_correlation
                  : JSON.stringify(enrichmentData.log_correlation, null, 2)}
              </pre>
            </DetailBlock>
          )}

          {/* Behavioral Deviation */}
          {enrichmentData.behavioral_deviation && (
            <DetailBlock label="WHAT — Behavioral Deviation">
              <pre className="text-xs font-mono text-yellow-400/80 whitespace-pre-wrap leading-relaxed">
                {typeof enrichmentData.behavioral_deviation === 'string'
                  ? enrichmentData.behavioral_deviation
                  : JSON.stringify(enrichmentData.behavioral_deviation, null, 2)}
              </pre>
            </DetailBlock>
          )}

          {/* Impact Level */}
          {enrichmentData.impact_level && (
            <InfoRow label="IMPACT" value={enrichmentData.impact_level.toUpperCase()} color="yellow" />
          )}
        </Panel>
      )}

      {/* ── Firewall ── */}
      {hasFirewall && (
        <Panel
          title="Firewall"
          icon="◈"
          accent={firewallFlags?.length > 0 ? 'red' : 'emerald'}
        >
          {firewallFlags?.length > 0 ? (
            <>
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 rounded-full bg-red-500 glow-red" />
                <span className="text-xs font-mono text-red-400">
                  {firewallFlags.length} FLAG(S) DETECTED
                </span>
              </div>
              {firewallFlags.map((flag, i) => (
                <div key={i} className="mb-2 ml-2">
                  <div className="text-xs font-mono text-red-400">{flag.flag_reason}</div>
                  {flag.raw_snippet && (
                    <pre className="text-xs font-mono text-slate-500 mt-0.5 whitespace-pre-wrap">
                      {flag.raw_snippet.slice(0, 120)}
                    </pre>
                  )}
                </div>
              ))}
            </>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400" />
                <span className="text-xs font-mono text-emerald-400">PASSED — No threats detected</span>
              </div>
              <p className="text-xs font-mono text-slate-600 mt-2">
                Log payload sanitized and cleared by injection-detection filters.
              </p>
            </>
          )}
        </Panel>
      )}
    </div>
  )
}

/* ── Sub-components ── */

function Panel({ title, icon, accent = 'slate', children }) {
  const borderColors = {
    cyan: 'border-cyan-500/25',
    emerald: 'border-emerald-500/25',
    red: 'border-red-500/25',
    yellow: 'border-yellow-500/25',
    slate: 'border-slate-700/40',
  }
  const textColors = {
    cyan: 'text-cyan-400',
    emerald: 'text-emerald-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    slate: 'text-slate-400',
  }

  return (
    <div className={`rounded-lg border ${borderColors[accent]} bg-slate-950/60 overflow-hidden`}>
      <div className="px-3 py-2 border-b border-slate-800/40 flex items-center gap-2">
        <span className={textColors[accent]}>{icon}</span>
        <span className={`text-xs font-mono ${textColors[accent]} uppercase tracking-wider`}>{title}</span>
      </div>
      <div className="p-3 space-y-2">{children}</div>
    </div>
  )
}

function DetailBlock({ label, children }) {
  return (
    <div className="mb-2">
      <div className="text-xs font-mono text-slate-500 mb-1">{label}</div>
      {children}
    </div>
  )
}

function InfoRow({ label, value, color = 'slate' }) {
  const textColors = {
    cyan: 'text-cyan-400',
    emerald: 'text-emerald-400',
    red: 'text-red-400',
    yellow: 'text-yellow-400',
    slate: 'text-slate-400',
  }
  if (!value) return null
  return (
    <div className="flex gap-2 text-xs font-mono">
      <span className="text-slate-600">{label}:</span>
      <span className={textColors[color]}>{value}</span>
    </div>
  )
}
