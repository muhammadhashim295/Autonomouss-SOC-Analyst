/**
 * FlowChart — Interactive, glassmorphic node graph visualization matching
 * the investigation workflow branches:
 *
 * Row 1: Live Env → Alert Queue → Log Firewall → [Escalate if Poisoned] → Primary Agent
 * Row 2: Primary Agent Details & Verdict Branch
 * Row 3: Secondary Agent Details & Re-investigation Cross-Check
 * Row 4: Action Impact Gating → [Auto Execute or Escalate to Human Analyst]
 */

const BRANCH_LABELS = {
  firewall: { left: '③a POISONED (FLAGGED)', right: '③b CLEAN (PROCEED)' },
  primary: { left: '④a FALSE POSITIVE', right: '④b TRUE POSITIVE' },
  secondary: { left: '⑤ FALSE POSITIVE', right: '⑤ TRUE POSITIVE' },
  action: { left: '⑦ AUTONOMOUS EXECUTE', right: '⑦ HUMAN APPROVAL REQD' },
}

export default function FlowChart({ stages, firewallFlags, primaryData, secondaryData, caseResult }) {
  const hasFlags = firewallFlags && firewallFlags.length > 0

  const firewallBranch = hasFlags ? 'left' : 'right'
  const primaryVerdict = primaryData?.verdict
  const primaryBranch = primaryVerdict === 'false_positive' ? 'left' : primaryVerdict === 'true_positive' ? 'right' : null
  const secondaryVerdict = secondaryData?.verdict
  const secondaryBranch = secondaryVerdict === 'false_positive' ? 'left' : secondaryVerdict === 'true_positive' ? 'right' : null
  const actionBranch = caseResult?.action_status === 'executed' ? 'left'
    : caseResult?.action_status === 'awaiting_approval' || caseResult?.action_status === 'escalated' ? 'right' : null

  const ns = (key) => stages[key] || 'pending'

  return (
    <div className="glass-panel rounded-2xl p-6 overflow-x-auto border-emerald-500/20">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          <h3 className="font-display font-bold text-xs uppercase tracking-wider text-slate-300">
            Autonomous Pipeline Flow Architecture
          </h3>
        </div>
        <span className="font-mono text-[11px] text-slate-500">Live Stage Tracker</span>
      </div>

      <div className="flex flex-col gap-1 min-w-[760px]">
        
        {/* ══ Row 1: Live Env → Queue → Firewall → Primary Agent ══ */}
        <div className="flex items-center gap-0">
          <Node label="Live Environment" sub="① Org Ingestion" icon="◉" status={ns('liveEnv')} />
          <Arrow active={ns('liveEnv') !== 'pending'} />
          <Node label="Alert Queue" sub="Feed Buffer" icon="☰" status={ns('liveEnv')} />
          <Arrow active={ns('liveEnv') !== 'pending'} />
          <Node label="Log Firewall" sub="② Poison Check" icon="🛡" status={hasFlags ? 'error' : ns('firewall')} />
          <Arrow taken={firewallBranch === 'right'} active={ns('firewall') !== 'pending'} />
          <Node label="Primary Agent" sub="③ Triage Signal" icon="▣" status={ns('primary')}
            active={ns('primary') !== 'pending'} glow={ns('primary') === 'active'} />
        </div>

        {/* Firewall escalate branch */}
        <div className="flex items-start ml-[calc(2*(150px+16px)+2*44px+16px)] pl-10">
          <div className="flex flex-col items-center -mt-1">
            <BranchArrow label={BRANCH_LABELS.firewall.left} taken={firewallBranch === 'left'} direction="up" />
            {firewallBranch === 'left' && (
              <Node label="Firewall Flagged" sub="Logged + Quarantined" icon="⚠" status="error" small />
            )}
          </div>
        </div>

        {/* ══ Row 2: Primary Agent Detail ══ */}
        <div className="mt-4 flex items-start gap-0">
          <div className="flex-shrink-0" style={{ width: 'calc(3*(150px+16px) + 2*44px + 16px)' }} />
          <AgentNode
            name="Primary Triage Agent"
            status={ns('primary')}
            data={primaryData}
            branchLabels={BRANCH_LABELS.primary}
            branchTaken={primaryBranch}
          />
          {primaryBranch === 'right' && (
            <>
              <Arrow taken={true} active={true} />
              <Node label="Secondary Agent" sub="⑤ Deep Cross-Check" icon="◫" status={ns('secondary')}
                active={ns('secondary') !== 'pending'} glow={ns('secondary') === 'active'} />
            </>
          )}
        </div>

        {/* Primary FP branch */}
        {primaryBranch === 'left' && (
          <div className="mt-2 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(3*(150px+16px) + 2*44px + 16px)' }} />
            <div className="flex items-center">
              <BranchArrow label={BRANCH_LABELS.primary.left} taken={true} direction="down" />
              <Node label="RAG Memory Store" sub="④ FP Record Indexed" icon="▪" status="complete" small />
            </div>
          </div>
        )}

        {/* ══ Row 3: Secondary Agent Detail ══ */}
        {primaryBranch === 'right' && (
          <div className="mt-4 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(4*(150px+16px) + 3*44px + 16px)' }} />
            <AgentNode
              name="Secondary Agent"
              status={ns('secondary')}
              data={secondaryData}
              branchLabels={BRANCH_LABELS.secondary}
              branchTaken={secondaryBranch}
            />
          </div>
        )}

        {/* Secondary FP → RAG Memory */}
        {secondaryBranch === 'left' && primaryBranch === 'right' && (
          <div className="mt-2 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(4*(150px+16px) + 3*44px + 16px)' }} />
            <div className="flex items-center">
              <BranchArrow label={BRANCH_LABELS.secondary.left} taken={true} direction="down" />
              <Node label="RAG Memory Store" sub="⑤ FP Record Indexed" icon="▪" status="complete" small />
            </div>
          </div>
        )}

        {/* ══ Row 4: Action Pipeline & Human Gating ══ */}
        {secondaryBranch === 'right' && (
          <div className="mt-4 flex items-start gap-0">
            <div className="flex-shrink-0" style={{ width: 'calc(4*(150px+16px) + 3*44px + 16px)' }} />
            <Node label="Impact Gating" sub="⑥ Response Catalog" icon="⚡" status={ns('action')} />
            <Arrow taken={actionBranch === 'left'} active={ns('action') !== 'pending'} />
            <Node label="Execution Logged" sub="⑦ Case Closed" icon="▪" status={ns('db')} />
            {actionBranch === 'right' && (
              <>
                <BranchArrow label={BRANCH_LABELS.action.right} taken={true} direction="right" />
                <Node label="Human Approval" sub="Awaiting Analyst" icon="⚠" status="error" small />
              </>
            )}
          </div>
        )}

      </div>
    </div>
  )
}

