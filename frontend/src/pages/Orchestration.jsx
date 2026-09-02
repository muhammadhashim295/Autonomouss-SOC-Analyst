import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import FlowDiagram from '../components/FlowDiagram'
import AgentPanel from '../components/AgentPanel'
import AlertCard from '../components/AlertCard'
import LiveStatsBar from '../components/LiveStatsBar'
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

export default function Orchestration() {
  const { client } = useParams()
  const displayName = client.charAt(0).toUpperCase() + client.slice(1).replace(/-/g, ' ')

  // Alert queue
  const [alerts, setAlerts] = useState([])
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [streamingAlertId, setStreamingAlertId] = useState(null)
  const [firewallFlags, setFirewallFlags] = useState(null)
  const [flaggedAlertIds, setFlaggedAlertIds] = useState(new Set())

  // Pipeline stages
  const [stages, setStages] = useState(INIT_STAGES)

  // Agent state
  const [primary, setPrimary] = useState({ status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} })
  const [secondary, setSecondary] = useState({ status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} })

  // Case result
  const [caseResult, setCaseResult] = useState(null)

  // Feed status + mode
  const [feedStatus, setFeedStatus] = useState('idle')
  const [feedStats, setFeedStats] = useState(null)
  const [mode, setMode] = useState('agentic')

  // ── SSE event handler ──
  const handleSSE = useCallback((e) => {
    switch (e.event) {
      case 'investigation_started':
        setStages(s => ({ ...s, liveEnv: 'active', investigation: 'active' }))
        break
      case 'memory_retrieved':
        setStages(s => ({ ...s, investigation: 'complete' }))
        break
      case 'enrichment_complete':
        setStages(s => ({ ...s, enrichment: 'complete', firewall: 'complete' }))
        break
      case 'agent_started':
        if (e.data.agent === 'primary') {
          setStages(s => ({ ...s, primary: 'active' }))
          setPrimary(p => ({ ...p, status: 'thinking' }))
        } else {
          setStages(s => ({ ...s, primary: 'complete', secondary: 'active' }))
          setSecondary(p => ({ ...p, status: 'thinking' }))
        }
        break
      case 'agent_status':
        // Thinking indicator is already shown via 'thinking' status — no-op
        break
      case 'agent_delta':
        if (e.data.agent === 'primary') {
          setPrimary(p => ({ ...p, reasoning: e.data.text }))
        } else {
          setSecondary(p => ({ ...p, reasoning: e.data.text }))
        }
        break
      case 'agent_complete':
        if (e.data.agent === 'primary') {
          setPrimary(p => ({
            ...p, status: 'complete',
            reasoning: p.reasoning || e.data.reasoning,
            verdict: e.data.verdict, confidence: e.data.confidence,
            extra: { attack_technique: e.data.attack_technique },
          }))
        } else {
          setSecondary(p => ({
            ...p, status: 'complete',
            reasoning: p.reasoning || e.data.reasoning,
            verdict: e.data.verdict, confidence: e.data.confidence,
            extra: { secondary_verdict: e.data.secondary_verdict, impact_level: e.data.impact_level },
          }))
          setStages(s => ({ ...s, secondary: 'complete' }))
        }
        break
      case 'case_persisted':
        setStages(s => ({ ...s, action: 'active' }))
        break
      case 'action_decided':
        setStages(s => ({ ...s, action: 'complete', db: 'active' }))
        break
      case 'investigation_complete':
        setStages(s => ({ ...s, db: 'complete' }))
        setStreamingAlertId(null)
        setCaseResult(e.data)
        break
      case 'investigation_error':
        setStreamingAlertId(null)
        break
    }
  }, [])

  useSSE(streamingAlertId, handleSSE)

  // ── Data fetching ──
  const refreshAlerts = useCallback(async () => {
    try {
      const data = await getAlerts(30)
      setAlerts(data)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    refreshAlerts()
    const t = setInterval(refreshAlerts, 3000)
    return () => clearInterval(t)
  }, [refreshAlerts])

  const refreshFeedStatus = useCallback(async () => {
    try {
      const s = await getLiveFeedStatus()
      setFeedStatus(s.status)
      setFeedStats(s.status === 'running' ? s : null)
    } catch { /* silent */ }
  }, [])

  useEffect(() => {
    refreshFeedStatus()
    const t = setInterval(refreshFeedStatus, 2000)
    return () => clearInterval(t)
  }, [refreshFeedStatus])

  useEffect(() => {
    getMode().then(m => setMode(m.mode)).catch(() => {})
  }, [])

  // ── Fetch firewall flags for ALL alerts ──
  useEffect(() => {
    if (alerts.length === 0) return
    getFirewallFlags().then(flags => {
      const ids = new Set(flags.map(f => f.alert_id))
      setFlaggedAlertIds(ids)
    }).catch(() => {})
  }, [alerts])

  // ── Actions ──
  const handleSelectAlert = (alert) => {
    if (streamingAlertId) return // don't switch while streaming
    setSelectedAlert(alert)
    setStages(INIT_STAGES)
    setPrimary({ status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} })
    setSecondary({ status: 'idle', reasoning: null, verdict: null, confidence: null, extra: {} })
    setCaseResult(null)
    setFirewallFlags(null)
    setStreamingAlertId(alert.id)

    getFirewallFlags(alert.id).then(setFirewallFlags).catch(() => {})
  }

  const handleStopFeed = async () => {
    try { await stopLiveFeed(); refreshFeedStatus() } catch { /* silent */ }
  }

  const handleModeToggle = async () => {
    try {
      const next = mode === 'agentic' ? 'approval' : 'agentic'
      const r = await setModeAPI(next)
      setMode(r.mode)
    } catch { /* silent */ }
  }

  // ── Render ──
  return (
    <div className="min-h-screen bg-[#050705] flex flex-col">
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
        </div>
        <div className="flex items-center gap-3">
          {feedStatus === 'running' ? (
            <button onClick={handleStopFeed}
              className="px-3 py-1 rounded font-mono text-xs border border-red-500/30 text-red-400 bg-red-500/10 hover:bg-red-500/20 transition-all">
              STOP FEED
            </button>
          ) : (
            <span className="font-mono text-xs text-slate-600">Feed stopped</span>
          )}
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* ── Alert Queue Sidebar ── */}
        <div className="w-72 border-r border-slate-800/50 flex flex-col bg-slate-950/30">
          <div className="px-3 py-2.5 border-b border-slate-800/50 flex items-center justify-between">
            <span className="font-mono text-xs text-slate-500 uppercase tracking-wider">Alert Queue</span>
            <span className="font-mono text-xs text-emerald-500">{alerts.length}</span>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {alerts.length === 0 ? (
              <div className="text-center py-8">
                <span className="text-slate-600 font-mono text-xs">No alerts yet</span>
              </div>
            ) : (
              alerts.map(alert => (
                <AlertCard
                  key={alert.id} alert={alert}
                  isSelected={selectedAlert?.id === alert.id}
                  isStreaming={streamingAlertId === alert.id}
                  firewallFlagged={flaggedAlertIds.has(alert.id)}
                  onClick={() => handleSelectAlert(alert)}
                />
              ))
            )}
          </div>
        </div>

        {/* ── Main Panel ── */}
        <div className="flex-1 flex flex-col overflow-y-auto p-4 space-y-4">
          {selectedAlert ? (
            <div className="animate-fade-in">
              {/* Alert info bar */}
              <div className="flex items-center gap-4 mb-4 px-2">
                <span className="font-mono text-xs text-slate-500">
                  ALERT: <span className="text-cyan-400">{selectedAlert.source_alert_id}</span>
                </span>
                <span className="font-mono text-xs text-slate-700">│</span>
                <span className="font-mono text-xs text-slate-500">{selectedAlert.alert_type}</span>
                {firewallFlags !== null && (
                  <>
                    <span className="font-mono text-xs text-slate-700">│</span>
                    <span className={`font-mono text-xs ${firewallFlags.length > 0 ? 'text-red-400' : 'text-emerald-500/70'}`}>
                      {firewallFlags.length > 0 ? `${firewallFlags.length} FLAG(S)` : 'CLEAN'}
                    </span>
                  </>
                )}
              </div>

              {/* Flow Diagram */}
              <FlowDiagram stages={stages} firewallFlags={firewallFlags} />

              {/* Agent Reasoning Panels */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-4">
                <AgentPanel
                  name="Primary Agent" status={primary.status}
                  reasoning={primary.reasoning} verdict={primary.verdict}
                  confidence={primary.confidence} extra={primary.extra}
                />
                <AgentPanel
                  name="Secondary Agent" status={secondary.status}
                  reasoning={secondary.reasoning} verdict={secondary.verdict}
                  confidence={secondary.confidence} extra={secondary.extra}
                />
              </div>

              {/* Case Result */}
              {caseResult && (
                <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-950/15 p-4 glow-green animate-slide-in">
                  <div className="flex items-center gap-2 mb-3">
                    <div className="w-2 h-2 rounded-full bg-emerald-400" />
                    <span className="font-mono text-xs text-emerald-400 uppercase tracking-wider">Case Filed</span>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Verdict</div>
                      <div className={`text-sm font-mono ${
                        caseResult.primary_verdict === 'true_positive' ? 'text-red-400' : 'text-emerald-400'
                      }`}>
                        {caseResult.primary_verdict?.replace('_', ' ').toUpperCase()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">2nd Opinion</div>
                      <div className="text-sm font-mono text-cyan-400">
                        {caseResult.secondary_verdict?.replace('_', ' ').toUpperCase() || '—'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Action</div>
                      <div className="text-sm font-mono text-yellow-400">
                        {caseResult.action_status || 'NONE'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500 font-mono mb-1">Case ID</div>
                      <div className="text-xs font-mono text-slate-400 truncate">{caseResult.case_id}</div>
                    </div>
                  </div>
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
                    ? 'Select an alert from the queue to investigate'
                    : feedStatus === 'running'
                      ? 'Waiting for alerts...'
                      : 'Start the live feed to generate alerts'}
                </p>
                <div className="flex items-center justify-center gap-2 mt-4">
                  <div className={`w-1.5 h-1.5 rounded-full ${
                    feedStatus === 'running' ? 'bg-emerald-400 animate-pulse' : 'bg-slate-700'
                  }`} />
                  <span className="font-mono text-xs text-slate-700">
                    {feedStatus === 'running' ? 'Feed active' : 'Feed idle'}
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
