import { useState, useEffect, useCallback, useReducer } from 'react'
import { useParams, Link } from 'react-router-dom'
import FlowChart from '../components/FlowChart'
import AgentPanel from '../components/AgentPanel'
import AlertCard from '../components/AlertCard'
import LiveStatsBar from '../components/LiveStatsBar'
import StageDetail from '../components/StageDetail'
import { useSSE } from '../hooks/useSSE'
import {
  getAlerts, getFirewallFlags, getLiveFeedStatus, stopLiveFeed,
  getMode, setMode as setModeAPI,
} from '../utils/api'

const INIT_STAGES = {
  liveEnv: 'pending', investigation: 'pending', enrichment: 'pending',
  firewall: 'pending', primary: 'pending', secondary: 'pending',
  action: 'pending', db: 'pending',
}

const INIT_STREAM = () => ({
  stages: { ...INIT_STAGES },
  primary: { status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} },
  secondary: { status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} },
  enrichment: null, memory: [], firewallFlags: null,
  caseResult: null, error: null,
})

/** Find the current "active" pipeline stage for a stream (rightmost active/complete). */
function currentStage(stages) {
  const order = ['db', 'action', 'secondary', 'primary', 'firewall', 'enrichment', 'investigation', 'liveEnv']
  for (const key of order) {
    if (stages[key] === 'active') return key
  }
  return null
}

// ── Stream state reducer ──
function streamReducer(state, { alertId, event, data }) {
  if (!alertId) return state
  const s = state[alertId] || INIT_STREAM()
  let u // updated stream

  switch (event) {
    case 'investigation_started':
      u = { ...s, stages: { ...s.stages, liveEnv: 'active', investigation: 'active' } }
      break
    case 'memory_retrieved':
      u = { ...s, stages: { ...s.stages, investigation: 'complete' },
        memory: [...s.memory, ...(data.similar_cases || [])] }
      break
    case 'enrichment_complete':
      u = { ...s, stages: { ...s.stages, enrichment: 'complete', firewall: 'complete' },
        enrichment: { ...data.enrichment, ...(data.impact_level ? { impact_level: data.impact_level } : {}) } }
      break
    case 'agent_started':
      if (data.agent === 'primary') {
        u = { ...s, stages: { ...s.stages, primary: 'active' },
          primary: { ...s.primary, status: 'thinking' } }
      } else {
        u = { ...s, stages: { ...s.stages, primary: 'complete', secondary: 'active' },
          secondary: { ...s.secondary, status: 'thinking' } }
      }
      break
    case 'agent_status':
      u = s // thinking indicator already shown via status='thinking'
      break
    case 'agent_delta':
      if (data.agent === 'primary') {
        u = { ...s, primary: { ...s.primary, reasoning: data.text } }
      } else {
        u = { ...s, secondary: { ...s.secondary, reasoning: data.text } }
      }
      break
    case 'agent_complete':
      if (data.agent === 'primary') {
        u = { ...s, primary: {
          ...s.primary, status: 'complete',
          reasoning: s.primary.reasoning || data.reasoning,
          verdict: data.verdict, confidence: data.confidence,
          extra: { attack_technique: data.attack_technique },
        }}
      } else {
        u = { ...s, stages: { ...s.stages, secondary: 'complete' },
          secondary: {
            ...s.secondary, status: 'complete',
            reasoning: s.secondary.reasoning || data.reasoning,
            verdict: data.verdict, confidence: data.confidence,
            extra: { secondary_verdict: data.secondary_verdict, impact_level: data.impact_level },
          }}
      }
      break
    case 'case_persisted':
      u = { ...s, stages: { ...s.stages, action: 'active' } }
      break
    case 'action_decided':
      u = { ...s, stages: { ...s.stages, action: 'complete', db: 'active' } }
      break
    case 'investigation_complete':
      u = { ...s, stages: { ...s.stages, db: 'complete' }, caseResult: data }
      break
    case 'investigation_error':
      u = { ...s, error: data.detail }
      break
    default:
      u = s
  }

  if (u === s) return state
  return { ...state, [alertId]: u }
}

// ── Child component: one per streaming alert (each has its own useSSE hook) ──
function AlertStream({ alertId, onEvent }) {
  useSSE(alertId, onEvent)
  return null
}