function Node({ label, sub, icon, status, active, glow, small }) {
  const colors = {
    pending: 'border-slate-800 bg-slate-950/60 text-slate-500',
    active: 'border-emerald-500/60 bg-emerald-500/15 text-emerald-300 glow-green font-semibold',
    complete: 'border-emerald-700/50 bg-emerald-950/30 text-emerald-400',
    error: 'border-red-500/60 bg-red-500/15 text-red-300 glow-red font-semibold',
  }

  const iconColors = {
    pending: 'text-slate-600',
    active: 'text-emerald-400 text-glow-green',
    complete: 'text-emerald-400',
    error: 'text-red-400 text-glow-red',
  }

  return (
    <div
      className={`flex-shrink-0 rounded-xl border transition-all duration-300 glass-panel ${colors[status]} ${
        small ? 'px-3 py-2' : 'px-3.5 py-2.5'
      }`}
      style={small ? { minWidth: 120 } : { minWidth: 150 }}
    >
      <div className="flex items-center gap-2">
        <span className={`${iconColors[status]} ${active ? 'animate-pulse' : ''} text-base`}>
          {icon}
        </span>
        <div>
          <div className="font-mono text-xs font-semibold leading-tight">{label}</div>
          {sub && <div className="text-[10px] text-slate-500 font-mono leading-tight mt-0.5">{sub}</div>}
        </div>
      </div>
    </div>
  )
}

