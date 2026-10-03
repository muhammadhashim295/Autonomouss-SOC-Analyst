import React from 'react'

/**
 * FlowChart — Real-Time Visual Workflow Pipeline Architecture
 *
 * A connected, left-to-right pipeline strip whose nodes light up in real time as
 * the focused alert advances, with animated directional connectors showing the
 * live path and a pulsing "current stage" indicator:
 *
 * 1. Ingestion (Live Ingest) →
 * 2. Log Firewall            → [Clean] or [⚠ Quarantined]
 * 3. Primary Triage          → [TP] or [✓ FP Auto-Close]
 * 4. Secondary Auditor       → [Confirmed] or [Disputed]
 * 5. Response Action Engine  → [Autonomous] or [⚠ Human Gated]
 * 6. Audit & Memory Vault
 *
 * Below the strip, a Decision Branch matrix explains which gating rule fired.
 */

const ADVANCED = ['active', 'complete', 'error', 'warning', 'bypassed']

export default function FlowChart({
  stages = {},
  firewallFlags = null,
  primaryData = null,
  secondaryData = null,
  caseResult = null,
}) {
  // Determine decision branches from live data
  const hasFlags = Boolean(firewallFlags && firewallFlags.length > 0)
  const isFirewallComplete = stages?.firewall === 'complete' || hasFlags
  const isFirewallActive = stages?.firewall === 'active'

  const primaryVerdict = primaryData?.verdict
  const isPrimaryFP = primaryVerdict === 'false_positive'
  const isPrimaryTP = primaryVerdict === 'true_positive'
  const isPrimaryActive = stages?.primary === 'active' || primaryData?.status === 'thinking'

  const secondaryVerdict = secondaryData?.verdict || secondaryData?.extra?.secondary_verdict || secondaryData?.secondary_verdict
  const isSecondaryFP = secondaryVerdict === 'false_positive'
  const isSecondaryTP = secondaryVerdict === 'true_positive' || secondaryVerdict === 'agree'
  const isSecondaryDispute = secondaryVerdict === 'disagree'
  const isSecondaryActive = stages?.secondary === 'active' || secondaryData?.status === 'thinking'

  const actionStatus = caseResult?.action_status
  const isActionExecuted = actionStatus === 'executed'
  const isActionGated = actionStatus === 'awaiting_approval' || actionStatus === 'escalated'
  const isActionActive = stages?.action === 'active'

  const st = (key) => stages?.[key] || 'pending'
  const dbActive = st('db') === 'active'

  // ── Resolved definition for each pipeline node ──
  const nodes = [
    {
      id: 'liveEnv', step: '1', title: 'Ingestion', provider: 'Live Ingest Pipeline', icon: '📥',
      status: st('liveEnv') === 'active' ? 'active' : st('liveEnv') === 'complete' ? 'complete' : 'ready',
      statusLabel: st('liveEnv') === 'active' ? '▶ Streaming' : 'Telemetry Active',
      description: 'Normalized SIEM log ingest',
      highlight: !hasFlags,
    },
    {
      id: 'firewall', step: '2', title: 'Log Firewall', provider: 'Rule Sanitizer', icon: '🛡',
      status: hasFlags ? 'error' : isFirewallActive ? 'active' : isFirewallComplete ? 'complete' : 'ready',
      statusLabel: hasFlags ? '⚠ POISON DETECTED' : isFirewallActive ? '▶ Scanning…' : isFirewallComplete ? '✓ Sanitized Clean' : '24 Pattern Rules',
      description: hasFlags ? 'Quarantine triggered' : 'Prompt injection check',
      highlight: hasFlags || isFirewallActive || isFirewallComplete,
      isAlert: hasFlags,
    },
    {
      id: 'primary', step: '3', title: 'Primary Triage', provider: 'High-Speed Reasoning Core', icon: '▣',
      status: hasFlags ? 'bypassed' : isPrimaryActive ? 'active' : st('primary') === 'complete' ? 'complete' : 'ready',
      statusLabel:
        hasFlags ? 'Bypassed (0 Calls)' :
        isPrimaryTP ? '⚡ True Positive' :
        isPrimaryFP ? '✓ False Positive' :
        isPrimaryActive ? '▶ Reasoning Live…' : 'Signal Classifier',
      description:
        hasFlags ? 'Bypassed by firewall' :
        isPrimaryTP ? 'Threat confirmed' :
        isPrimaryFP ? 'Benign activity' : 'Fast MITRE taxonomy',
      highlight: !hasFlags && (isPrimaryTP || isPrimaryFP || isPrimaryActive),
    },
    {
      id: 'secondary', step: '4', title: 'Secondary Auditor', provider: 'Forensic Auditor Core', icon: '◫',
      status:
        hasFlags || isPrimaryFP ? 'bypassed' :
        isSecondaryActive ? 'active' :
        st('secondary') === 'complete' ? 'complete' : 'ready',
      statusLabel:
        hasFlags ? 'Bypassed (0 Calls)' :
        isPrimaryFP ? 'Bypassed (FP Closed)' :
        isSecondaryTP ? '⚡ Threat Validated' :
        isSecondaryDispute ? '⚠ Disputed' :
        isSecondaryFP ? '✓ Overruled FP' :
        isSecondaryActive ? '▶ Auditing Live…' : 'Cross-Validation',
      description:
        hasFlags || isPrimaryFP ? 'Zero agent invocation' :
        isSecondaryTP ? 'Dual-agent consensus' : 'Independent verification',
      highlight: !hasFlags && !isPrimaryFP && (isSecondaryTP || isSecondaryActive),
    },
    {
      id: 'action', step: '5', title: 'Response Engine', provider: 'Policy Gating', icon: '⚡',
      status:
        hasFlags ? 'bypassed' :
        isActionActive ? 'active' :
        isActionExecuted ? 'complete' :
        isActionGated ? 'warning' : 'ready',
      statusLabel:
        hasFlags ? 'Bypassed' :
        isActionActive ? '▶ Deciding…' :
        isActionExecuted ? '✓ Autonomous Executed' :
        isActionGated ? '⚠ Human Approval Gated' : 'Action Catalog',
      description:
        hasFlags ? 'Direct quarantine' :
        isActionExecuted ? 'Perimeter block active' :
        isActionGated ? 'Impact threshold exceeded' : 'Risk & impact matrix',
      highlight: !hasFlags && (isActionExecuted || isActionGated || isActionActive),
      isWarning: isActionGated,
    },
    {
      id: 'db', step: '6', title: 'Audit & Memory Vault', provider: 'Case Intel & Ledger', icon: '💾',
      status: st('db') === 'complete' ? 'complete' : dbActive ? 'active' : 'ready',
      statusLabel: st('db') === 'complete' ? '✓ Record Persisted' : dbActive ? '▶ Writing…' : 'Audit Ready',
      description:
        caseResult?.case_id ? `Case: ${caseResult.case_id.slice(0, 8)}…` :
        'Case memory writeback',
      highlight: st('db') === 'complete' || dbActive,
    },
  ]

  // ── Current live stage indicator ──
  const activeNode = nodes.find((n) => n.status === 'active')
  const isTerminal = caseResult != null || hasFlags
  let currentStageText = 'Standby — awaiting alert'
  let currentStageColor = 'text-slate-400'
  let currentPulse = false
  if (activeNode) {
    currentStageText = activeNode.title
    currentStageColor = activeNode.status === 'active' ? 'text-cyan-300' : 'text-emerald-300'
    currentPulse = true
  } else if (isActionGated || (hasFlags)) {
    currentStageText = 'Awaiting Human Approval'
    currentStageColor = 'text-amber-300'
    currentPulse = true
  } else if (isTerminal) {
    currentStageText = 'Pipeline Complete'
    currentStageColor = 'text-emerald-300'
  }

  // Connector between node i and i+1 is "lit" once the flow reaches node i+1
  const connectorLit = (i) => {
    const next = nodes[i + 1]
    const self = nodes[i]
    if (!next) return false
    if (next.status !== 'ready') return true
    return ADVANCED.includes(self.status) && self.status !== 'active'
  }
  // A connector is "flowing" (animated) when the next node is actively working
  const connectorFlowing = (i) => nodes[i + 1]?.status === 'active'

  // Selected branch summary for the active alert
  let activeBranchText = 'Autonomous Threat Intercept'
  let activeBranchColor = 'text-cyan-400'
  if (hasFlags) {
    activeBranchText = 'Branch: Firewall Adversarial Quarantine (Direct Human Escalation, 0 Agent Calls)'
    activeBranchColor = 'text-red-400'
  } else if (isPrimaryFP) {
    activeBranchText = 'Branch: False Positive Auto-Close & RAG Memory Store (0 Secondary Calls)'
    activeBranchColor = 'text-emerald-400'
  } else if (isActionGated) {
    activeBranchText = 'Branch: High-Impact Action Gated — Human Authorization Required'
    activeBranchColor = 'text-amber-400'
  } else if (isActionExecuted) {
    activeBranchText = 'Branch: Dual-Agent Threat Confirmation — Autonomous Containment Executed'
    activeBranchColor = 'text-cyan-400'
  }

  return (
    <div className="glass-panel rounded-2xl p-5 border-slate-800/80 bg-slate-950/70 space-y-6 shadow-2xl relative overflow-hidden">

      {/* ── Top Header: Title & Live Current-Stage Indicator ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/70 pb-3.5">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping absolute" />
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(34,211,238,0.9)]" />
          </div>
          <div>
            <h3 className="font-display font-bold text-sm tracking-wide text-white uppercase flex items-center gap-2">
              <span>Autonomous Workflow Pipeline</span>
              <span className="text-[10px] font-mono font-normal px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                LIVE VISUAL GRAPH
              </span>
            </h3>
            <p className="text-[11px] font-mono text-slate-400 mt-0.5">
              Dual-Agent Reasoning Highway • Sovereign Dual-Core Pipeline
            </p>
          </div>
        </div>

        {/* Current live stage badge (pulses while processing) */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-cyan-500/30 font-mono text-xs shadow-[0_0_12px_rgba(34,211,238,0.15)]">
            <span className={`w-2 h-2 rounded-full ${currentPulse ? 'bg-cyan-400 animate-pulse' : isTerminal ? 'bg-emerald-400' : 'bg-slate-600'}`} />
            <span className="text-slate-400 text-[11px]">NOW:</span>
            <span className={`font-semibold text-[11px] uppercase tracking-wide ${currentStageColor}`}>
              {currentStageText}
            </span>
          </div>

          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-900/90 border border-slate-800 font-mono text-xs">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-slate-400 text-[11px]">Current Path:</span>
            <span className={`font-semibold text-[11px] ${activeBranchColor}`}>
              {activeBranchText}
            </span>
          </div>
        </div>
      </div>

      {/* ── Live Pipeline Strip: 6 nodes wired by animated directional connectors ──
          Nodes flex to the available column width with a low readable minimum, so all
          six stages stay on screen in the shared command-center column; scrolling is
          only a last-resort fallback on very narrow viewports. */}
      <div className="relative">
        <div className="flex items-stretch gap-0 overflow-x-auto pb-1">
          {nodes.map((node, i) => (
            <React.Fragment key={node.id}>
              <div className="flex-1 min-w-[92px] lg:min-w-[104px] xl:min-w-[124px]">
                <WorkflowNode {...node} />
              </div>
              {i < nodes.length - 1 && (
                <Connector lit={connectorLit(i)} flowing={connectorFlowing(i)} bypassed={nodes[i + 1].status === 'bypassed'} />
              )}
            </React.Fragment>
          ))}
        </div>
        <div className="lg:hidden text-[10px] font-mono text-slate-600 mt-1.5 text-right">
          ↔ drag bar to see all 6 stages
        </div>
      </div>

      {/* ── Visual Decision Branch Matrix & Pathways ── */}
      <div className="space-y-3 pt-3 border-t border-slate-800/70">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs font-bold text-slate-300 uppercase tracking-wider">
              Decision Branch Architecture
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              (Live Flow Gating & Resolution Rules)
            </span>
          </div>

          <span className="text-[11px] font-mono text-cyan-400">
            Active Stage Resolution
          </span>
        </div>

        {/* 4 Interactive Visual Decision Branches */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">

          {/* Branch 1: Firewall Check */}
          <BranchCard
            stageNumber="01"
            title="Log Poison Firewall"
            rule="24 Regex & Heuristic Injection Rules"
            activeChoice={hasFlags ? 'poison' : isFirewallComplete ? 'clean' : null}
            choices={[
              {
                id: 'clean',
                label: 'Clean Log Payload',
                sub: 'Proceed to Primary Agent reasoning',
                color: 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300',
                badge: 'FORWARD',
              },
              {
                id: 'poison',
                label: 'Adversarial Prompt Detected',
                sub: 'Direct Human Escalation (0 Agent calls)',
                color: 'border-red-500/40 bg-red-950/30 text-red-300 glow-red',
                badge: 'QUARANTINE',
              },
            ]}
          />

          {/* Branch 2: Primary Verdict */}
          <BranchCard
            stageNumber="02"
            title="Primary Triage Verdict"
            rule="High-Speed Signal Classification"
            activeChoice={hasFlags ? null : isPrimaryFP ? 'fp' : isPrimaryTP ? 'tp' : null}
            choices={[
              {
                id: 'fp',
                label: 'False Positive (Benign)',
                sub: 'Auto-Close & RAG Memory (0 Secondary calls)',
                color: 'border-emerald-500/40 bg-emerald-950/20 text-emerald-300',
                badge: 'AUTO-CLOSE',
              },
              {
                id: 'tp',
                label: 'True Positive (Actionable)',
                sub: 'Escalate to Secondary Auditor Agent',
                color: 'border-cyan-500/40 bg-cyan-950/20 text-cyan-300',
                badge: 'CROSS-CHECK',
              },
            ]}
          />

          {/* Branch 3: Secondary Audit */}
          <BranchCard
            stageNumber="03"
            title="Secondary Cross-Check"
            rule="Independent Re-evaluation & Consensus"
            activeChoice={hasFlags || isPrimaryFP ? null : isSecondaryTP ? 'confirm' : (isSecondaryFP || isSecondaryDispute) ? 'dispute' : null}
            choices={[
              {
                id: 'confirm',
                label: 'Threat Confirmed',
                sub: 'Consensus reached ➔ Action Gating Engine',
                color: 'border-purple-500/40 bg-purple-950/20 text-purple-300',
                badge: 'ADVANCE',
              },
              {
                id: 'dispute',
                label: 'Verdict Disagreement',
                sub: 'FP override or escalated consensus review',
                color: 'border-amber-500/40 bg-amber-950/20 text-amber-300',
                badge: 'AUDIT',
              },
            ]}
          />

          {/* Branch 4: Action Impact Gating */}
          <BranchCard
            stageNumber="04"
            title="Impact Gating Engine"
            rule="Blast Radius & Sensitivity Catalog"
            activeChoice={hasFlags ? null : isActionExecuted ? 'standard' : isActionGated ? 'high' : null}
            choices={[
              {
                id: 'standard',
                label: 'Standard Impact Action',
                sub: 'Autonomous Mitigation (IP Block / Host Isolate)',
                color: 'border-cyan-500/40 bg-cyan-950/20 text-cyan-300',
                badge: 'AUTONOMOUS',
              },
              {
                id: 'high',
                label: 'High Impact Action',
                sub: 'HALT ➔ Require Human Analyst Approval',
                color: 'border-amber-500/40 bg-amber-950/25 text-amber-300 glow-amber',
                badge: 'HUMAN GATED',
              },
            ]}
          />

        </div>
      </div>

    </div>
  )
}

/** Animated directional connector between two pipeline nodes */
function Connector({ lit, flowing, bypassed }) {
  const lineColor = lit
    ? bypassed ? 'bg-slate-700' : 'bg-emerald-500'
    : 'bg-slate-800'

  return (
    <div className="flex-shrink-0 w-4 sm:w-5 lg:w-6 flex items-center justify-center relative">
      <div className={`relative w-full h-0.5 ${lineColor} transition-colors duration-500`}>
        {/* arrow head */}
        <div
          className={`absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0
            border-t-[4px] border-t-transparent border-b-[4px] border-b-transparent border-l-[7px]
            ${lit && !bypassed ? 'border-l-emerald-400' : 'border-l-slate-700'}`}
        />
        {/* traveling packet pulse while the next stage is actively working */}
        {flowing && (
          <span className="absolute top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(34,211,238,0.9)] animate-pipeflow" />
        )}
      </div>
    </div>
  )
}

/** Individual Pipeline Stage Node */
function WorkflowNode({
  step,
  title,
  provider,
  icon,
  status,
  statusLabel,
  description,
  highlight,
  isAlert,
  isWarning,
}) {
  const statusStyles = {
    active: 'border-cyan-500/70 bg-cyan-950/30 shadow-[0_0_18px_rgba(6,182,212,0.35)] text-white ring-2 ring-cyan-400/40',
    complete: 'border-emerald-500/50 bg-emerald-950/20 shadow-[0_0_12px_rgba(16,185,129,0.15)] text-white',
    error: 'border-red-500/60 bg-red-950/30 shadow-[0_0_18px_rgba(239,68,68,0.3)] text-white glow-red',
    warning: 'border-amber-500/60 bg-amber-950/25 shadow-[0_0_15px_rgba(245,158,11,0.2)] text-white glow-amber',
    bypassed: 'border-slate-800 bg-slate-950/40 text-slate-500 opacity-60',
    ready: 'border-slate-800/80 bg-slate-900/30 text-slate-400',
  }

  const badgeStyles = {
    active: 'bg-cyan-500/25 text-cyan-200 border-cyan-500/50 animate-pulse',
    complete: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    error: 'bg-red-500/20 text-red-400 border-red-500/40 font-bold',
    warning: 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold',
    bypassed: 'bg-slate-900/60 text-slate-500 border-slate-800',
    ready: 'bg-slate-950 text-slate-500 border-slate-800',
  }

  return (
    <div
      className={`rounded-2xl p-2.5 lg:p-3.5 border transition-all duration-300 flex flex-col justify-between h-full min-h-[145px] ${
        statusStyles[status] || statusStyles.ready
      } ${highlight && status !== 'active' ? 'ring-1 ring-white/10' : ''}`}
    >
      <div>
        {/* Top: Icon & Step */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-base lg:text-lg leading-none flex-shrink-0">{icon}</span>
            <span className="font-display font-bold text-[11px] lg:text-xs text-white tracking-wide truncate">
              {title}
            </span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-900/80 border border-slate-800 text-slate-400 flex-shrink-0 ml-1">
            #{step}
          </span>
        </div>

        {/* Provider Tag */}
        <div className="text-[9px] lg:text-[10px] font-mono text-slate-400 mb-2 truncate">
          {provider}
        </div>
      </div>

      <div>
        {/* Status Badge */}
        <div
          className={`px-1.5 lg:px-2 py-1 rounded-lg text-[9px] lg:text-[10px] font-mono font-semibold border truncate mb-1.5 ${
            badgeStyles[status] || badgeStyles.ready
          }`}
        >
          {statusLabel}
        </div>

        {/* Short description */}
        <div className="text-[9px] lg:text-[10px] font-mono text-slate-500 truncate leading-tight">
          {description}
        </div>
      </div>
    </div>
  )
}

/** Decision Branch Resolution Card */
function BranchCard({ stageNumber, title, rule, activeChoice, choices }) {
  return (
    <div className="p-3.5 rounded-xl border border-slate-800/80 bg-slate-900/40 flex flex-col justify-between space-y-2.5">
      <div>
        <div className="flex items-center justify-between border-b border-slate-800/70 pb-1.5">
          <span className="font-display font-bold text-xs text-slate-200 flex items-center gap-1.5">
            <span className="text-cyan-400 font-mono text-[11px]">#{stageNumber}</span>
            <span>{title}</span>
          </span>
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-400">
            {activeChoice ? 'RESOLVED' : 'STANDBY'}
          </span>
        </div>
        <p className="text-[10px] font-mono text-slate-500 mt-1 leading-tight">
          {rule}
        </p>
      </div>

      <div className="space-y-1.5">
        {choices.map((choice) => {
          const isSelected = activeChoice === choice.id
          return (
            <div
              key={choice.id}
              className={`p-2 rounded-lg border transition-all ${
                isSelected
                  ? `${choice.color} shadow-sm font-semibold`
                  : 'border-slate-800/60 bg-slate-950/40 text-slate-500 opacity-40'
              }`}
            >
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="truncate">{choice.label}</span>
                <span className="text-[9px] font-bold px-1.5 py-0.2 rounded border border-current ml-1 flex-shrink-0">
                  {isSelected ? `✓ ${choice.badge}` : choice.badge}
                </span>
              </div>
              <div className="text-[10px] opacity-80 mt-0.5 leading-snug">
                {choice.sub}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
