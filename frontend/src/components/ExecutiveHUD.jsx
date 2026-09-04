import { useState, useEffect, useMemo } from 'react'
import { getCases, getFirewallFlags } from '../utils/api'

/**
 * Live Executive Metrics & Command Center HUD Component
 * Visualizes high-level SOC performance KPIs derived from real backend data.
 */
export default function ExecutiveHUD({ alerts = [] }) {
  const [cases, setCases] = useState([])
  const [flags, setFlags] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([getCases(200), getFirewallFlags()])
      .then(([casesData, flagsData]) => {
        if (cancelled) return
        setCases(Array.isArray(casesData) ? casesData : [])
        setFlags(Array.isArray(flagsData) ? flagsData : [])
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [alerts.length])

  const totalAlerts = alerts.length
  const totalCases = cases.length
  const closedCases = cases.filter((c) => c.action_status && c.action_status !== 'none')

  // Mean Time To Respond: average seconds from alert received_at to case closed_at
  const mttrSeconds = useMemo(() => {
    const durations = closedCases
      .map((c) => {
        const received = c.alerts?.received_at ? new Date(c.alerts.received_at).getTime() : null
        const closed = c.closed_at ? new Date(c.closed_at).getTime() : null
        if (received && closed && closed > received) return (closed - received) / 1000
        return null
      })
      .filter((d) => d !== null)
    if (durations.length === 0) return null
    return durations.reduce((a, b) => a + b, 0) / durations.length
  }, [closedCases])

  // Autonomous triage rate: cases closed in agentic mode without human override
  const agenticCases = cases.filter((c) => c.mode === 'agentic')
  const autonomousRate = totalCases ? (agenticCases.length / totalCases) * 100 : 0

  // False positive rate
  const fpCases = cases.filter((c) => c.primary_verdict === 'false_positive')
  const fpRate = totalCases ? (fpCases.length / totalCases) * 100 : 0

  // Poison defense: flagged alerts / total alerts
  const poisonRate = totalAlerts ? (flags.length / totalAlerts) * 100 : 0

  // Dual-agent agreement
  const casesWithSecondary = cases.filter((c) => c.secondary_verdict)
  const agreementCases = casesWithSecondary.filter((c) => {
    if (c.secondary_verdict === 'agree') return true
    return c.secondary_verdict === c.primary_verdict
  })
  const agreementRate = casesWithSecondary.length
    ? (agreementCases.length / casesWithSecondary.length) * 100
    : 0

  // Average primary confidence
  const avgConfidence = totalCases
    ? cases.reduce((sum, c) => sum + (c.primary_confidence || 0), 0) / totalCases
    : 0

  // Threat category breakdown from cases (real alert_type distribution)
  const typeBreakdown = useMemo(() => {
    const counts = {}
    cases.forEach((c) => {
      const type = c.alerts?.alert_type || c.alert_type || 'unknown'
      counts[type] = (counts[type] || 0) + 1
    })
    return Object.entries(counts)
      .map(([type, count]) => ({ type, count, pct: totalCases ? (count / totalCases) * 100 : 0 }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6)
  }, [cases, totalCases])

  // Awaiting approval / escalated
  const pendingApproval = cases.filter(
    (c) => c.action_status === 'awaiting_approval' || c.action_status === 'escalated'
  ).length

  const formatDuration = (seconds) => {
    if (seconds === null || Number.isNaN(seconds)) return '—'
    if (seconds < 60) return `${seconds.toFixed(1)}s`
    if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`
    return `${(seconds / 3600).toFixed(1)}h`
  }

  if (loading) {
    return (
      <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6 animate-fade-in relative overflow-hidden min-h-[300px] flex flex-col items-center justify-center">
        <div className="flex items-center gap-2 text-emerald-400 font-mono text-xs animate-pulse">
          <span className="w-2 h-2 rounded-full bg-emerald-400" />
          Loading executive metrics from backend...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="glass-panel rounded-2xl p-6 border border-red-500/30 space-y-6 animate-fade-in relative overflow-hidden">
        <div className="text-red-400 font-mono text-xs">
          ⚠ Failed to load executive metrics: {error}
        </div>
      </div>
    )
  }

  return (
    <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-6 animate-fade-in relative overflow-hidden">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <h3 className="font-display font-bold text-base text-white tracking-wide">
              EXECUTIVE SOC METRICS & ROI ANALYTICS HUD
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            High-level performance dashboard computed from live alert, case, and firewall data.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-lg font-mono text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 glow-green">
            ● LIVE BACKEND DATA
          </span>
        </div>
      </div>

      {/* Hero Executive KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: MTTR */}
        <KpiCard
          label="MEAN TIME TO RESPOND (MTTR)"
          badge={mttrSeconds !== null ? 'AUTONOMOUS' : 'NO CLOSED CASES'}
          value={mttrSeconds !== null ? formatDuration(mttrSeconds) : '—'}
          sub="avg. case resolution"
          width={mttrSeconds !== null ? Math.min(100, Math.max(5, (60 / Math.max(mttrSeconds, 1)) * 100)) : 0}
          color="emerald"
          footer={mttrSeconds !== null ? "Dual-agent triage measured end-to-end from ingestion to closure." : "Cases will appear as alerts are investigated."}
        />

        {/* KPI 2: Autonomous Triage Rate */}
        <KpiCard
          label="AUTONOMOUS TRIAGE RATE"
          badge={`${autonomousRate.toFixed(1)}% AUTO`}
          value={`${autonomousRate.toFixed(1)}%`}
          sub="of closed cases"
          width={autonomousRate}
          color="cyan"
          footer="Cases resolved in agentic mode without analyst override."
        />

        {/* KPI 3: Prompt Poison Defense */}
        <KpiCard
          label="PROMPT POISON DEFENSE"
          badge={`${flags.length} FLAGGED`}
          value={`${poisonRate.toFixed(1)}%`}
          sub="log firewall catch rate"
          width={poisonRate}
          color="pink"
          footer="Adversarial prompt injection payloads intercepted before reaching agents."
        />

        {/* KPI 4: Analyst Workload Reduction */}
        <KpiCard
          label="FALSE POSITIVE FILTERING"
          badge={`${fpRate.toFixed(1)}% FP`}
          value={`${fpRate.toFixed(1)}%`}
          sub="noise reduced"
          width={fpRate}
          color="purple"
          footer="Primary agent classified benign noise, freeing analysts for real threats."
        />
      </div>

      {/* Secondary Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MiniStat label="Total Alerts" value={totalAlerts} color="white" />
        <MiniStat label="Investigated Cases" value={totalCases} color="cyan" />
        <MiniStat label="Awaiting Approval" value={pendingApproval} color="amber" />
        <MiniStat label="Avg Confidence" value={`${(avgConfidence * 100).toFixed(1)}%`} color="emerald" />
      </div>

      {/* Main Analytics Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Threat Distribution Breakdown Panel */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider">
              Threat Category & Ingestion Breakdown
            </span>
            <span className="text-xs font-mono text-slate-400">{totalCases} Investigated Cases</span>
          </div>

          {typeBreakdown.length === 0 ? (
            <div className="text-center py-8 text-xs font-mono text-slate-500">
              No case data available yet.
            </div>
          ) : (
            <div className="space-y-3 font-mono text-xs">
              {typeBreakdown.map((item, idx) => {
                const colors = [
                  { name: 'emerald', text: 'text-emerald-400', bar: 'bg-emerald-400' },
                  { name: 'cyan', text: 'text-cyan-400', bar: 'bg-cyan-400' },
                  { name: 'amber', text: 'text-amber-400', bar: 'bg-amber-400' },
                  { name: 'pink', text: 'text-pink-400', bar: 'bg-pink-400' },
                  { name: 'purple', text: 'text-purple-400', bar: 'bg-purple-400' },
                  { name: 'red', text: 'text-red-400', bar: 'bg-red-400' },
                ]
                const c = colors[idx % colors.length]
                return (
                  <div key={item.type}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-slate-300 capitalize">{item.type.replace(/_/g, ' ')}</span>
                      <span className={`${c.text} font-semibold`}>
                        {item.count} ({item.pct.toFixed(1)}%)
                      </span>
                    </div>
                    <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden">
                      <div
                        className={`${c.bar} h-full rounded-full`}
                        style={{ width: `${Math.min(100, item.pct)}%` }}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Dual AI Agent Accuracy & Agreement Matrix */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-950/60 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <span className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wider">
              Dual-Agent Agreement & Model Metrics
            </span>
            <span className="text-xs font-mono text-emerald-400">{agreementRate.toFixed(1)}% Consensus</span>
          </div>

          <div className="grid grid-cols-2 gap-3 font-mono text-xs">
            <StatBox
              label="PRIMARY AGENT VERDICT CONFIDENCE"
              value={`${(avgConfidence * 100).toFixed(1)}%`}
              sub="Average confidence across cases"
              color="cyan"
            />
            <StatBox
              label="SECONDARY CROSS-CHECK VERIFY"
              value={`${agreementRate.toFixed(1)}%`}
              sub="Agreement with primary verdict"
              color="purple"
            />
            <StatBox
              label="RAG MEMORY RECALL USAGE"
              value={`${cases.filter((c) => c.qoder_memory_record_id).length}`}
              sub="Cases with memory records written"
              color="emerald"
            />
            <StatBox
              label="HUMAN ESCALATION QUEUE"
              value={`${pendingApproval}`}
              sub="Cases awaiting analyst decision"
              color="amber"
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function KpiCard({ label, badge, value, sub, width, color, footer }) {
  const colorMap = {
    emerald: { text: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', bar: 'bg-emerald-400', badge: 'text-emerald-400' },
    cyan: { text: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30', bar: 'bg-cyan-400', badge: 'text-cyan-400' },
    pink: { text: 'text-pink-400', bg: 'bg-pink-500/10', border: 'border-pink-500/30', bar: 'bg-pink-400', badge: 'text-pink-400' },
    purple: { text: 'text-purple-300', bg: 'bg-purple-500/10', border: 'border-purple-500/30', bar: 'bg-purple-400', badge: 'text-purple-300' },
  }
  const c = colorMap[color]
  return (
    <div className={`p-5 rounded-2xl border ${c.border} ${c.bg} relative overflow-hidden space-y-2`}>
      <div className="flex items-center justify-between text-xs font-mono text-slate-400">
        <span>{label}</span>
        <span className={`${c.badge} font-bold`}>{badge}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`text-3xl font-mono font-extrabold ${c.text}`}>{value}</span>
        <span className="text-xs font-mono text-slate-500">{sub}</span>
      </div>
      <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
        <div className={`${c.bar} h-full rounded-full`} style={{ width: `${Math.min(100, width)}%` }} />
      </div>
      <p className="text-[11px] font-mono text-slate-400 pt-1">{footer}</p>
    </div>
  )
}

function MiniStat({ label, value, color }) {
  const colorMap = {
    white: 'text-white',
    cyan: 'text-cyan-400',
    amber: 'text-amber-400',
    emerald: 'text-emerald-400',
  }
  return (
    <div className="p-3 rounded-xl border border-slate-800 bg-slate-950/60">
      <div className="text-[10px] font-mono text-slate-500 uppercase">{label}</div>
      <div className={`text-lg font-mono font-bold ${colorMap[color]} mt-1`}>
        {value}
      </div>
    </div>
  )
}

function StatBox({ label, value, sub, color }) {
  const colorMap = {
    cyan: 'text-cyan-400',
    purple: 'text-purple-400',
    emerald: 'text-emerald-400',
    amber: 'text-amber-400',
  }
  return (
    <div className="p-3 rounded-lg border border-slate-800 bg-slate-900/40">
      <span className="text-slate-500 block text-[11px]">{label}</span>
      <span className={`text-base font-bold ${colorMap[color]} mt-1 block`}>{value}</span>
      <span className="text-[10px] text-slate-400">{sub}</span>
    </div>
  )
}