function Arrow({ taken, active }) {
  return (
    <div className="flex-shrink-0 w-11 h-0.5 mx-1 transition-colors duration-300 relative bg-slate-800">
      <div
        className={`h-full transition-all duration-500 ${
          taken !== false && active ? 'bg-emerald-500 glow-green' : 'bg-slate-800'
        }`}
      />
      <div
        className={`absolute right-0 top-1/2 -translate-y-1/2 w-0 h-0
          border-t-[4px] border-t-transparent
          border-b-[4px] border-b-transparent
          ${taken !== false && active ? 'border-l-[6px] border-l-emerald-400' : 'border-l-[6px] border-l-slate-700'}
        `}
      />
    </div>
  )
}

function BranchArrow({ label, taken, direction = 'down' }) {
  const color = taken ? 'text-red-400 font-semibold' : 'text-slate-500'
  const lineColor = taken ? 'bg-red-500/50 glow-red' : 'bg-slate-800'

  if (direction === 'up') {
    return (
      <div className="flex flex-col items-center">
        <span className={`text-[10px] font-mono ${color} whitespace-nowrap mb-1`}>{label}</span>
        <div className={`w-0.5 h-4 ${lineColor}`} />
      </div>
    )
  }

  if (direction === 'right') {
    return (
      <div className="flex items-center gap-1.5 mx-1">
        <div className={`w-8 h-0.5 ${lineColor}`} />
        <span className={`text-[10px] font-mono ${color} whitespace-nowrap`}>{label}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 mr-2">
      <div className={`w-0.5 h-4 ${lineColor}`} />
      <span className={`text-[10px] font-mono ${color} whitespace-nowrap`}>{label}</span>
    </div>
  )
}

function AgentNode({ name, status, data, branchLabels, branchTaken }) {
  const isActive = status === 'active'
  const isDone = status === 'complete'
  const reasoning = data?.reasoning
  const verdict = data?.verdict

  return (
    <div
      className={`rounded-xl border glass-panel transition-all duration-300 p-3.5 ${
        isDone ? 'border-emerald-500/40 bg-emerald-950/20' :
        isActive ? 'border-amber-500/40 bg-amber-950/15 glow-amber' :
        'border-slate-800 bg-slate-950/40'
      }`}
      style={{ minWidth: 230, maxWidth: 320 }}
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${
            isDone ? 'bg-emerald-400' : isActive ? 'bg-amber-400 animate-pulse' : 'bg-slate-600'
          }`} />
          <span className="font-display font-bold text-xs text-white">{name}</span>
        </div>

        {verdict && (
          <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
            verdict === 'true_positive'
              ? 'bg-red-500/20 text-red-400 border border-red-500/30'
              : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
          }`}>
            {verdict === 'true_positive' ? 'TP' : 'FP'}
          </span>
        )}
      </div>

      {isActive && !reasoning && (
        <div className="flex items-center gap-1.5 py-2">
          <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
          <span className="text-amber-300 font-mono text-[11px]">Reasoning live...</span>
        </div>
      )}

      {reasoning && (
        <div className="text-[11px] font-mono text-slate-300 leading-relaxed max-h-[70px] overflow-hidden relative">
          {reasoning.slice(0, 180)}{reasoning.length > 180 && '...'}
        </div>
      )}

      {branchTaken && (
        <div className="mt-2 pt-2 border-t border-slate-800/60 flex items-center gap-2">
          <span className={`text-[10px] font-mono font-semibold ${
            branchTaken === 'left' ? 'text-emerald-400' : 'text-red-400'
          }`}>
            → {branchTaken === 'left' ? branchLabels.left : branchLabels.right}
          </span>
        </div>
      )}
    </div>
  )
}