// ═══════════════════════════════════════════════════════
// Main Orchestration Component
// ═══════════════════════════════════════════════════════
export default function Orchestration() {
  const { client } = useParams()
  const displayName = client.charAt(0).toUpperCase() + client.slice(1).replace(/-/g, ' ')

  // Alert list
  const [alerts, setAlerts] = useState([])
  const [focusedId, setFocusedId] = useState(null)
  const [flaggedAlertIds, setFlaggedAlertIds] = useState(new Set())

  // Multi-stream state: Map<alertId, streamData>
  const [streamMap, dispatch] = useReducer(streamReducer, {})

  // Which alert IDs currently have active SSE streams
  const [streamingIds, setStreamingIds] = useState(new Set())

  // Feed + mode
  const [feedStatus, setFeedStatus] = useState('idle')
  const [feedStats, setFeedStats] = useState(null)
  const [mode, setMode] = useState('agentic')

  // ── Stable SSE callback (uses functional updater — no stale closures) ──
  const handleStreamEvent = useCallback((alertId, e) => {
    dispatch({ alertId, event: e.event, data: e.data })
  }, [])

  // ── Alert polling (3s) ──
  useEffect(() => {
    const refresh = async () => {
      try { setAlerts(await getAlerts(50)) } catch { /* silent */ }
    }
    refresh()
    const t = setInterval(refresh, 3000)
    return () => clearInterval(t)
  }, [])

  // ── Feed status polling (2s) ──
  useEffect(() => {
    const refresh = async () => {
      try {
        const s = await getLiveFeedStatus()
        setFeedStatus(s.status)
        setFeedStats(s.status === 'running' ? s : null)
      } catch { /* silent */ }
    }
    refresh()
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [])

  // ── Fetch mode once ──
  useEffect(() => { getMode().then(m => setMode(m.mode)).catch(() => {}) }, [])

  // ── AUTO-PROCESS: start SSE streams for new pending alerts ──
  useEffect(() => {
    const MAX_CONCURRENT = 3
    const pendingAlerts = alerts.filter(a => a.status === 'pending')
    const newPending = pendingAlerts.filter(a => !streamingIds.has(a.id))

    if (newPending.length > 0) {
      const available = MAX_CONCURRENT - streamingIds.size
      const toStart = newPending.slice(0, Math.max(0, available))
      if (toStart.length > 0) {
        setStreamingIds(prev => {
          const next = new Set(prev)
          toStart.forEach(a => next.add(a.id))
          return next
        })
      }
    }
  }, [alerts, streamingIds])

  // ── AUTO-FOCUS: focus on the newest stream if nothing focused ──
  useEffect(() => {
    if (!focusedId && streamingIds.size > 0) {
      const first = [...streamingIds][streamingIds.size - 1]
      setFocusedId(first)
    }
    // If focused stream finished and there are others, switch to the newest active one
    if (focusedId && streamMap[focusedId]?.stages?.db === 'complete') {
      const activeIds = [...streamingIds].filter(id => {
        const s = streamMap[id]
        return s && s.stages.db !== 'complete' && !s.error
      })
      if (activeIds.length > 0) {
        setFocusedId(activeIds[activeIds.length - 1])
      }
    }
  }, [focusedId, streamingIds, streamMap])

  // ── Clean up finished streams (keep data, remove from streaming set) ──
  useEffect(() => {
    setStreamingIds(prev => {
      const next = new Set(prev)
      let changed = false
      for (const id of prev) {
        const s = streamMap[id]
        if (s && (s.stages.db === 'complete' || s.error)) {
          next.delete(id)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [streamMap])

  // ── Firewall flags for all alerts ──
  useEffect(() => {
    if (alerts.length === 0) return
    getFirewallFlags().then(flags => {
      setFlaggedAlertIds(new Set(flags.map(f => f.alert_id)))
    }).catch(() => {})
  }, [alerts])

  // ── Actions ──
  const handleSelectAlert = useCallback((alert) => {
    setFocusedId(alert.id)
    // Auto-start SSE if this alert isn't already streaming or completed
    if (!streamMap[alert.id] && alert.status === 'pending') {
      setStreamingIds(prev => new Set([...prev, alert.id]))
    }
  }, [streamMap])

  const handleStopFeed = async () => {
    try { await stopLiveFeed() } catch { /* silent */ }
  }

  const handleModeToggle = async () => {
    try {
      const next = mode === 'agentic' ? 'approval' : 'agentic'
      const r = await setModeAPI(next)
      setMode(r.mode)
    } catch { /* silent */ }
  }

  // ── Focused stream data ──
  const focusedStream = focusedId ? streamMap[focusedId] : null
  const focusedAlert = alerts.find(a => a.id === focusedId) || null

  // ── Render ──
  return (
    <div className="min-h-screen bg-[#050705] flex flex-col">
      {/* Hidden SSE consumers — one per streaming alert */}
      {[...streamingIds].map(id => (
        <AlertStream
          key={id}
          alertId={id}
          onEvent={(e) => handleStreamEvent(id, e)}
        />
      ))}

      <LiveStatsBar
        feedStatus={feedStatus} stats={feedStats}
        mode={mode} onModeToggle={handleModeToggle}
      />

      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-800/50 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-slate-600 hover:text-slate-400 font-mono text-sm transition-colors">← Back</Link>
          <span className="text-slate-800">│</span>
          <h1 className="text-lg font-semibold text-white">
            <span className="text-emerald-400 text-glow-green">{displayName}</span>
            <span className="text-slate-500 text-sm ml-2 font-mono">Orchestration</span>
          </h1>
          <span className="font-mono text-xs text-slate-700 ml-2">
            {streamingIds.size > 0 && `${streamingIds.size} active stream${streamingIds.size > 1 ? 's' : ''}`}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleStopFeed}
            className={`px-3 py-1 rounded font-mono text-xs border transition-all ${
              feedStatus === 'running'
                ? 'border-red-500/30 text-red-400 bg-red-500/10 hover:bg-red-500/20'
                : 'border-slate-700/50 text-slate-600 bg-slate-900/30'
            }`}
          >
            {feedStatus === 'running' ? '■ STOP FEED' : '■ FEED STOPPED'}
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Alert Queue Sidebar ── */}
        <div className="w-72 border-r border-slate-800/50 flex flex-col bg-slate-950/30">
          <div className="px-3 py-2.5 border-b border-slate-800/50 flex items-center justify-between">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Alert Queue</span>
            <div className="flex items-center gap-2">
              {streamingIds.size > 0 && (
                <span className="font-mono text-xs text-cyan-400">{streamingIds.size} live</span>
              )}
              <span className="font-mono text-xs text-emerald-500">{alerts.length}</span>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {alerts.length === 0 ? (
              <div className="text-center py-8">
                <span className="text-slate-600 font-mono text-xs">
                  {feedStatus === 'running' ? 'Waiting for alerts...' : 'Start the live feed'}
                </span>
              </div>
            ) : (
              alerts.map(alert => {
                const stream = streamMap[alert.id]
                return (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    isSelected={focusedId === alert.id}
                    isStreaming={streamingIds.has(alert.id)}
                    firewallFlagged={flaggedAlertIds.has(alert.id)}
                    streamStage={stream ? currentStage(stream.stages) : null}
                    onClick={() => handleSelectAlert(alert)}
                  />
                )
              })
            )}
          </div>
        </div>

        {/* ── Main Panel ── */}
        <div className="flex-1 flex flex-col overflow-y-auto p-4 space-y-4">
          {focusedStream && focusedAlert ? (
            <div className="animate-fade-in">
              {/* Alert info bar */}
              <div className="flex items-center gap-4 mb-4 px-2">
                <span className="font-mono text-xs text-slate-500">
                  ALERT: <span className="text-cyan-400">{focusedAlert.source_alert_id}</span>
                </span>
                <span className="font-mono text-xs text-slate-700">│</span>
                <span className="font-mono text-xs text-slate-500">{focusedAlert.alert_type}</span>
                <span className="font-mono text-xs text-slate-700">│</span>
                <span className="font-mono text-xs text-slate-500">
                  {focusedAlert.received_at
                    ? new Date(focusedAlert.received_at).toLocaleString()
                    : '—'}
                </span>
                {focusedStream.firewallFlags && (
                  <>
                    <span className="font-mono text-xs text-slate-700">│</span>
                    <span className={`font-mono text-xs ${
                      focusedStream.firewallFlags.length > 0 ? 'text-red-400' : 'text-emerald-500/70'
                    }`}>
                      {focusedStream.firewallFlags.length > 0 ? '⚠ FLAGGED' : '✓ CLEAN'}
                    </span>
                  </>
                )}
              </div>

              {/* Workflow Flowchart */}
              <FlowChart
                stages={focusedStream.stages}
                firewallFlags={focusedStream.firewallFlags}
                primaryData={focusedStream.primary}
                secondaryData={focusedStream.secondary}
                caseResult={focusedStream.caseResult}
              />

              {/* Stage Details: Investigation, Enrichment, Firewall */}
              <StageDetail
                stages={focusedStream.stages}
                enrichmentData={focusedStream.enrichment}
                memoryData={focusedStream.memory}
                firewallFlags={focusedStream.firewallFlags}
                alert={focusedAlert}
              />

              {/* Agent Reasoning Panels */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                <AgentPanel
                  name="Primary Agent"
                  status={focusedStream.primary.status}
                  reasoning={focusedStream.primary.reasoning}
                  verdict={focusedStream.primary.verdict}
                  confidence={focusedStream.primary.confidence}
                  extra={focusedStream.primary.extra}
                  alertTime={focusedAlert.received_at}
                />
                <AgentPanel
                  name="Secondary Agent"
                  status={focusedStream.secondary.status}
                  reasoning={focusedStream.secondary.reasoning}
                  verdict={focusedStream.secondary.verdict}
                  confidence={focusedStream.secondary.confidence}
                  extra={focusedStream.secondary.extra}
                  alertTime={focusedAlert.received_at}
                />
              </div>

              {/* Case Result */}
              {focusedStream.caseResult && (
                <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-950/15 p-4 glow-green animate-slide-in">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-emerald-400" />
                    <span className="font-mono text-xs text-emerald-400 uppercase tracking-wider">Case Filed</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <ResultItem label="Verdict" value={focusedStream.caseResult.primary_verdict?.replace('_', ' ').toUpperCase()}
                      color={focusedStream.caseResult.primary_verdict === 'true_positive' ? 'text-red-400' : 'text-emerald-400'} />
                    <ResultItem label="2nd Opinion" value={focusedStream.caseResult.secondary_verdict?.replace('_', ' ').toUpperCase() || '—'} color="text-cyan-400" />
                    <ResultItem label="Action" value={focusedStream.caseResult.action_status || 'NONE'} color="text-yellow-400" />
                    <ResultItem label="Case ID" value={focusedStream.caseResult.case_id?.slice(0, 12) + '...'} color="text-slate-400" small />
                  </div>
                </div>
              )}

              {/* Error state */}
              {focusedStream.error && (
                <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-4">
                  <span className="font-mono text-xs text-red-400">Error: {focusedStream.error}</span>
                </div>
              )}
            </div>
          ) : (
            /* Empty state */
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="text-4xl text-slate-800 mb-4">◉</div>
                <p className="text-slate-600 font-mono text-sm mb-2">
                  {alerts.length > 0
                    ? 'Processing alerts automatically...'
                    : feedStatus === 'running'
                      ? 'Waiting for alerts...'
                      : 'Start the live feed from the dashboard'}
                </p>
                <div className="flex items-center justify-center gap-2 mt-4">
                  <div className={`w-1.5 h-1.5 rounded-full ${
                    feedStatus === 'running' ? 'bg-emerald-400 animate-pulse' : 'bg-slate-700'
                  }`} />
                  <span className="font-mono text-xs text-slate-700">
                    {feedStatus === 'running' ? 'Feed active — alerts auto-processing' : 'Feed idle'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ResultItem({ label, value, color = 'text-slate-400', small = false }) {
  return (
    <div>
      <div className="text-xs text-slate-500 font-mono mb-1">{label}</div>
      <div className={`${small ? 'text-xs' : 'text-sm'} font-mono ${color} truncate`}>{value}</div>
    </div>
  )
}
