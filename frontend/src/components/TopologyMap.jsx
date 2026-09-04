import React, { useState } from 'react'

/**
 * Autonomous Cyber SOC Architecture & Data-Flow Topology Map Component
 * Visualizes core platform pipeline nodes: Telemetry Ingestion, Log Firewall,
 * Primary Triage Agent, Secondary Deep Agent, RAG Memory Vault, Skill Enrichment,
 * Autonomous Action Engine, and Human Analyst Gating.
 */
export default function TopologyMap({ activeAlert, streamState, alerts = [] }) {
  const [selectedNode, setSelectedNode] = useState(null)
  const [simulatedPoison, setSimulatedPoison] = useState(false)

  // Current streaming status from props
  const stages = streamState?.stages || {}
  const primaryStatus = streamState?.primary?.status || 'idle'
  const secondaryStatus = streamState?.secondary?.status || 'idle'
  const isPoisoned = simulatedPoison || activeAlert?.source_alert_id?.includes('POISON') || streamState?.firewallFlags?.length > 0
  const isAwaitingApproval = streamState?.caseResult?.action_status === 'awaiting_approval' || streamState?.caseResult?.action_status === 'escalated'

  // Architecture System Nodes definition
  const nodes = [
    // 1. Ingestion & Perimeter Layer
    {
      id: 'ingestion',
      label: 'TELEMETRY INGESTION',
      subtext: 'Log Stream & SIEM',
      type: 'ingestion',
      x: 100,
      y: 130,
      status: stages.liveEnv === 'active' || stages.liveEnv === 'complete' ? 'active' : 'idle',
      icon: '📥',
      category: 'Ingress Stream',
      details: 'High-throughput telemetry ingestion pipeline collecting raw JSON security logs and SIEM feeds.',
      metrics: { throughput: '1.2k events/sec', buffer: 'Optimal', latency: '2ms' },
    },
    {
      id: 'firewall',
      label: 'LOG FIREWALL',
      subtext: 'Adversarial Prompt Sanitizer',
      type: 'firewall',
      x: 100,
      y: 310,
      status: isPoisoned ? 'poisoned' : (stages.firewall === 'active' || stages.firewall === 'complete' ? 'active' : 'idle'),
      icon: '🛡',
      category: 'Sanitization Perimeter',
      details: 'Inspects incoming log payloads for prompt injection attacks, jailbreaks, and adversarial poisoning before AI agent consumption.',
      metrics: { inspectionRules: '24 Rules', threatStatus: isPoisoned ? '⚠ POISON DETECTED' : '✓ Clean' },
    },

    // 2. Dual AI Intelligence Core
    {
      id: 'primary-agent',
      label: 'PRIMARY TRIAGE AGENT',
      subtext: 'Fast Signal Verdict',
      type: 'agent',
      x: 360,
      y: 130,
      status: primaryStatus === 'thinking' || primaryStatus === 'running' ? 'active' : (primaryStatus === 'complete' ? 'complete' : 'idle'),
      icon: '🤖',
      category: 'Primary LLM Core',
      details: 'Rapid-response triage agent performing initial threat classification, verdict generation, and ATT&CK mapping.',
      metrics: { model: 'Groq / gpt-oss-120b', avgResponseTime: '1.4s', confidence: streamState?.primary?.confidence ? `${(streamState.primary.confidence * 100).toFixed(0)}%` : '—' },
    },
    {
      id: 'secondary-agent',
      label: 'SECONDARY DEEP AGENT',
      subtext: 'Independent Cross-Check',
      type: 'agent',
      x: 360,
      y: 310,
      status: secondaryStatus === 'thinking' || secondaryStatus === 'running' ? 'active' : (secondaryStatus === 'complete' ? 'complete' : 'idle'),
      icon: '🧠',
      category: 'Independent Auditor',
      details: 'Independent secondary agent that re-examines evidence without bias, cross-checking the primary verdict against RAG memory.',
      metrics: { model: 'Cerebras / gpt-oss-120b', crossCheckResult: streamState?.secondary?.verdict || 'Standby', agreement: '100%' },
    },

    // 3. Knowledge & Skill Matrix
    {
      id: 'rag-memory',
      label: 'RAG MEMORY VAULT',
      subtext: 'Supabase Vector Store',
      type: 'memory',
      x: 620,
      y: 130,
      status: stages.investigation === 'complete' ? 'active' : 'idle',
      icon: '💾',
      category: 'Knowledge Store',
      details: 'Vector database storing past incident cases, similar threat patterns, and analyst correction feedback for RAG recall.',
      metrics: { recordsCount: '1,420 Cases', similarityThreshold: '0.78', recallTime: '18ms' },
    },
    {
      id: 'skill-enrichment',
      label: '4-SKILL ENRICHMENT',
      subtext: 'OTX, ATT&CK, Correlation',
      type: 'enrichment',
      x: 620,
      y: 310,
      status: stages.enrichment === 'complete' ? 'complete' : 'idle',
      icon: '🔍',
      category: 'Threat Intel Engine',
      details: 'Automated skill suite querying AlienVault OTX Threat Intel, MITRE ATT&CK techniques, log correlation, and behavioral deviation.',
      metrics: { otxMatches: 'Active', attackMapping: 'Enabled', deviationHeuristic: '0.88' },
    },

    // 4. Action Cascade & Human Gating
    {
      id: 'action-engine',
      label: 'AUTONOMOUS ACTION',
      subtext: 'Low-Impact Auto Dispatcher',
      type: 'action',
      x: 860,
      y: 130,
      status: stages.action === 'complete' && !isAwaitingApproval ? 'complete' : 'idle',
      icon: '⚡',
      category: 'Automated Response',
      details: 'Executes safe, low-impact containment actions (IP blocking, ticket creation) autonomously when confidence threshold is met.',
      metrics: { autonomousRules: 'Standard Catalog', autoExecute: 'Enabled' },
    },
    {
      id: 'human-gating',
      label: 'HUMAN ANALYST GATING',
      subtext: 'High-Impact Escalation',
      type: 'gating',
      x: 860,
      y: 310,
      status: isAwaitingApproval ? 'escalated' : (stages.db === 'complete' ? 'complete' : 'idle'),
      icon: '👤',
      category: 'Escalation Safeguard',
      details: 'Mandatory human approval gate for high-impact response actions (host isolation, account lockouts).',
      metrics: { gatingPolicy: 'Enforced Logic', approvalState: isAwaitingApproval ? '⚠ AWAITING ANALYST' : 'Verified' },
    },
  ]

  // Data flow connections between architecture components
  const connections = [
    { from: 'ingestion', to: 'firewall', active: true, color: '#38bdf8' },
    { from: 'firewall', to: 'primary-agent', active: stages.primary === 'active' || stages.primary === 'complete', color: isPoisoned ? '#ec4899' : '#38bdf8' },
    { from: 'primary-agent', to: 'rag-memory', active: stages.primary === 'active' || stages.primary === 'complete', color: '#10b981' },
    { from: 'primary-agent', to: 'skill-enrichment', active: stages.enrichment === 'complete', color: '#10b981' },
    { from: 'skill-enrichment', to: 'secondary-agent', active: stages.secondary === 'active' || stages.secondary === 'complete', color: '#a855f7' },
    { from: 'secondary-agent', to: 'action-engine', active: stages.action === 'complete' && !isAwaitingApproval, color: '#10b981' },
    { from: 'secondary-agent', to: 'human-gating', active: isAwaitingApproval || stages.db === 'complete', color: isAwaitingApproval ? '#f59e0b' : '#10b981' },
  ]

  const getNodeColor = (node) => {
    switch (node.status) {
      case 'active': return { fill: 'rgba(56, 189, 248, 0.2)', stroke: '#38bdf8', text: '#7dd3fc' }
      case 'complete': return { fill: 'rgba(16, 185, 129, 0.2)', stroke: '#10b981', text: '#6ee7b7' }
      case 'poisoned': return { fill: 'rgba(236, 72, 153, 0.25)', stroke: '#ec4899', text: '#fbcfe8' }
      case 'escalated': return { fill: 'rgba(245, 158, 11, 0.25)', stroke: '#f59e0b', text: '#fcd34d' }
      case 'idle': default: return { fill: 'rgba(30, 41, 59, 0.5)', stroke: '#475569', text: '#94a3b8' }
    }
  }

  const activeNodeObj = selectedNode ? nodes.find(n => n.id === selectedNode) : null

  return (
    <div className="glass-panel rounded-2xl p-6 border border-slate-800 space-y-4 animate-fade-in relative overflow-hidden">
      
      {/* Topology Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
            <h3 className="font-display font-bold text-base text-white tracking-wide">
              AUTONOMOUS SOC ARCHITECTURE & DATA-FLOW TOPOLOGY MAP
            </h3>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-0.5">
            Interactive map visualizing the live flow of security telemetry across Ingestion, Log Firewall, Dual AI Agents, RAG Memory, and Action Cascade.
          </p>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping" />
            <span className="text-cyan-300">Active Flow</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-pink-500" />
            <span className="text-pink-400">Poison Flagged</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <span className="text-amber-300">Human Escalation</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
            <span className="text-emerald-300">Complete / Secured</span>
          </div>
        </div>
      </div>

      {/* SVG Architecture Map Canvas */}
      <div className="relative w-full h-[400px] bg-slate-950/90 rounded-xl border border-slate-900 overflow-hidden flex items-center justify-center">
        
        {/* Background Grid Pattern */}
        <div className="absolute inset-0 opacity-15 bg-[radial-gradient(#38bdf8_1px,transparent_1px)] [background-size:18px_18px]" />

        <svg className="w-full h-full relative z-10" viewBox="0 0 960 420">
          <defs>
            <filter id="glow-cyan" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="glow-amber" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
            <filter id="glow-pink" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feComposite in="SourceGraphic" in2="blur" operator="over" />
            </filter>
          </defs>

          {/* Render Connections */}
          {connections.map((conn, idx) => {
            const source = nodes.find(n => n.id === conn.from)
            const target = nodes.find(n => n.id === conn.to)
            if (!source || !target) return null

            return (
              <g key={idx}>
                {/* Base Vector Connection */}
                <path
                  d={`M ${source.x} ${source.y} C ${(source.x + target.x) / 2} ${source.y}, ${(source.x + target.x) / 2} ${target.y}, ${target.x} ${target.y}`}
                  fill="none"
                  stroke={conn.active ? conn.color : '#1e293b'}
                  strokeWidth={conn.active ? 2.5 : 1}
                  strokeDasharray={conn.active ? '6,6' : 'none'}
                  className={conn.active ? 'animate-pulse' : ''}
                />

                {/* Animated Flow Pulse Ball */}
                {conn.active && (
                  <circle r="4" fill={conn.color} filter="url(#glow-cyan)">
                    <animateMotion
                      path={`M ${source.x} ${source.y} C ${(source.x + target.x) / 2} ${source.y}, ${(source.x + target.x) / 2} ${target.y}, ${target.x} ${target.y}`}
                      dur="2s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            )
          })}

          {/* Render System Architecture Nodes */}
          {nodes.map((node) => {
            const colors = getNodeColor(node)
            const isSelected = selectedNode === node.id

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onClick={() => setSelectedNode(node.id)}
                className="cursor-pointer group"
              >
                {/* Outer Ring Effect */}
                {node.status === 'active' && (
                  <circle
                    r="34"
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="1.5"
                    className="animate-ping opacity-50"
                  />
                )}
                {node.status === 'escalated' && (
                  <circle
                    r="34"
                    fill="none"
                    stroke="#f59e0b"
                    strokeWidth="1.5"
                    className="animate-ping opacity-60"
                  />
                )}

                {/* Main Node Body Circle */}
                <circle
                  r="26"
                  fill={colors.fill}
                  stroke={isSelected ? '#38bdf8' : colors.stroke}
                  strokeWidth={isSelected ? 3 : 2}
                  className="transition-all duration-300 group-hover:scale-110"
                  filter={node.status === 'escalated' ? 'url(#glow-amber)' : (node.status === 'poisoned' ? 'url(#glow-pink)' : 'none')}
                />

                {/* Node Icon */}
                <text
                  textAnchor="middle"
                  dy="5"
                  fontSize="15"
                  className="select-none"
                >
                  {node.icon}
                </text>

                {/* Node Label Text */}
                <text
                  textAnchor="middle"
                  dy="44"
                  fill="#f1f5f9"
                  fontSize="11"
                  fontFamily="monospace"
                  fontWeight="bold"
                  className="drop-shadow-md"
                >
                  {node.label}
                </text>

                {/* Subtext */}
                <text
                  textAnchor="middle"
                  dy="58"
                  fill="#64748b"
                  fontSize="9"
                  fontFamily="monospace"
                >
                  {node.subtext}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Floating Interactive Node Inspector Drawer */}
        {activeNodeObj && (
          <div className="absolute top-4 right-4 w-80 glass-panel p-4 rounded-xl border border-cyan-500/40 shadow-2xl z-20 space-y-3 animate-slide-up">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="font-mono text-xs font-bold text-cyan-400 uppercase tracking-wider">Architecture Inspector</span>
              <button
                onClick={() => setSelectedNode(null)}
                className="text-slate-500 hover:text-white font-mono text-xs"
              >
                ✕
              </button>
            </div>

            <div>
              <div className="text-sm font-mono font-bold text-white flex items-center justify-between">
                <span>{activeNodeObj.label}</span>
                <span className={`text-[10px] px-2 py-0.5 rounded font-mono font-semibold uppercase ${
                  activeNodeObj.status === 'poisoned' ? 'bg-pink-500/20 text-pink-300 border border-pink-500/40' :
                  activeNodeObj.status === 'escalated' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40' :
                  activeNodeObj.status === 'active' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40' :
                  'bg-slate-800 text-slate-400'
                }`}>
                  {activeNodeObj.status}
                </span>
              </div>
              <div className="text-xs font-mono text-slate-400 mt-0.5">Category: {activeNodeObj.category}</div>
              <div className="text-[11px] text-slate-300 font-mono mt-2 leading-relaxed">
                {activeNodeObj.details}
              </div>
            </div>

            {/* Live Metrics Grid */}
            <div className="p-2.5 rounded-lg border border-slate-800 bg-slate-950/80 space-y-1">
              <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider mb-1">Live Telemetry & State</div>
              {Object.entries(activeNodeObj.metrics).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400 capitalize">{k.replace(/([A-Z])/g, ' $1')}:</span>
                  <span className="text-cyan-300 font-semibold">{v}</span>
                </div>
              ))}
            </div>

            {/* Interactive Simulation Controls */}
            {activeNodeObj.id === 'firewall' && (
              <div className="space-y-2">
                <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
                  Demo Simulation Control
                </div>
                <button
                  onClick={() => setSimulatedPoison(prev => !prev)}
                  className={`w-full py-1.5 rounded-lg font-mono text-xs font-semibold border transition-all ${
                    isPoisoned
                      ? 'bg-pink-500/20 text-pink-300 border-pink-500/50 hover:bg-pink-500/30'
                      : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50 hover:bg-cyan-500/30'
                  }`}
                >
                  {isPoisoned ? '✓ RESET SIMULATED POISON' : '🧪 SIMULATE POISON PAYLOAD'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>

    </div>
  )
}
