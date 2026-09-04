import { useState, useEffect, useMemo } from 'react'
import { getMemoryRecords } from '../utils/api'

/**
 * Interactive RAG Memory Vault & Vector Intelligence Explorer Component
 * Visualizes real pgvector memory records, analyst correction overrides,
 * semantic similarity scores, and live RAG recall intelligence.
 */
export default function MemoryVault({ activeAlert, streamState }) {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedRecord, setSelectedRecord] = useState(null)
  const [filterType, setFilterType] = useState('ALL')
  const [searchQuery, setSearchQuery] = useState('')

  const loadRecords = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = { limit: 100 }
      if (activeAlert?.alert_type) {
        params.alert_type = activeAlert.alert_type
      }
      if (filterType !== 'ALL') {
        params.record_type = filterType.toLowerCase()
      }
      const data = await getMemoryRecords(params)
      setRecords(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRecords()
    // Refresh every 10 seconds to catch new memory writes
    const t = setInterval(loadRecords, 10000)
    return () => clearInterval(t)
  }, [activeAlert?.alert_type, filterType])

  // Merge real records with records currently being retrieved by the active stream
  const allRecords = useMemo(() => {
    const streamRecords = (streamState?.memory || []).map((r) => ({
      ...r,
      _source: 'stream',
      _raw: r,
      id: r.source_alert_id ? `stream-${r.source_alert_id}` : `stream-${Math.random().toString(36).slice(2)}`,
    }))
    const backendRecords = records.map((r) => ({ ...r, _source: 'backend', _raw: r }))
    // Prefer backend records over stream duplicates
    const seen = new Set()
    const merged = []
    for (const r of [...streamRecords, ...backendRecords]) {
      const key = r.id || r.source_alert_id
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(r)
    }
    return merged
  }, [records, streamState?.memory])

  const filteredRecords = allRecords.filter((r) => {
    if (filterType === 'CORRECTION' && r.record_type !== 'correction') return false
    if (filterType === 'CASE' && r.record_type !== 'case') return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      const iocs = Array.isArray(r.iocs) ? r.iocs.join(' ') : String(r.iocs || '')
      const tags = Array.isArray(r.asset_tags) ? r.asset_tags.join(' ') : String(r.asset_tags || '')
      return (
        String(r.id || '').toLowerCase().includes(q) ||
        String(r.source_alert_id || '').toLowerCase().includes(q) ||
        String(r.alert_type || '').toLowerCase().includes(q) ||
        String(r.source_ip || '').toLowerCase().includes(q) ||
        String(iocs).toLowerCase().includes(q) ||
        String(tags).toLowerCase().includes(q) ||
        String(r.analyst_correction || '').toLowerCase().includes(q) ||
        String(r.reasoning || '').toLowerCase().includes(q)
      )
    }
    return true
  })

  const activeRecordObj = selectedRecord ? allRecords.find((r) => r.id === selectedRecord) : null

  // Derived stats from real records
  const totalRecords = allRecords.length
  const correctionCount = allRecords.filter((r) => r.record_type === 'correction').length
  const topConfidence = allRecords.length
    ? Math.max(...allRecords.map((r) => r.confidence || 0))
    : 0

  const mapRecord = (record) => {
    const iocs = Array.isArray(record.iocs) ? record.iocs : []
    const tags = Array.isArray(record.asset_tags) ? record.asset_tags : []
    const isCorrection = record.record_type === 'correction'
    return {
      id: record.id,
      record_type: record.record_type,
      priority_boost: isCorrection ? '1.5x (Analyst Override)' : '1.0x (Standard Case)',
      similarity_score: record.confidence || 0,
      source_alert_id: record.source_alert_id,
      alert_type: record.alert_type,
      target: tags[0] || record.source_ip || 'unknown asset',
      ioc: iocs[0] || record.source_ip || 'none',
      original_verdict: record.verdict,
      analyst_correction: record.analyst_correction || record.reasoning || 'No guidance recorded.',
      created_at: record.created_at,
      embedding_dim: 1536,
      raw: record,
    }
  }

  const mappedRecords = filteredRecords.map(mapRecord)

  return (
    <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6 animate-fade-in relative overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-400 animate-pulse" />
            <h3 className="font-display font-bold text-base text-white tracking-wide">
              RAG MEMORY VAULT & VECTOR INTELLIGENCE EXPLORER
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Vector database storing historical incident embeddings and high-priority analyst corrections for RAG recall.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={loadRecords}
            disabled={loading}
            className="px-4 py-2 rounded-xl font-mono text-xs font-bold bg-purple-500/20 text-purple-300 border border-purple-500/50 hover:bg-purple-500/30 glow-purple transition-all cursor-pointer flex items-center gap-2 disabled:opacity-50"
          >
            <span>{loading ? '↻ REFRESHING...' : '↻ REFRESH VAULT'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-xs font-mono text-red-400">
          ⚠ Failed to load memory records: {error}
        </div>
      )}

      {/* RAG Stat Counters Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCounter label="Total Vectors" value={totalRecords} badge="pgvector" color="cyan" />
        <StatCounter
          label="Analyst Overrides"
          value={correctionCount}
          badge="1.5x Boost"
          color="purple"
        />
        <StatCounter
          label="Records For This Alert Type"
          value={activeAlert?.alert_type ? allRecords.filter((r) => r.alert_type === activeAlert.alert_type).length : '—'}
          badge="Filtered"
          color="emerald"
        />
        <StatCounter
          label="Top Confidence Match"
          value={topConfidence ? `${(topConfidence * 100).toFixed(1)}%` : '—'}
          badge="Active RAG"
          color="cyan"
        />
      </div>

      {/* Filter Tabs & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-2">
          {['ALL', 'CORRECTION', 'CASE'].map((tab) => (
            <button
              key={tab}
              onClick={() => setFilterType(tab)}
              className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all ${
                filterType === tab
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/50 glow-purple'
                  : 'text-slate-500 hover:text-slate-300 border border-slate-800 bg-slate-900/40'
              }`}
            >
              {tab === 'ALL' ? 'ALL VECTORS' : tab === 'CORRECTION' ? '★ ANALYST CORRECTIONS' : 'INCIDENT CASES'}
            </button>
          ))}
        </div>

        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search memory by IOC, target, or keywords..."
          className="w-full sm:w-72 px-3 py-1.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 font-mono focus:border-purple-500 focus:outline-none"
        />
      </div>

      {/* Vector Memory Record Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading && mappedRecords.length === 0 ? (
          <div className="col-span-full text-center py-12 text-slate-500 font-mono text-xs animate-pulse">
            Loading memory vectors...
          </div>
        ) : mappedRecords.length === 0 ? (
          <div className="col-span-full text-center py-12 text-slate-500 font-mono text-xs">
            {searchQuery ? 'No memory records match your search.' : 'No memory records in the vault yet. Cases will be indexed as investigations complete.'}
          </div>
        ) : (
          mappedRecords.map((record) => {
            const isCorrection = record.record_type === 'correction'
            const simPct = (record.similarity_score * 100).toFixed(1)

            return (
              <div
                key={record.id}
                onClick={() => setSelectedRecord(record.id)}
                className={`p-4 rounded-xl border transition-all duration-200 cursor-pointer space-y-3 relative overflow-hidden group ${
                  selectedRecord === record.id
                    ? 'border-purple-500 bg-purple-500/10 glow-purple'
                    : isCorrection
                    ? 'border-purple-500/30 bg-slate-950/80 hover:border-purple-500/50'
                    : 'border-slate-800/80 bg-slate-950/60 hover:border-slate-700'
                }`}
              >
                {/* Card Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                      isCorrection
                        ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                        : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                    }`}>
                      {isCorrection ? '★ ANALYST CORRECTION' : 'CASE RECORD'}
                    </span>
                    <span className="font-mono text-xs text-slate-400 truncate max-w-[120px]">{record.source_alert_id}</span>
                  </div>

                  <div className="flex items-center gap-1 text-xs font-mono font-semibold text-emerald-400">
                    <span>{simPct}% Conf</span>
                  </div>
                </div>

                {/* Targets & IOC Badges */}
                <div className="flex items-center gap-3 text-xs font-mono flex-wrap">
                  <div>
                    <span className="text-slate-500">Target: </span>
                    <span className="text-cyan-400 font-semibold">{record.target}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">IOC: </span>
                    <span className="text-slate-300 font-semibold">{record.ioc}</span>
                  </div>
                </div>

                {/* Analyst Guidance Text */}
                <div className="p-2.5 rounded-lg border border-slate-900 bg-slate-900/60 text-xs font-mono text-slate-300 leading-relaxed line-clamp-2">
                  "{record.analyst_correction}"
                </div>

                {/* Footer Boost Info */}
                <div className="flex items-center justify-between text-[11px] font-mono text-slate-500 pt-1">
                  <span>Weight: {record.priority_boost}</span>
                  <span>{record.created_at ? new Date(record.created_at).toLocaleDateString() : '—'}</span>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Floating Detailed Vector Inspector Drawer */}
      {activeRecordObj && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fade-in">
          <div className="relative w-full max-w-xl overflow-hidden glass-panel border border-purple-500/40 rounded-2xl shadow-2xl glow-purple animate-slide-up p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-purple-400 font-mono text-sm font-bold">VECTOR INSPECTOR</span>
                <span className="text-xs font-mono text-slate-400">[{activeRecordObj.id?.slice(0, 12)}]</span>
              </div>
              <button
                onClick={() => setSelectedRecord(null)}
                className="text-slate-500 hover:text-white font-mono text-sm"
                aria-label="Close inspector"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="grid grid-cols-2 gap-3 p-3 rounded-xl border border-slate-800 bg-slate-950/80">
                <div>
                  <span className="text-slate-500 block">RECORD TYPE</span>
                  <span className="text-purple-300 font-bold uppercase">{activeRecordObj.record_type}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">PRIORITY BOOST</span>
                  <span className="text-emerald-400 font-bold">
                    {activeRecordObj.record_type === 'correction' ? '1.5x' : '1.0x'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">CONFIDENCE</span>
                  <span className="text-cyan-400 font-bold">
                    {activeRecordObj.confidence ? `${(activeRecordObj.confidence * 100).toFixed(1)}%` : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 block">VERDICT</span>
                  <span className="text-slate-300 font-bold uppercase">{activeRecordObj.verdict || '—'}</span>
                </div>
              </div>

              <div>
                <span className="text-slate-400 block mb-1">RAG Memory Content & Guidance:</span>
                <div className="p-3.5 rounded-xl border border-slate-800 bg-slate-950 text-slate-200 whitespace-pre-wrap leading-relaxed max-h-64 overflow-y-auto">
                  {activeRecordObj.analyst_correction || activeRecordObj.reasoning || 'No guidance recorded.'}
                </div>
              </div>

              {activeRecordObj._raw?.evidence_gathered && (
                <div>
                  <span className="text-slate-400 block mb-1">Evidence Gathered:</span>
                  <pre className="p-3 rounded-xl border border-slate-800 bg-slate-950 text-slate-300 text-[11px] whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {JSON.stringify(activeRecordObj._raw.evidence_gathered, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            <div className="pt-2 border-t border-slate-800/80 flex justify-end">
              <button
                onClick={() => setSelectedRecord(null)}
                className="px-4 py-1.5 rounded-lg font-mono text-xs text-slate-400 hover:text-white border border-slate-800"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCounter({ label, value, badge, color }) {
  const colorMap = {
    cyan: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400',
    purple: 'bg-purple-500/10 border-purple-500/30 text-purple-400',
    emerald: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400',
  }
  return (
    <div className="p-4 rounded-xl border border-slate-800 bg-slate-950/60 flex items-center justify-between">
      <div>
        <div className="text-xs font-mono text-slate-500 uppercase">{label}</div>
        <div className="text-xl font-mono font-bold text-white mt-1">{value}</div>
      </div>
      <div className={`p-2.5 rounded-lg border font-mono text-xs ${colorMap[color]}`}>
        {badge}
      </div>
    </div>
  )
}
