import { useState, useEffect, useCallback, useReducer } from 'react'
import { useParams, Link } from 'react-router-dom'
import FlowChart from '../components/FlowChart'
import AgentPanel from '../components/AgentPanel'
import AlertCard from '../components/AlertCard'
import LiveStatsBar from '../components/LiveStatsBar'
import StageDetail from '../components/StageDetail'
import EscalationModal from '../components/EscalationModal'
import MemoryToast from '../components/MemoryToast'
import TopologyMap from '../components/TopologyMap'
import MemoryVault from '../components/MemoryVault'
import ComplianceReportModal from '../components/ComplianceReportModal'




import { useSSE } from '../hooks/useSSE'

import {
  startLiveFeed, getAlerts, getFirewallFlags, getLiveFeedStatus, stopLiveFeed,
  getMode, setMode as setModeAPI, submitAnalystDecision, getCase, ingestAlert,
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

const LIVE_FEED_DURATION_SECONDS = 300
const LIVE_FEED_INTERVAL_SECONDS = 3
const LIVE_FEED_POISON_RATIO = 0
const ALERT_POLL_INTERVAL_MS = 1000

/** Find current active stage for stream visualization */
function currentStage(stages) {
  const order = ['db', 'action', 'secondary', 'primary', 'firewall', 'enrichment', 'investigation', 'liveEnv']
  for (const key of order) {
    if (stages[key] === 'active') return key
  }
  return null
}

// ── Stream State Reducer ──
function streamReducer(state, { alertId, event, data }) {
  if (!alertId) return state
  const s = state[alertId] || INIT_STREAM()
  let u

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
    case 'agent_delta':
      if (data.agent === 'primary') {
        u = {
          ...s,
          primary: {
            ...s.primary,
            status: 'thinking',
            reasoning: (s.primary.reasoning || '') + (data.text || ''),
          },
        }
      } else {
        u = {
          ...s,
          secondary: {
            ...s.secondary,
            status: 'thinking',
            reasoning: (s.secondary.reasoning || '') + (data.text || ''),
          },
        }
      }
      break
    case 'agent_complete':
      if (data.agent === 'primary') {
        const finalPrimaryReasoning = (data.reasoning && data.reasoning.trim())
          ? data.reasoning
          : (s.primary.reasoning || '')
        u = {
          ...s,
          primary: {
            ...s.primary,
            status: 'complete',
            reasoning: finalPrimaryReasoning,
            verdict: data.verdict,
            confidence: data.confidence,
            extra: { attack_technique: data.attack_technique },
          },
        }
      } else {
        const finalSecReasoning = (data.reasoning && data.reasoning.trim())
          ? data.reasoning
          : (s.secondary.reasoning || '')
        u = {
          ...s,
          stages: { ...s.stages, secondary: 'complete' },
          secondary: {
            ...s.secondary,
            status: 'complete',
            reasoning: finalSecReasoning,
            verdict: data.verdict || data.secondary_verdict,
            confidence: data.confidence,
            extra: {
              secondary_verdict: data.secondary_verdict,
              impact_level: data.impact_level,
              attack_technique: data.attack_technique,
            },
          },
        }
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
      u = { ...s, error: data.detail || null }
      break
    default:
      u = s
  }

  if (u === s) return state
  return { ...state, [alertId]: u }
}

function AlertStream({ alertId, onEvent }) {
  useSSE(alertId, onEvent)
  return null
}

function isLiveQueueAlert(alert, sessionStartedAt) {
  if (!['pending', 'in_review'].includes(alert.status)) return false
  if (!alert.source_alert_id?.startsWith('LIVE-')) return false

  const receivedAt = Date.parse(alert.received_at || '')
  return Number.isFinite(receivedAt) && receivedAt >= sessionStartedAt
}

// Closed/resolved alerts from this launch — same session scoping as the live
// queue, but for the CLOSED tab (kept separate so auto-investigation still only
// ever picks up pending/in_review alerts).
function isClosedQueueAlert(alert, sessionStartedAt) {
  if (alert.status !== 'closed') return false
  if (!alert.source_alert_id?.startsWith('LIVE-')) return false

  const receivedAt = Date.parse(alert.received_at || '')
  return Number.isFinite(receivedAt) && receivedAt >= sessionStartedAt
}

export default function Orchestration() {
  const { client } = useParams()
  const displayName = client ? client.charAt(0).toUpperCase() + client.slice(1).replace(/-/g, ' ') : 'Command Center'

  // Alert State & Filters
  const [alerts, setAlerts] = useState([])
  const [focusedId, setFocusedId] = useState(null)
  const [flaggedAlertIds, setFlaggedAlertIds] = useState(new Set())
  const [statusFilter, setStatusFilter] = useState('ACTIVE')
  const [searchQuery, setSearchQuery] = useState('')
  const [activeView, setActiveView] = useState('pipeline') // 'pipeline' | 'topology'
  const [focusPinned, setFocusPinned] = useState(false)
  const [globalError, setGlobalError] = useState(null)
  const [announcement, setAnnouncement] = useState('')
  // Queue is scoped to this Command Center launch, never historic records.
  const [liveSessionStartedAt, setLiveSessionStartedAt] = useState(() => Date.now())


  // Multi-stream state & Active streams
  const [streamMap, dispatch] = useReducer(streamReducer, {})
  const [streamingIds, setStreamingIds] = useState(new Set())

  // System & Feed Controls
  const [feedStatus, setFeedStatus] = useState('idle')
  const [feedStats, setFeedStats] = useState(null)
  const [mode, setMode] = useState('agentic')

  // Analyst Escalation Modal & Memory Toast state
  const [showEscalationModal, setShowEscalationModal] = useState(false)
  const [showComplianceModal, setShowComplianceModal] = useState(false)
  const [activeCaseDetails, setActiveCaseDetails] = useState(null)
  const [memoryToast, setMemoryToast] = useState(null)

  const handleStreamEvent = useCallback((alertId, e) => {
    dispatch({ alertId, event: e.event, data: e.data })
  }, [])

  // Auto-start live threat feed on launch — skip if a run is already active
  useEffect(() => {
    const boot = async () => {
      try {
        const s = await getLiveFeedStatus()
        if (s.status === 'running') return
        const run = await startLiveFeed(
          LIVE_FEED_DURATION_SECONDS,
          LIVE_FEED_INTERVAL_SECONDS,
          LIVE_FEED_POISON_RATIO,
        )
        const startedAt = Date.parse(run.started_at || '')
        setLiveSessionStartedAt(Number.isFinite(startedAt) ? startedAt : Date.now())
      } catch (err) {
        // A concurrent run is benign (re-visit or StrictMode double-mount)
        if (!String(err.message || '').includes('already active')) {
          setGlobalError(err.message)
        }
      }
    }
    boot()
  }, [])

  // Poll every second so a newly generated Cloudflare alert appears immediately.
  useEffect(() => {
    const refresh = async () => {
      try {
        const res = await getAlerts(25)
        if (Array.isArray(res)) setAlerts(res)
      } catch (err) {
        setGlobalError(err.message)
      }
    }
    refresh()
    const t = setInterval(refresh, ALERT_POLL_INTERVAL_MS)
    return () => clearInterval(t)
  }, [])


  // Poll live feed status (2s)
  useEffect(() => {
    const refresh = async () => {
      try {
        const s = await getLiveFeedStatus()
        setFeedStatus(s.status)
        setFeedStats(s.status === 'running' ? s : null)
        if (s.last_error) setGlobalError(s.last_error)
      } catch (err) {
        setFeedStatus('idle')
        setGlobalError(err.message)
      }
    }
    refresh()
    const t = setInterval(refresh, 2000)
    return () => clearInterval(t)
  }, [])

  // Fetch mode once
  useEffect(() => {
    getMode().then(m => setMode(m.mode)).catch((err) => setGlobalError(err.message))
  }, [])

  // Auto-focus newest active stream (disabled when focus is pinned)
  useEffect(() => {
    if (focusPinned) return
    if (!focusedId && streamingIds.size > 0) {
      const first = [...streamingIds][streamingIds.size - 1]
      setFocusedId(first)
    }
    if (focusedId && streamMap[focusedId]?.stages?.db === 'complete') {
      const activeIds = [...streamingIds].filter(id => {
        const s = streamMap[id]
        return s && s.stages.db !== 'complete' && !s.error
      })
      if (activeIds.length > 0) {
        setFocusedId(activeIds[activeIds.length - 1])
      }
    }
  }, [focusedId, streamingIds, streamMap, focusPinned])

  // Clean finished streams from active set and announce completed investigations
  useEffect(() => {
    setStreamingIds(prev => {
      const next = new Set(prev)
      let changed = false
      for (const id of prev) {
        const s = streamMap[id]
        if (s && (s.stages.db === 'complete' || s.error)) {
          next.delete(id)
          changed = true
          if (s.stages.db === 'complete' && s.caseResult) {
            const verdict = s.caseResult.primary_verdict === 'true_positive' ? 'true positive' : 'false positive'
            const action = s.caseResult.action_status === 'executed' ? 'action executed' : s.caseResult.action_status?.replace('_', ' ')
            setAnnouncement(`Investigation complete for alert ${id.slice(0, 8)}. ${verdict}. ${action}.`)
          }
        }
      }
      return changed ? next : prev
    })
  }, [streamMap])

  // Auto-investigate pending alerts — up to 3 concurrent SSE streams.
  // Newest alerts first; a slot frees up as each stream completes or errors.
  const MAX_CONCURRENT_STREAMS = 3
  useEffect(() => {
    setStreamingIds(prev => {
      if (prev.size >= MAX_CONCURRENT_STREAMS) return prev
      const next = new Set(prev)
      let added = false
      for (const a of alerts) {
        if (next.size >= MAX_CONCURRENT_STREAMS) break
        // Only Cloudflare alerts generated during this launch can enter the pipeline.
        if (
          isLiveQueueAlert(a, liveSessionStartedAt)
          && a.status === 'pending'
          && !next.has(a.id)
          && !streamMap[a.id]
        ) {
          next.add(a.id)
          added = true
        }
      }
      return added ? next : prev
    })
  }, [alerts, streamMap, liveSessionStartedAt])

  // Fetch Firewall Flags
  useEffect(() => {
    if (alerts.length === 0) return
    getFirewallFlags().then(flags => {
      setFlaggedAlertIds(new Set(flags.map(f => f.alert_id)))
    }).catch(() => {})
  }, [alerts])

  const handleSelectAlert = useCallback((alert) => {
    setFocusedId(alert.id)
    setFocusPinned(true)
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

  // Open Escalation Modal for case decision
  const handleOpenEscalation = async () => {
    const stream = streamMap[focusedId]
    const caseId = stream?.caseResult?.case_id
    if (caseId) {
      try {
        const fullCase = await getCase(caseId)
        setActiveCaseDetails(fullCase.case)
        setShowEscalationModal(true)
      } catch (err) {
        // Fallback to stream caseResult
        setActiveCaseDetails(stream.caseResult)
        setShowEscalationModal(true)
      }
    }
  }

  // Handle analyst decision submission
  const handleDecisionSubmitted = async (decisionData) => {
    const stream = streamMap[focusedId]
    const caseId = stream?.caseResult?.case_id || activeCaseDetails?.id
    if (!caseId) return

    const response = await submitAnalystDecision(caseId, decisionData)

    // Instantly update streamMap state so human approval badge turns off and case displays closed
    if (focusedId && stream) {
      handleStreamEvent(focusedId, {
        event: 'investigation_complete',
        data: {
          ...stream.caseResult,
          action_status: response.case?.action_status || 'executed',
          case_status: 'closed',
          action_taken: response.case?.action_taken || stream.caseResult?.action_taken,
        },
      })
    }

    // Trigger Memory Toast Notification
    setMemoryToast({
      recordType: response.memory_record_type || 'correction',
      recordId: response.memory_record_id,
      message: response.analyst_correction || `Analyst decision '${decisionData.decision}' recorded. Case closed.`,
    })

    // Refresh alert list and case result status
    getAlerts(25).then(res => { if (Array.isArray(res)) setAlerts(res) }).catch(() => {})
    setShowEscalationModal(false)
  }

  // The command queue never replays historic data or solved alerts.
  const safeAlerts = Array.isArray(alerts) ? alerts : []
  const liveQueueAlerts = safeAlerts.filter(alert => isLiveQueueAlert(alert, liveSessionStartedAt))
  const closedQueueAlerts = safeAlerts.filter(alert => isClosedQueueAlert(alert, liveSessionStartedAt))

  // Filter this launch's queue by search and state. CLOSED draws from resolved
  // alerts; the other tabs draw from the live (pending/in_review) queue.
  const queueSource = statusFilter === 'CLOSED' ? closedQueueAlerts : liveQueueAlerts
  const filteredAlerts = queueSource.filter(alert => {
    if (statusFilter === 'PENDING' && alert.status !== 'pending') return false
    if (statusFilter === 'IN_REVIEW' && alert.status !== 'in_review') return false
    if (statusFilter === 'FLAGGED' && !flaggedAlertIds.has(alert.id)) return false
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      return (alert.source_alert_id || '').toLowerCase().includes(q) || (alert.alert_type || '').toLowerCase().includes(q)
    }
    return true
  })

  const focusedStream = focusedId ? streamMap[focusedId] : null
  const focusedAlert = safeAlerts.find(a => a.id === focusedId) || null

  const isAwaitingApproval = focusedStream?.caseResult?.action_status === 'awaiting_approval' || focusedStream?.caseResult?.action_status === 'escalated'

  return (
    <div className="min-h-screen bg-[#04070d] flex flex-col font-sans relative">
      {/* Hidden SSE streams */}
      {[...streamingIds].map(id => (
        <AlertStream
          key={id}
          alertId={id}
          onEvent={(e) => handleStreamEvent(id, e)}
        />
      ))}

      {/* Top Glassmorphic Stats Header */}
      <LiveStatsBar
        feedStatus={feedStatus}
        stats={feedStats}
        mode={mode}
        onModeToggle={handleModeToggle}
      />

      {/* Global Error Banner */}
      {globalError && (
        <div className="px-6 py-2 bg-red-950/40 border-b border-red-500/30 flex items-center justify-between z-30">
          <span className="text-red-400 font-mono text-xs" role="alert">
            ⚠ {globalError}
          </span>
          <button
            onClick={() => setGlobalError(null)}
            className="text-slate-400 hover:text-white font-mono text-xs"
            aria-label="Dismiss error"
          >
            ✕
          </button>
        </div>
      )}

      {/* Screen-reader announcements for live events */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      {/* Sub Header Navigation */}

      <div className="px-6 py-3 border-b border-slate-800/80 bg-slate-950/40 flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 z-20">
        <div className="flex items-center gap-3">
          <Link to="/" className="text-slate-400 hover:text-cyan-300 font-mono text-xs transition-colors flex items-center gap-1">
            <span>←</span> Back to Gateway
          </Link>
          <span className="text-slate-800">│</span>
          <h1 className="text-base font-display font-bold text-white flex items-center gap-2">
            <span className="text-emerald-400 text-glow-green">{displayName}</span>
            <span className="text-slate-500 font-mono text-xs font-normal">Command Center</span>
          </h1>
          {streamingIds.size > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 glow-cyan animate-pulse">
              {streamingIds.size} ACTIVE PIPELINE{streamingIds.size > 1 ? 'S' : ''}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* View Switcher Tabs */}
          <div className="flex items-center gap-1 p-1 bg-slate-900/80 border border-slate-800 rounded-xl flex-wrap">
            <button
              onClick={() => setActiveView('pipeline')}
              className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all cursor-pointer ${
                activeView === 'pipeline'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 glow-green'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              📊 WORKFLOW PIPELINE
            </button>
            <button
              onClick={() => setActiveView('topology')}
              className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all cursor-pointer ${
                activeView === 'topology'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 glow-cyan'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              🌐 THREAT TOPOLOGY MAP
            </button>
            <button
              onClick={() => setActiveView('memory')}
              className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all cursor-pointer ${
                activeView === 'memory'
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 glow-purple'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              🧠 RAG MEMORY VAULT
            </button>
            <button
              onClick={() => setActiveView('hud')}
              className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold transition-all cursor-pointer ${
                activeView === 'hud'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 glow-green'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              📈 EXECUTIVE HUD
            </button>
          </div>



          <button
            onClick={() => setFocusPinned(!focusPinned)}
            className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold border transition-all duration-300 flex items-center gap-1.5 ${
              focusPinned
                ? 'border-amber-500/40 text-amber-300 bg-amber-500/15 hover:bg-amber-500/25 glow-amber cursor-pointer'
                : 'border-slate-800 text-slate-500 bg-slate-900/40 hover:text-slate-300'
            }`}
            title={focusPinned ? 'Focus is pinned to selected alert' : 'Auto-focus follows newest active stream'}
          >
            {focusPinned ? '🔒 FOCUS PINNED' : '🔓 AUTO FOCUS'}
          </button>

          <button
            onClick={handleStopFeed}
            className={`px-3 py-1.5 rounded-lg font-mono text-xs font-semibold border transition-all duration-300 flex items-center gap-1.5 ${
              feedStatus === 'running'
                ? 'border-red-500/40 text-red-400 bg-red-500/15 hover:bg-red-500/25 glow-red cursor-pointer'
                : 'border-slate-800 text-slate-500 bg-slate-900/40'
            }`}
          >

            {feedStatus === 'running' ? (
              <>
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span>■ STOP LIVE FEED</span>
              </>
            ) : (
              <span>■ FEED STOPPED</span>
            )}
          </button>
        </div>
      </div>

      {/* Main Command Center Layout */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">

        {/* ── Left Sidebar: Alert Queue ── */}
        <div className="w-full lg:w-80 border-b lg:border-b-0 lg:border-r border-slate-800/80 flex flex-col bg-slate-950/50 backdrop-blur-md z-10 lg:self-start max-h-[60vh] lg:max-h-[75vh]">
          
          {/* Queue Filter Bar */}
          <div className="p-3 border-b border-slate-800/80 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs font-bold text-slate-300 uppercase tracking-wider">Alert Queue</span>
              <span className="font-mono text-xs text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                {liveQueueAlerts.length} live
              </span>
            </div>

            {/* Search Input */}
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by ID or type..."
              className="w-full px-2.5 py-1.5 bg-slate-900/80 border border-slate-800 rounded-lg text-xs text-slate-200 font-mono focus:border-emerald-500/50 focus:outline-none"
            />

            {/* Filter Tabs */}
            <div className="flex gap-1 pt-1 overflow-x-auto">
              {['ACTIVE', 'PENDING', 'IN_REVIEW', 'FLAGGED', 'CLOSED'].map((tab) => (
                <button
                  key={tab}
                  onClick={() => setStatusFilter(tab)}
                  className={`px-2 py-1 rounded text-[10px] font-mono font-semibold transition-all cursor-pointer ${
                    statusFilter === tab
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {tab.replace('_', ' ')}
                </button>
              ))}
            </div>

          </div>

          {/* Queue List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {filteredAlerts.length === 0 ? (
              <div className="text-center py-12">
                <span className="text-slate-600 font-mono text-xs">
                  {feedStatus === 'running' ? 'Waiting for alerts...' : 'No alerts match criteria'}
                </span>
              </div>
            ) : (
              filteredAlerts.map(alert => {
                const stream = streamMap[alert.id]
                return (
                  <AlertCard
                    key={alert.id}
                    alert={alert}
                    isSelected={focusedId === alert.id}
                    isStreaming={streamingIds.has(alert.id)}
                    firewallFlagged={flaggedAlertIds.has(alert.id)}
                    streamStage={stream ? currentStage(stream.stages) : null}
                    streamError={stream?.error || null}
                    onClick={() => handleSelectAlert(alert)}
                    onRetry={(a) => {
                      dispatch({ alertId: a.id, event: 'investigation_error', data: { detail: null } })
                      dispatch({ alertId: a.id, event: 'investigation_started', data: {} })
                      setStreamingIds(prev => new Set([...prev, a.id]))
                    }}
                  />
                )
              })
            )}
          </div>
        </div>

        {/* ── Main Workspace Panel ── */}
        <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6 bg-slate-950/20">
          {activeView === 'topology' ? (
            <TopologyMap activeAlert={focusedAlert} streamState={focusedStream} alerts={liveQueueAlerts} />
          ) : activeView === 'memory' ? (
            <MemoryVault activeAlert={focusedAlert} streamState={focusedStream} />
          ) : activeView === 'hud' ? (
            <ExecutiveHUD alerts={alerts} />
          ) : focusedStream && focusedAlert ? (



            <div className="animate-fade-in space-y-6">
              
              {/* Alert Info Glass Card */}
              <div className="glass-panel rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4 border-emerald-500/20">
                <div className="flex items-center gap-4">
                  <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 font-mono text-xs">
                    ALERT ID
                  </div>
                  <div>
                    <div className="font-mono text-base font-bold text-white flex items-center gap-2">
                      <span>{focusedAlert.source_alert_id}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-normal">
                        {focusedAlert.alert_type?.replace(/_/g, ' ')}
                      </span>
                    </div>
                    <div className="text-xs font-mono text-slate-500">
                      Received: {focusedAlert.received_at ? new Date(focusedAlert.received_at).toLocaleString() : '—'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  {/* Firewall Flag Badge */}
                  {focusedStream.firewallFlags && (
                    <span className={`px-3 py-1 rounded-lg font-mono text-xs font-semibold border ${
                      focusedStream.firewallFlags.length > 0
                        ? 'bg-red-500/20 text-red-400 border-red-500/40 glow-red animate-pulse'
                        : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    }`}>
                      {focusedStream.firewallFlags.length > 0 ? '⚠ FIREWALL POISON FLAGGED' : '✓ LOG FIREWALL PASSED CLEAN'}
                    </span>
                  )}

                  {/* Compliance Report Button */}
                  <button
                    onClick={() => setShowComplianceModal(true)}
                    className="px-3.5 py-1.5 rounded-xl font-mono text-xs font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/25 glow-green transition-all cursor-pointer flex items-center gap-1.5"
                  >
                    <span>📄 VIEW COMPLIANCE REPORT</span>
                  </button>

                  {/* Human Approval Required Badge */}
                  {isAwaitingApproval && (
                    <button
                      onClick={handleOpenEscalation}
                      className="px-4 py-1.5 rounded-xl font-mono text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/50 hover:bg-amber-500/30 glow-amber transition-all cursor-pointer animate-pulse-glow"
                    >
                      ⚠ HUMAN APPROVAL REQUIRED — REVIEW & DECIDE →
                    </button>
                  )}

                </div>
              </div>

              {/* Workflow Node Graph */}
              <FlowChart
                stages={focusedStream.stages}
                firewallFlags={focusedStream.firewallFlags}
                primaryData={focusedStream.primary}
                secondaryData={focusedStream.secondary}
                caseResult={focusedStream.caseResult}
              />

              {/* Dual Agent Reasoning Matrix */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <AgentPanel
                  name="Primary Triage Agent"
                  status={focusedStream.primary.status}
                  reasoning={focusedStream.primary.reasoning}
                  verdict={focusedStream.primary.verdict}
                  confidence={focusedStream.primary.confidence}
                  extra={focusedStream.primary.extra}
                  alertTime={focusedAlert.received_at}
                />
                <AgentPanel
                  name="Secondary Deep Investigation Agent"
                  status={focusedStream.secondary.status}
                  reasoning={focusedStream.secondary.reasoning}
                  verdict={focusedStream.secondary.verdict}
                  confidence={focusedStream.secondary.confidence}
                  extra={focusedStream.secondary.extra}
                  alertTime={focusedAlert.received_at}
                />
              </div>

              {/* Deep Inspection Drawer (Enrichment, Memory RAG, Firewall Audit) */}
              <StageDetail
                stages={focusedStream.stages}
                enrichmentData={focusedStream.enrichment}
                memoryData={focusedStream.memory}
                firewallFlags={focusedStream.firewallFlags}
                alert={focusedAlert}
              />

              {/* Case Result Resolution Box */}
              {focusedStream.caseResult && (
                <div className="glass-panel rounded-2xl p-5 border-emerald-500/40 glow-green animate-slide-up">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full bg-emerald-400 animate-pulse" />
                      <span className="font-display font-bold text-base text-emerald-400 uppercase tracking-wider">
                        Case Outcome & Investigation Record Filed
                      </span>
                    </div>

                    {isAwaitingApproval && (
                      <button
                        onClick={handleOpenEscalation}
                        className="px-4 py-1 rounded-lg font-mono text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 hover:bg-amber-500/30 transition-all cursor-pointer"
                      >
                        ACTION DECISION PENDING — OVERRIDE NOW →
                      </button>
                    )}
                  </div>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-slate-950/60 p-4 rounded-xl border border-slate-800">
                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Primary Verdict</div>
                      <div className={`text-sm font-mono font-bold ${
                        focusedStream.caseResult.primary_verdict === 'true_positive' ? 'text-red-400' : 'text-emerald-400'
                      }`}>
                        {focusedStream.caseResult.primary_verdict?.replace('_', ' ').toUpperCase()}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Secondary Opinion</div>
                      <div className="text-sm font-mono font-bold text-cyan-400">
                        {focusedStream.caseResult.secondary_verdict?.replace('_', ' ').toUpperCase() || 'AGREE'}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Action Status</div>
                      <div className="text-sm font-mono font-bold text-amber-400">
                        {focusedStream.caseResult.action_status?.replace('_', ' ').toUpperCase() || 'NONE'}
                      </div>
                    </div>

                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Case UUID</div>
                      <div className="text-xs font-mono text-slate-400 truncate">
                        {focusedStream.caseResult.case_id}
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>
          ) : (
            /* Empty State */
            <div className="flex-1 flex flex-col items-center justify-center py-24 text-center">
              <div className="w-16 h-16 rounded-full border border-emerald-500/30 bg-emerald-500/10 flex items-center justify-center text-emerald-400 text-2xl mb-4 glow-green animate-float">
                ◉
              </div>
              <h3 className="font-display text-xl font-bold text-white mb-2">Autonomous Pipeline Ready</h3>
              <p className="text-slate-500 font-mono text-xs max-w-sm mb-6">
                {alerts.length > 0
                  ? 'Select an alert from the queue to inspect live investigation steps'
                  : feedStatus === 'running'
                    ? 'Listening for incoming security alert streams...'
                    : 'Start the live alert feed to trigger autonomous agent triage'}
              </p>
            </div>
          )}

        </div>
      </div>

      {/* Analyst Escalation Modal Dialog */}
      {showEscalationModal && activeCaseDetails && (
        <EscalationModal
          caseData={activeCaseDetails}
          alertData={focusedAlert}
          onClose={() => setShowEscalationModal(false)}
          onSubmitDecision={handleDecisionSubmitted}
        />
      )}

      {/* Executive Post-Incident Compliance Report Modal */}
      {showComplianceModal && (
        <ComplianceReportModal
          caseResult={focusedStream?.caseResult}
          alert={focusedAlert}
          onClose={() => setShowComplianceModal(false)}
        />
      )}


      {/* RAG Memory Writeback Toast */}
      <MemoryToast
        toast={memoryToast}
        onClose={() => setMemoryToast(null)}
      />

    </div>
  )
}
