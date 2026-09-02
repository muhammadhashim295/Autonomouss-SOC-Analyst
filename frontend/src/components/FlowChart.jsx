/**
 * FlowChart — matches the hand-drawn flowchart layout with decision
 * branches. Nodes are positioned in a grid; arrows connect them.
 *
 * Layout (matching the user's flowchart):
 *   Row 1: Live Env → Queue → Firewall → [Escalate branch up]
 *   Row 2: Primary Agent (with reasoning detail)
 *   Row 3: Doc DB ← Secondary Agent (with reasoning detail)
 *   Row 4: Action → Ask Analyst branch
 */

const BRANCH_LABELS = {
  firewall: { left: '③a POISONED', right: '③b CLEAN' },
  primary: { left: '④a FALSE POSITIVE', right: '④b TRUE POSITIVE' },
  secondary: { left: '⑤ FALSE POSITIVE', right: '⑤ TRUE POSITIVE' },
  action: { left: '⑦ ALLOWED', right: 'NOT ALLOWED' },
}

export default function FlowChart({ stages, firewallFlags, primaryData, secondaryData, caseResult }) {
  const hasFlags = firewallFlags && firewallFlags.length > 0

  // Determine branch outcomes from data
  const firewallBranch = hasFlags ? 'left' : 'right' // left=poisoned, right=clean
  const primaryVerdict = primaryData?.verdict
  const primaryBranch = primaryVerdict === 'false_positive' ? 'left' : primaryVerdict === 'true_positive' ? 'right' : null
  const secondaryVerdict = secondaryData?.verdict
  const secondaryBranch = secondaryVerdict === 'false_positive' ? 'left' : secondaryVerdict === 'true_positive' ? 'right' : null
  const actionBranch = caseResult?.action_status === 'executed' ? 'left'
    : caseResult?.action_status === 'awaiting_approval' || caseResult?.action_status === 'escalated' ? 'right' : null

  // Node status helper
  const ns = (key) => stages[key] || 'pending'

  return (
    <div className="rounded-lg border border-slate-800/50 bg-slate-950/50 p-5 overflow-x-auto">
      <div className="text-xs font-mono text-slate-500 uppercase tracking-wider mb-5">
        Investigation Workflow
      </div>

      <div className="flex flex-col gap-0 min-w-[700px]">
        {/* ═══ Row 1: Ingestion → Firewall ═══ */}
        <div className="flex items-center gap-0">
          <Node label="Live Environment" sub="① Organization" icon="◉" status={ns('liveEnv')} />
          <Arrow />
          <Node label="Alert Queue" sub="Feed" icon="☰" status={ns('liveEnv')} />
          <Arrow />
          <Node label="Firewall" sub="② Poison Check" icon="◈" status={hasFlags ? 'error' : ns('firewall')} />
          <Arrow taken={firewallBranch === 'right'} />
          <Node label="Primary Agent" sub="③b Triage" icon="▣" status={ns('primary')}
            active={ns('primary') !== 'pending'} glow={ns('primary') === 'active'} />
        </div>

        {/* Firewall escalate branch (upward from Firewall) */}
        <div className="flex items-start ml-[calc(2*(140px+16px)+2*40px+16px)] pl-10">
          <div className="flex flex-col items-center -mt-1">
            <BranchArrow label={BRANCH_LABELS.firewall.left} taken={firewallBranch === 'left'} direction="up" />
            {firewallBranch === 'left' && (
              <Node label="Escalate to Human" sub="Drop + Alert Analyst" icon="⚠" status="error" small />
            )}
          </div>
        </div>

        {/* ═══ Row 2: Primary Agent detail ═══ */}
        <div className="mt-3 flex items-start gap-0">
          {/* Spacer to align under Primary Agent position */}
          <div className="flex-shrink-0" style={{ width: 'calc(3*(140px+16px) + 2*40px + 16px)' }} />
          <AgentNode
            name="Primary Agent"
            status={ns('primary')}
            data={primaryData}
            branchLabels={BRANCH_LABELS.primary}
            branchTaken={primaryBranch}
          />
          {primaryBranch === 'right' && (
            <>
              <Arrow taken={true} />
              <Node label="Secondary Agent" sub="⑤ Re-investigate" icon="◫" status={ns('secondary')}
                active={ns('secondary') !== 'pending'} glow={ns('secondary') === 'active'} />
            </>
          )}
        </div>

        {/* Primary FP branch */}
        {primaryBranch === 'left' && (
          <div className="mt-2 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(3*(140px+16px) + 2*40px + 16px)' }} />
            <div className="flex items-center">
              <BranchArrow label={BRANCH_LABELS.primary.left} taken={true} direction="down" />
              <Node label="Documentation DB" sub="④a Case Filed" icon="▪" status="complete" small />
            </div>
          </div>
        )}

        {/* ═══ Row 3: Secondary Agent detail ═══ */}
        {primaryBranch === 'right' && (
          <div className="mt-3 flex items-start gap-0">
            {/* Spacer to align under Secondary Agent */}
            <div className="flex-shrink-0" style={{ width: 'calc(4*(140px+16px) + 3*40px + 16px)' }} />
            <AgentNode
              name="Secondary Agent"
              status={ns('secondary')}
              data={secondaryData}
              branchLabels={BRANCH_LABELS.secondary}
              branchTaken={secondaryBranch}
            />
          </div>
        )}

        {/* Secondary FP → Doc DB */}
        {secondaryBranch === 'left' && primaryBranch === 'right' && (
          <div className="mt-2 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(4*(140px+16px) + 3*40px + 16px)' }} />
            <div className="flex items-center">
              <BranchArrow label={BRANCH_LABELS.secondary.left} taken={true} direction="down" />
              <Node label="Documentation DB" sub="⑤ Case Filed" icon="▪" status="complete" small />
            </div>
          </div>
        )}

        {/* ═══ Row 4: Action ═══ */}
        {secondaryBranch === 'right' && (
          <div className="mt-3 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(4*(140px+16px) + 3*40px + 16px)' }} />
            <Node label="Action" sub="⑥ Response" icon="⚡" status={ns('action')} />
            <Arrow taken={actionBranch === 'left'} />
            <Node label="Documentation DB" sub="⑦ Case Filed" icon="▪" status={ns('db')} />
            {actionBranch === 'right' && (
              <>
                <BranchArrow label={BRANCH_LABELS.action.right} taken={true} direction="right" />
                <Node label="Ask Analyst" sub="Awaiting Approval" icon="⚠" status="error" small />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ════════════════════════════════════════
// Sub-components
// ════════════════════════════════════════

function Node({ label, sub, icon, status, active, glow, small }) {
  const colors = {
    pending: 'border-slate-800/50 bg-slate-900/40 text-slate-600',
    active: 'border-emerald-500/50 bg-emerald-500/10 text-emerald-300 glow-green',
    complete: 'border-emerald-700/40 bg-emerald-900/20 text-emerald-600',
    error: 'border-red-500/50 bg-red-500/10 text-red-400 glow-red',
  }
  const iconColors = {
    pending: 'text-slate-600',
    active: 'text-emerald-400 text-glow-green',
    complete: 'text-emerald-600',
    error: 'text-red-400 text-glow-red',
  }

  return (
    <div className={`flex-shrink-0 rounded-lg border transition-all duration-500 ${colors[status]} ${small ? 'px-2 py-1.5' : 'px-3 py-2'}`}
      style={small ? { minWidth: 100 } : { minWidth: 140 }}>
      <div className="flex items-center gap-2">
        <span className={`${iconColors[status]} ${active ? 'animate-pulse' : ''} ${small ? 'text-sm' : 'text-base'}`}>
          {icon}
        </span>
        <div>
          <div className={`font-mono ${small ? 'text-xs' : 'text-xs'} leading-tight`}>{label}</div>
          {sub && <div className="text-xs text-slate-500 font-mono leading-tight">{sub}</div>}
        </div>
      </div>
    </div>
  )
}

function Arrow({ taken }) {
  return (
    <div className={`flex-shrink-0 w-10 h-0.5 mx-0.5 transition-colors duration-300 relative ${
      taken !== false ? 'bg-emerald-600/50' : 'bg-slate-800/30'
    }`}>
      <div className={`absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0
        border-t-[4px] border-t-transparent
        border-b-[4px] border-b-transparent
        ${taken !== false ? 'border-l-[6px] border-l-emerald-600/50' : 'border-l-[6px] border-l-slate-800/30'}
      `} />
    </div>
  )
}

function BranchArrow({ label, taken, direction = 'down' }) {
  const color = taken ? 'text-red-400' : 'text-slate-600'
  const lineColor = taken ? 'bg-red-500/40' : 'bg-slate-800/30'

  if (direction === 'up') {
    return (
      <div className="flex flex-col items-center">
        <span className={`text-xs font-mono ${color} whitespace-nowrap mb-0.5`}>{label}</span>
        <div className={`w-0.5 h-4 ${lineColor}`} />
      </div>
    )
  }
  if (direction === 'right') {
    return (
      <div className="flex items-center gap-1 mx-1">
        <div className={`w-8 h-0.5 ${lineColor}`} />
        <span className={`text-xs font-mono ${color} whitespace-nowrap`}>{label}</span>
      </div>
    )
  }
  // down
  return (
    <div className="flex items-center gap-2 mr-2">
      <div className={`w-0.5 h-4 ${lineColor}`} />
      <span className={`text-xs font-mono ${color} whitespace-nowrap`}>{label}</span>
    </div>
  )
}

function AgentNode({ name, status, data, branchLabels, branchTaken }) {
  const isActive = status === 'active'
  const isDone = status === 'complete'
  const reasoning = data?.reasoning
  const verdict = data?.verdict

  return (
    <div className={`rounded-lg border transition-all duration-500 p-3 ${
      isDone ? 'border-emerald-500/40 bg-emerald-950/15' :
      isActive ? 'border-yellow-500/30 bg-yellow-950/10' :
      'border-slate-800/50 bg-slate-900/30'
    }`} style={{ minWidth: 220, maxWidth: 320 }}>
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <div className={`w-2 h-2 rounded-full ${
          isDone ? 'bg-emerald-400' : isActive ? 'bg-yellow-400 animate-pulse' : 'bg-slate-600'
        }`} />
        <span className="font-mono text-xs text-white">{name}</span>
        {verdict && (
          <span className={`ml-auto px-1.5 py-0.5 rounded text-xs font-mono ${
            verdict === 'true_positive'
              ? 'bg-red-500/15 text-red-400 border border-red-500/20'
              : 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
          }`}>
            {verdict === 'true_positive' ? 'TP' : 'FP'}
          </span>
        )}
      </div>

      {/* Thinking indicator */}
      {isActive && !reasoning && (
        <div className="flex items-center gap-1.5 py-2">
          <div className="w-1 h-1 rounded-full bg-yellow-400 animate-pulse" />
          <div className="w-1 h-1 rounded-full bg-yellow-400 animate-pulse" style={{ animationDelay: '0.2s' }} />
          <div className="w-1 h-1 rounded-full bg-yellow-400 animate-pulse" style={{ animationDelay: '0.4s' }} />
          <span className="text-yellow-400/60 font-mono text-xs ml-1">Reasoning</span>
        </div>
      )}

      {/* Reasoning preview */}
      {reasoning && (
        <div className="text-xs font-mono text-slate-400 leading-relaxed max-h-[80px] overflow-hidden relative">
          {reasoning.slice(0, 200)}{reasoning.length > 200 && '...'}
          {reasoning.length > 80 && (
            <div className="absolute bottom-0 left-0 right-0 h-4 bg-gradient-to-t from-slate-950/80 to-transparent" />
          )}
        </div>
      )}

      {/* Branch outcome labels */}
      {branchTaken && (
        <div className="mt-2 pt-2 border-t border-slate-800/30 flex items-center gap-2">
          <span className={`text-xs font-mono ${
            branchTaken === 'left' ? 'text-emerald-500/70' : 'text-red-400/70'
          }`}>
            → {branchTaken === 'left' ? branchLabels.left : branchLabels.right}
          </span>
        </div>
      )}
    </div>
  )
}
