import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import FlowDiagram from '../components/FlowDiagram'
import AgentPanel from '../components/AgentPanel'
import { useSSE } from '../hooks/useSSE'
import { getAlerts, getFirewallFlags } from '../utils/api'

export default function Orchestration() {
  const { client } = useParams()
  const [alerts, setAlerts] = useState([])
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [stages, setStages] = useState({
    liveEnv: 'pending',
    firewall: 'pending',
    primary: 'pending',
    secondary: 'pending',
    action: 'pending',
    db: 'pending',
  })
  const [primaryStatus, setPrimaryStatus] = useState('idle')
  const [secondaryStatus, setSecondaryStatus] = useState('idle')
  const [primaryReasoning, setPrimaryReasoning] = useState(null)
  const [secondaryReasoning, setSecondaryReasoning] = useState(null)
  const [primaryVerdict, setPrimaryVerdict] = useState(null)
  const [secondaryVerdict, setSecondaryVerdict] = useState(null)
  const [actionResult, setActionResult] = useState(null)
  const [firewallFlags, setFirewallFlags] = useState(null)
  const [completedCaseId, setCompletedCaseId] = useState(null)

  // Poll for new LIVE alerts
  useEffect(() => {
    const pollAlerts = async () => {
      try {
        const newAlerts = await getAlerts(50)
        const liveAlerts = newAlerts.filter(a => a.source_alert_id?.startsWith('LIVE-'))
        setAlerts(liveAlerts)
        
        // Auto-select first alert if none selected
        if (!selectedAlert && liveAlerts.length > 0) {
          setSelectedAlert(liveAlerts[0])
        }
      } catch (err) {
        console.error('Failed to fetch alerts:', err)
      }
    }

    pollAlerts()
    const interval = setInterval(pollAlerts, 3000)
    return () => clearInterval(interval)
  }, [selectedAlert])

  // Fetch firewall flags when alert is selected
  useEffect(() => {
    if (!selectedAlert) return
    
    setFirewallFlags(null)
    getFirewallFlags(selectedAlert.id)
      .then(flags => setFirewallFlags(flags))
      .catch(err => {
        console.error('Failed to fetch firewall flags:', err)
        setFirewallFlags([])
      })
  }, [selectedAlert])

  // Reset stages when alert changes
  useEffect(() => {
    if (selectedAlert) {
      setStages({
        liveEnv: 'complete',
        firewall: 'pending',
        primary: 'pending',
        secondary: 'pending',
        action: 'pending',
        db: 'pending',
      })
      setPrimaryStatus('idle')
      setSecondaryStatus('idle')
      setPrimaryReasoning(null)
      setSecondaryReasoning(null)
      setPrimaryVerdict(null)
      setSecondaryVerdict(null)
      setActionResult(null)
      setCompletedCaseId(null)
      
      // Mark firewall as checked once flags are loaded
      if (firewallFlags !== null) {
        setStages(prev => ({ ...prev, firewall: firewallFlags.length > 0 ? 'flagged' : 'complete' }))
      }
    }
  }, [selectedAlert])

  // Handle SSE events
  const handleEvent = useCallback(({ event, data }) => {
    switch (event) {
      case 'investigation_started':
        setStages(prev => ({ ...prev, liveEnv: 'complete', firewall: 'active' }))
        break
        
      case 'memory_retrieved':
        if (data.agent === 'primary') {
          setStages(prev => ({ ...prev, firewall: firewallFlags?.length > 0 ? 'flagged' : 'complete', primary: 'active' }))
        } else {
          setStages(prev => ({ ...prev, secondary: 'active' }))
        }
        break
        
      case 'agent_started':
        if (data.agent === 'primary') {
          setPrimaryStatus('thinking')
        } else {
          setSecondaryStatus('thinking')
        }
        break
        
      case 'agent_status':
        // agent.thinking is the live signal
        break
        
      case 'agent_delta':
        // Full reasoning text arrives here (message granularity)
        break
        
      case 'agent_complete':
        if (data.agent === 'primary') {
          setPrimaryStatus('complete')
          setPrimaryVerdict({
            verdict: data.verdict,
            confidence: data.confidence,
          })
          setPrimaryReasoning(data.reasoning)
          setStages(prev => ({ ...prev, primary: 'complete' }))
        } else {
          setSecondaryStatus('complete')
          setSecondaryVerdict({
            verdict: data.secondary_verdict || data.verdict,
            confidence: data.confidence,
          })
          setSecondaryReasoning(data.reasoning)
          setStages(prev => ({ ...prev, secondary: 'complete', action: 'active' }))
        }
        break
        
      case 'case_persisted':
        setStages(prev => ({ ...prev, action: 'complete', db: 'active' }))
        break
        
      case 'action_decided':
        setActionResult(data)
        setStages(prev => ({ ...prev, action: 'complete' }))
        break
        
      case 'investigation_complete':
        setStages(prev => ({ ...prev, db: 'complete' }))
        setCompletedCaseId(data.case_id)
        break
        
      case 'investigation_error':
        console.error('Investigation error:', data.detail)
        break
    }
  }, [firewallFlags])

  useSSE(selectedAlert?.id, handleEvent, (err) => {
    console.error('SSE error:', err)
  })

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6 flex items-center justify-between">
          <div>
            <Link to="/" className="text-sm text-blue-600 hover:underline mb-2 inline-block">
              ← Back to Dashboard
            </Link>
            <h1 className="text-2xl font-bold text-gray-900">
              {client?.toUpperCase()}'s Live Environment
            </h1>
          </div>
          {selectedAlert && (
            <div className="text-sm text-gray-600">
              Alert: <span className="font-mono">{selectedAlert.source_alert_id}</span>
            </div>
          )}
        </header>

        {/* Flow Diagram */}
        <div className="mb-6">
          <FlowDiagram stages={stages} firewallFlags={firewallFlags} />
        </div>

        {/* Agent Panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <AgentPanel
            agentName="primary"
            status={primaryStatus}
            reasoning={primaryReasoning}
            verdict={primaryVerdict}
          />
          <AgentPanel
            agentName="secondary"
            status={secondaryStatus}
            reasoning={secondaryReasoning}
            verdict={secondaryVerdict}
          />
        </div>

        {/* Action Result */}
        {actionResult && (
          <div className="bg-white rounded-lg shadow p-4 border border-gray-200">
            <h3 className="font-semibold text-gray-800 mb-2">Response Action</h3>
            <div className="text-sm space-y-1">
              <div>
                <strong>Action:</strong> {actionResult.action_id}
              </div>
              <div>
                <strong>Status:</strong>{' '}
                <span className={
                  actionResult.action_status === 'executed' ? 'text-green-600' :
                  actionResult.action_status === 'awaiting_approval' ? 'text-orange-600' :
                  'text-gray-600'
                }>
                  {actionResult.action_status}
                </span>
              </div>
              {actionResult.target && (
                <div>
                  <strong>Target:</strong> {actionResult.target}
                </div>
              )}
              {actionResult.rationale && (
                <div className="text-gray-600 italic mt-2">
                  {actionResult.rationale}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Case Link */}
        {completedCaseId && (
          <div className="mt-4 text-center">
            <Link
              to={`/cases/${completedCaseId}`}
              className="text-sm text-blue-600 hover:underline"
            >
              View Case Detail →
            </Link>
          </div>
        )}

        {/* Alert Queue */}
        {alerts.length > 1 && (
          <div className="mt-6 bg-white rounded-lg shadow p-4 border border-gray-200">
            <h3 className="font-semibold text-gray-800 mb-3">Alert Queue</h3>
            <div className="space-y-2">
              {alerts.slice(0, 10).map(alert => (
                <button
                  key={alert.id}
                  onClick={() => setSelectedAlert(alert)}
                  className={`w-full text-left px-3 py-2 rounded text-sm ${
                    selectedAlert?.id === alert.id
                      ? 'bg-blue-50 border-2 border-blue-400'
                      : 'bg-gray-50 border border-gray-200 hover:bg-gray-100'
                  }`}
                >
                  <div className="flex justify-between items-center">
                    <span className="font-mono">{alert.source_alert_id}</span>
                    <span className="text-xs text-gray-500">{alert.alert_type}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
