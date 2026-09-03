import { useState } from 'react'

/**
 * Deep Inspection Drawer.
 * Renders tabbed view for Raw Payload, OTX Threat Intel, Log Correlation,
 * RAG Memory Store Retrieval, and Firewall Audit Flags.
 */
export default function StageDetail({ stages, enrichmentData, memoryData, firewallFlags, alert }) {
  const [activeTab, setActiveTab] = useState('enrichment') // 'payload' | 'enrichment' | 'memory' | 'firewall'

  const hasInvestigation = memoryData && memoryData.length > 0
  const hasEnrichment = !!enrichmentData
  const hasFirewall = !!firewallFlags

  if (!hasInvestigation && !hasEnrichment && !hasFirewall && !alert) return null

  return (
    <div className="glass-panel rounded-2xl p-5 border-emerald-500/20 space-y-4">
      
      {/* Header & Tabs */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          <h3 className="font-display font-bold text-xs uppercase tracking-wider text-slate-200">
            Deep Signal Inspection & Evidence Audit
          </h3>
        </div>

        {/* Tab Selection */}
        <div className="flex gap-1.5 font-mono text-xs">
          <TabButton
            label="4-SKILL ENRICHMENT"
            active={activeTab === 'enrichment'}
            onClick={() => setActiveTab('enrichment')}
            badge={hasEnrichment ? '✓' : null}
          />
          <TabButton
            label="RAW PAYLOAD"
            active={activeTab === 'payload'}
            onClick={() => setActiveTab('payload')}
          />
          <TabButton
            label="RAG MEMORY STORE"
            active={activeTab === 'memory'}
            onClick={() => setActiveTab('memory')}
            badge={memoryData?.length ? memoryData.length : null}
          />
          <TabButton
            label="FIREWALL AUDIT"
            active={activeTab === 'firewall'}
            onClick={() => setActiveTab('firewall')}
            badge={firewallFlags?.length ? firewallFlags.length : 0}
            isAlert={firewallFlags?.length > 0}
          />
        </div>
      </div>

      {/* Tab 1: 4-Skill Enrichment */}
      {activeTab === 'enrichment' && (
        <div className="animate-fade-in space-y-4">
          {!enrichmentData ? (
            <div className="py-8 text-center text-xs font-mono text-slate-500">
              Enrichment skills running... (OTX IOC, ATT&CK, Log Correlation, Deviation)
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              
              {/* OTX Threat Intel */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-950/60">
                <div className="text-xs font-mono font-semibold text-cyan-400 mb-2 flex items-center justify-between">
                  <span>🌐 OTX Threat Intel Enrichment</span>
                  <span className="text-[10px] text-slate-500">AlienVault API</span>
                </div>
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  {typeof enrichmentData.otx_enrichment === 'string'
                    ? enrichmentData.otx_enrichment
                    : JSON.stringify(enrichmentData.otx_enrichment, null, 2)}
                </pre>
              </div>

              {/* MITRE ATT&CK Mapping */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-950/60">
                <div className="text-xs font-mono font-semibold text-emerald-400 mb-2 flex items-center justify-between">
                  <span>🎯 MITRE ATT&CK Matrix Mapping</span>
                  <span className="text-[10px] text-slate-500">Taxonomy Lookup</span>
                </div>
                <pre className="text-xs font-mono text-emerald-300/90 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  {typeof enrichmentData.attack_mapping === 'string'
                    ? enrichmentData.attack_mapping
                    : JSON.stringify(enrichmentData.attack_mapping, null, 2)}
                </pre>
              </div>

              {/* Log Correlation */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-950/60">
                <div className="text-xs font-mono font-semibold text-amber-400 mb-2 flex items-center justify-between">
                  <span>🔗 Log & Anomaly Correlation</span>
                  <span className="text-[10px] text-slate-500">Event Graph</span>
                </div>
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  {typeof enrichmentData.log_correlation === 'string'
                    ? enrichmentData.log_correlation
                    : JSON.stringify(enrichmentData.log_correlation, null, 2)}
                </pre>
              </div>

              {/* Behavioral Deviation */}
              <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-950/60">
                <div className="text-xs font-mono font-semibold text-purple-400 mb-2 flex items-center justify-between">
                  <span>📊 Behavioral Deviation Heuristic</span>
                  <span className="text-[10px] text-slate-500">Baseline Score</span>
                </div>
                <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                  {typeof enrichmentData.behavioral_deviation === 'string'
                    ? enrichmentData.behavioral_deviation
                    : JSON.stringify(enrichmentData.behavioral_deviation, null, 2)}
                </pre>
              </div>

            </div>
          )}
        </div>
      )}

      {/* Tab 2: Raw Payload */}
      {activeTab === 'payload' && (
        <div className="animate-fade-in">
          <div className="p-4 rounded-xl border border-slate-800/80 bg-slate-950/60">
            <div className="text-xs font-mono font-semibold text-slate-400 mb-2 flex items-center justify-between">
              <span>Raw JSON Ingestion Payload</span>
              <span className="text-[10px] text-slate-500">Source: {alert?.source_alert_id}</span>
            </div>
            <pre className="text-xs font-mono text-cyan-300/90 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto bg-slate-900/80 p-3 rounded-lg border border-slate-800">
              {JSON.stringify(alert?.raw_payload || {}, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Tab 3: RAG Memory Store */}
      {activeTab === 'memory' && (
        <div className="animate-fade-in space-y-3">
          {!memoryData || memoryData.length === 0 ? (
            <div className="py-8 text-center text-xs font-mono text-slate-500">
              No similar past cases retrieved for this alert type.
            </div>
          ) : (
            <div className="space-y-3">
              <div className="text-xs font-mono text-slate-400 flex items-center justify-between">
                <span>Retrieved Similar Cases ({memoryData.length})</span>
                <span className="text-[10px] text-purple-400">Analyst Corrections Boosted (+5)</span>
              </div>
              {memoryData.map((record, i) => {
                const isCorrection = record.record_type === 'correction' || !!record.analyst_correction
                return (
                  <div
                    key={i}
                    className={`p-3.5 rounded-xl border transition-all ${
                      isCorrection
                        ? 'border-purple-500/40 bg-purple-950/20 glow-purple'
                        : 'border-slate-800 bg-slate-950/60'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-bold text-white">
                          {record.source_alert_id || `Case #${i + 1}`}
                        </span>
                        {isCorrection && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40">
                            🧠 ANALYST CORRECTION (+5 WEIGHT)
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] font-mono text-cyan-400">
                        Score: {record.similarity_score || 5}
                      </span>
                    </div>

                    {record.reasoning && (
                      <p className="text-xs font-mono text-slate-300 leading-relaxed mb-2 line-clamp-2">
                        {record.reasoning}
                      </p>
                    )}

                    {record.analyst_correction && (
                      <div className="p-2 rounded bg-purple-950/40 border border-purple-500/30 text-xs font-mono text-purple-200 mb-2">
                        <span className="font-bold">Analyst Guidance: </span>
                        {record.analyst_correction}
                      </div>
                    )}

                    <div className="flex items-center gap-4 text-[10px] font-mono text-slate-500 pt-1 border-t border-slate-800/40">
                      <span>Verdict: <span className="text-slate-300">{record.verdict}</span></span>
                      <span>Action: <span className="text-slate-300">{record.action_taken || 'none'}</span></span>
                      <span>Date: <span className="text-slate-300">{record.closed || '—'}</span></span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Firewall Audit */}
      {activeTab === 'firewall' && (
        <div className="animate-fade-in">
          {firewallFlags && firewallFlags.length > 0 ? (
            <div className="space-y-3">
              <div className="p-3 rounded-xl border border-red-500/40 bg-red-950/20 glow-red">
                <div className="flex items-center gap-2 text-xs font-mono font-bold text-red-400 mb-1">
                  <span>⚠ LOG-POISONING FIREWALL FLAGGED INJECTION ATTEMPT</span>
                </div>
                <p className="text-xs font-mono text-slate-300">
                  Suspicious embedded instructions detected in raw payload. Alert was sanitized and flagged before reaching agent context.
                </p>
              </div>

              {firewallFlags.map((flag, i) => (
                <div key={i} className="p-3 rounded-xl border border-slate-800 bg-slate-950/60 font-mono text-xs">
                  <div className="text-red-400 font-semibold mb-1 flex items-center justify-between">
                    <span>Reason: {flag.flag_reason}</span>
                    <span className="text-slate-500 text-[10px]">{flag.created_at ? new Date(flag.created_at).toLocaleTimeString() : '—'}</span>
                  </div>
                  {flag.raw_snippet && (
                    <pre className="p-2 rounded bg-slate-900 text-[11px] text-slate-400 whitespace-pre-wrap border border-slate-800 mt-1">
                      {flag.raw_snippet}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="p-4 rounded-xl border border-emerald-500/30 bg-emerald-950/15 text-xs font-mono text-emerald-400 flex items-center gap-3">
              <div className="w-3 h-3 rounded-full bg-emerald-400" />
              <div>
                <div className="font-bold">PASSED LOG FIREWALL SANITIZATION</div>
                <div className="text-slate-400 text-[11px] mt-0.5">No prompt-injection signatures, role-play mimicry, or encoding anomalies detected.</div>
              </div>
            </div>
          )}
        </div>
      )}

    </div>
  )
}

function TabButton({ label, active, onClick, badge, isAlert }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg transition-all duration-200 flex items-center gap-1.5 cursor-pointer ${
        active
          ? isAlert
            ? 'bg-red-500/20 text-red-300 border border-red-500/40 font-bold glow-red'
            : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold glow-green'
          : 'text-slate-400 hover:text-slate-200 border border-transparent'
      }`}
    >
      <span>{label}</span>
      {badge !== null && badge !== undefined && (
        <span className={`px-1.5 py-0.2 rounded text-[10px] ${
          isAlert ? 'bg-red-500/30 text-red-200' : 'bg-emerald-500/30 text-emerald-200'
        }`}>
          {badge}
        </span>
      )}
    </button>
  )
}
